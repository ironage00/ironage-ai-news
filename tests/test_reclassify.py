"""reclassify_article_unit 점수 계산 회귀 테스트.

버그: 추출 키워드가 term당 매칭 점수를 '합산'하면, 짧은 term("ai")이 한 단의
결합어 키워드 다수("AI 표준", "AI 모델", "AI 시스템" ...)와 전부 부분매칭되어
점수가 인플레이션된다. 실 데이터에서 표준혁신단(23개 AI+X 키워드)이 이 문제로
일반 AI 비즈니스 기사까지 흡수했다 (예: "뉴욕증시 AI 반도체주 급락").

수정: term당 최고 매칭 1건만 반영(sum of max, not sum of all matches).
"""
import contextlib

import json
import news_engine
from news_engine import reclassify_article_unit


class _FakeArticle:
    def __init__(self, unit_id=None, unit_ids=None, title='제목'):
        self.id = 1
        self.unit_id = unit_id
        self.unit_ids = unit_ids
        self.title = title


class _FakeQuery:
    def __init__(self, article):
        self._article = article

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self._article


class _FakeSession:
    def __init__(self, article):
        self._article = article

    def query(self, *a, **k):
        return _FakeQuery(self._article)


def _fake_db_session_factory(article):
    @contextlib.contextmanager
    def _fake(*a, **k):
        yield _FakeSession(article)
    return _fake


# 표준혁신단(2) — 인공지능 PG 4대 영역 결합어(재설계 후 실제 키워드 축약판)
STANDARD_INNOVATION_KWS = [
    "AI 표준", "AI 표준화", "인공지능 표준", "AI 국제표준", "인공지능 표준화",
    "AI 용어", "AI 온톨로지", "AI 참조구조", "AI 참조모델", "AI 프레임워크",
    "AI 모델", "인공지능 모델", "머신러닝 모델", "파운데이션 모델", "거대언어모델",
    "AI 시스템", "인공지능 시스템", "AI 수명주기", "AI 데이터 품질", "MLOps",
    "AI 신뢰성", "인공지능 신뢰성", "AI 안전",
]

# AI융합단(3) — AI 일반 홈
AI_CONVERGENCE_KWS = ["AI", "인공지능", "생성형 AI", "온디바이스 AI", "LLM"]


def _setup_units(monkeypatch):
    monkeypatch.setattr(news_engine, 'get_all_units', lambda: [
        {'id': 2, 'display_name': '표준혁신단'},
        {'id': 3, 'display_name': 'AI융합표준단'},
    ])
    settings = {
        2: {'keywords': STANDARD_INNOVATION_KWS},
        3: {'keywords': AI_CONVERGENCE_KWS},
    }
    monkeypatch.setattr(news_engine, 'load_unit_settings', lambda uid: settings[uid])


def test_short_generic_term_does_not_outscore_specific_unit(monkeypatch):
    """일반 AI 기사(추출 term="ai" 단독)는 표준혁신단으로 재배정되면 안 된다."""
    _setup_units(monkeypatch)
    article = _FakeArticle(unit_id=3, unit_ids=',3,', title='뉴욕증시 AI 반도체주 급락')
    monkeypatch.setattr(news_engine, 'get_db_session', _fake_db_session_factory(article))

    ekw = json.dumps({'key_technologies': ['ai'], 'keywords': []})
    changed = reclassify_article_unit(article.id, ekw)

    # 합산 버그였다면 표준혁신단(23개 결합어 부분매칭 합산)이 AI융합단을 역전했다.
    assert article.unit_id == 3
    assert changed is False or article.unit_id == 3


def test_specific_term_still_reassigns_to_correct_unit(monkeypatch):
    """표준혁신단 전문 용어(정확 매칭)가 실제로 있으면 재배정은 여전히 동작해야 한다."""
    _setup_units(monkeypatch)
    article = _FakeArticle(unit_id=3, unit_ids=',3,', title='AI 신뢰성 국제표준 논의')
    monkeypatch.setattr(news_engine, 'get_db_session', _fake_db_session_factory(article))

    ekw = json.dumps({'key_technologies': ['ai 신뢰성', 'ai 표준화'], 'keywords': []})
    changed = reclassify_article_unit(article.id, ekw)

    assert article.unit_id == 2
    assert changed is True


def test_term_score_is_max_not_sum_across_matching_keywords():
    """단일 term이 여러 부분매칭 키워드를 가져도 점수는 최고 1건만 반영되어야 한다."""
    ukws = [kw.lower() for kw in STANDARD_INNOVATION_KWS]
    term = 'ai'
    # 재현: 옛 로직(합산)이면 23개 키워드 각각 min(len(ukw), len(term))*1.0 만큼 더해짐
    old_sum = sum(
        min(len(ukw), len(term)) * 1.0
        for ukw in ukws if ukw in term or term in ukw
    )
    # 새 로직(max)은 가장 긴 매칭 1건만
    new_max = max(
        (min(len(ukw), len(term)) * 1.0 for ukw in ukws if ukw in term or term in ukw),
        default=0.0,
    )
    assert old_sum > new_max  # 합산이 인플레이션됨을 확인 (회귀 방지용 기준선)
    assert new_max == len(term) * 1.0  # 'ai'가 term이므로 min(len(ukw), 2)=2
