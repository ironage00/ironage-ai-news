"""Phase C1(저장 시점 이동)·C2(30일 보존) 테스트.

conftest.py가 격리된 임시 SQLite DB로 DATABASE_URL을 고정하므로, 여기서는
실제 DB에 대고 삽입/갱신/정리 분기를 검증한다(순수 monkeypatch가 아니라
실제 SQLAlchemy 세션 통합 테스트). 테스트 간 간섭을 피하기 위해 title/link는
매 테스트 uuid로 유일하게 만든다.
"""
import datetime
import uuid

from sqlalchemy import text

import news_engine as ne
from news_engine import (
    NewsArticle,
    get_db_session,
    _upsert_analyzed_article,
    cleanup_stale_unselected_articles,
)


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _fetch(link: str):
    with get_db_session() as s:
        row = s.query(NewsArticle).filter_by(link=link).first()
        if row is None:
            return None
        # detached 상태에서도 읽을 수 있도록 필요한 필드만 복사
        return {
            'id': row.id, 'title': row.title, 'is_selected': row.is_selected,
            'is_analyzed': row.is_analyzed, 'analysis_result': row.analysis_result,
            'quality_score': row.quality_score,
        }


# ── _upsert_analyzed_article: 신규 삽입 ──────────────────────────────────────

def test_upsert_inserts_new_row_with_analysis():
    link = f"https://example.com/{_uniq('a')}"
    item = {
        'link': link, 'title': _uniq('제목'), 'content': '본문 내용입니다.' * 5,
        'analysis_result': '## 분석 결과', 'source': '테스트', 'published': None,
    }
    art_id = _upsert_analyzed_article(item, unit_id=1, is_selected=True, ai_model='openai')
    assert art_id is not None
    row = _fetch(link)
    assert row['is_analyzed'] is True
    assert row['is_selected'] is True
    assert row['analysis_result'] == '## 분석 결과'
    assert row['quality_score'] == 1.0


def test_upsert_not_selected_gets_zero_quality_score():
    link = f"https://example.com/{_uniq('b')}"
    item = {'link': link, 'title': _uniq('제목'), 'content': 'x' * 50, 'analysis_result': 'y'}
    _upsert_analyzed_article(item, unit_id=2, is_selected=False, ai_model='openai')
    row = _fetch(link)
    assert row['is_selected'] is False
    assert row['quality_score'] == 0.0


# ── _upsert_analyzed_article: 기존 row 갱신 (같은 link 재분석) ───────────────

def test_upsert_updates_existing_row_by_link():
    link = f"https://example.com/{_uniq('c')}"
    item1 = {'link': link, 'title': _uniq('원본제목'), 'content': 'short', 'analysis_result': '1차'}
    id1 = _upsert_analyzed_article(item1, unit_id=1, is_selected=False, ai_model='openai')

    item2 = {'link': link, 'title': item1['title'], 'content': 'much longer content ' * 10,
              'analysis_result': '2차(재분석)'}
    id2 = _upsert_analyzed_article(item2, unit_id=1, is_selected=True, ai_model='openai')

    assert id1 == id2  # 새 row가 아니라 같은 row 갱신
    row = _fetch(link)
    assert row['analysis_result'] == '2차(재분석)'
    assert row['is_selected'] is True  # False -> True로 승격, 되돌아가지 않음


def test_upsert_is_selected_never_downgrades_on_rerun():
    """한 번 선별됐던 기사가 재실행에서 미선별로 나와도 is_selected=True 유지."""
    link = f"https://example.com/{_uniq('d')}"
    item = {'link': link, 'title': _uniq('제목'), 'content': 'x' * 50, 'analysis_result': 'a'}
    _upsert_analyzed_article(item, unit_id=1, is_selected=True, ai_model='openai')
    _upsert_analyzed_article(item, unit_id=1, is_selected=False, ai_model='openai')
    row = _fetch(link)
    assert row['is_selected'] is True


# ── _upsert_analyzed_article: 교차 단 제목 유사도 중복 ───────────────────────

def test_upsert_skips_cross_unit_title_duplicate():
    shared_title = _uniq('동일사건제목입니다완전히똑같은제목')
    link1 = f"https://a.example.com/{_uniq('x')}"
    link2 = f"https://b.example.com/{_uniq('y')}"  # 다른 링크, 같은 제목(다른 단 재보도 시뮬레이션)

    id1 = _upsert_analyzed_article(
        {'link': link1, 'title': shared_title, 'content': 'x' * 50, 'analysis_result': 'a'},
        unit_id=1, is_selected=True, ai_model='openai')
    id2 = _upsert_analyzed_article(
        {'link': link2, 'title': shared_title, 'content': 'x' * 50, 'analysis_result': 'b'},
        unit_id=2, is_selected=True, ai_model='openai')

    assert id1 == id2  # link2용 새 row가 생기지 않고 기존 row id 재사용
    assert _fetch(link2) is None  # link2로는 실제 row가 없음(중복 삽입 안 됨)


# ── cleanup_stale_unselected_articles (C2) ───────────────────────────────────

def _insert_raw(link, days_old, is_selected, is_analyzed):
    """cleanup 대상 여부를 직접 통제하기 위해 컬럼을 수동 세팅해 삽입."""
    with get_db_session() as s:
        s.add(NewsArticle(
            title=_uniq('title'), link=link, is_selected=is_selected, is_analyzed=is_analyzed,
            collected_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old),
        ))
        s.commit()


def test_null_flags_row_protected_and_upsert_handles_it():
    """레거시 NULL 플래그 row: cleanup이 지우지 않고, 재분석 upsert가 올바르게 승격.

    참고: ORM은 default=False 때문에 is_selected=None을 넣어도 False로 저장한다
    (즉 NULL row는 ORM 경로로는 생기지 않고 원시 SQL/마이그레이션에서만 발생).
    그 진짜 NULL 상황을 재현하기 위해 raw UPDATE로 컬럼을 NULL로 강제한다.
    """
    link = f"https://example.com/{_uniq('null-legacy')}"
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=40)
    with get_db_session() as s:
        s.add(NewsArticle(title=_uniq('legacy'), link=link, collected_at=old))
        s.commit()
        # ORM default을 우회해 실제 NULL로 강제
        s.execute(
            text("UPDATE news_articles SET is_selected=NULL, is_analyzed=NULL WHERE link=:l"),
            {"l": link},
        )
        s.commit()

    # C2: NULL은 .is_(False)에 매칭되지 않으므로 보호되어야 함
    cleanup_stale_unselected_articles(days=30)
    assert _fetch(link) is not None, "NULL 플래그 row가 삭제됨 — 보호 실패"

    # upsert 재분석: NULL → is_analyzed=True, is_selected=True로 승격
    _upsert_analyzed_article(
        {'link': link, 'title': _uniq('제목'), 'content': 'x' * 50, 'analysis_result': 'z'},
        unit_id=1, is_selected=True, ai_model='openai')
    row = _fetch(link)
    assert row['is_analyzed'] is True
    assert row['is_selected'] is True


def test_cleanup_deletes_only_old_unselected_unanalyzed():
    old_junk = f"https://example.com/{_uniq('old-junk')}"
    old_selected = f"https://example.com/{_uniq('old-selected')}"
    old_analyzed = f"https://example.com/{_uniq('old-analyzed')}"
    recent_junk = f"https://example.com/{_uniq('recent-junk')}"

    _insert_raw(old_junk, days_old=31, is_selected=False, is_analyzed=False)
    _insert_raw(old_selected, days_old=31, is_selected=True, is_analyzed=False)
    _insert_raw(old_analyzed, days_old=31, is_selected=False, is_analyzed=True)
    _insert_raw(recent_junk, days_old=5, is_selected=False, is_analyzed=False)

    deleted = cleanup_stale_unselected_articles(days=30)
    assert deleted >= 1  # 다른 테스트의 잔여 데이터가 섞일 수 있어 >=로 검증

    assert _fetch(old_junk) is None          # 삭제됨
    assert _fetch(old_selected) is not None  # 선별됐던 건 보호
    assert _fetch(old_analyzed) is not None  # 분석됐던 건 보호
    assert _fetch(recent_junk) is not None   # 아직 30일 안 지남
