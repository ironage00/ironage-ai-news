"""본문 추출 품질 게이트·선택·실패판정 테스트 (순수 함수).

네트워크·trafilatura 실제 호출은 다루지 않는다 — 정제·게이트·선택 로직만 검증.
"""
from news_engine import (
    _finalize_article_text,
    _extract_with_bs4,
    _choose_extraction,
    _is_extraction_failed,
    _fail,
    _MIN_BODY_LEN,
)


_LONG = ('과학기술정보통신부는 6G 주파수 연구개발 로드맵을 발표했다. '
         '이번 계획은 민간 기업과의 협력으로 추진되며 총 1조원이 투입된다. '
         '삼성전자와 LG전자가 핵심 파트너로 참여한다. '
         '2030년 상용화를 목표로 테라헤르츠 대역 연구가 진행된다. '
         '위성 통합 기술도 주요 과제로 포함됐다.') * 2


# ── _finalize_article_text ───────────────────────────────────────────────────

def test_finalize_accepts_quality_body():
    out = _finalize_article_text(_LONG, max_length=3000)
    assert out.startswith('과학기술정보통신부')
    assert not _is_extraction_failed(out)


def test_finalize_rejects_empty():
    assert _is_extraction_failed(_finalize_article_text('', 3000))
    assert _is_extraction_failed(_finalize_article_text(None, 3000))


def test_finalize_rejects_too_short():
    assert _is_extraction_failed(_finalize_article_text('짧은 본문입니다.', 3000))


def test_finalize_rejects_low_sentence_count():
    # 200자 넘지만 문장(마침표 기준)이 3개 미만 — 네비게이션/목록성 텍스트
    junk = '메뉴 홈 뉴스 스포츠 연예 ' * 20
    assert _is_extraction_failed(_finalize_article_text(junk, 3000))


def test_finalize_truncates_real_content():
    # max_length가 게이트(200)보다 커야 실제 본문 절단이 검증됨 (사소 통과 방지)
    out = _finalize_article_text(_LONG, max_length=250)
    assert len(out) == 250
    assert out.startswith('과학기술정보통신부')
    assert not _is_extraction_failed(out)


# ── _is_extraction_failed: '실패' 오탐 회귀 방지 ─────────────────────────────

def test_legit_article_with_failure_word_not_dropped():
    """'발사 실패'처럼 정상 본문에 흔한 단어가 있어도 실패로 오판하지 않는다."""
    body = _finalize_article_text(
        '누리호 3차 발사가 실패로 끝났다. ' + _LONG, max_length=3000)
    assert '실패' in body            # 본문에 단어는 남아 있고
    assert not _is_extraction_failed(body)  # 실패로 판정되지 않음


def test_sentinel_failures_detected():
    assert _is_extraction_failed(_fail("본문 수집 실패 (네트워크 오류): timeout"))
    assert _is_extraction_failed('')
    assert _is_extraction_failed('짧음')      # 100자 미만


# ── _choose_extraction ───────────────────────────────────────────────────────

def test_choose_prefers_trafilatura_when_adequate():
    traf = 'ㄱ' * _MIN_BODY_LEN
    bs4 = 'ㄴ' * (_MIN_BODY_LEN * 5)   # bs4가 더 길어도(보일러플레이트)
    assert _choose_extraction(traf, bs4) == traf  # 정밀한 trafilatura 채택


def test_choose_falls_back_when_trafilatura_short():
    traf = 'ㄱ' * 50                   # 게이트 미달
    bs4 = 'ㄴ' * 400
    assert _choose_extraction(traf, bs4) == bs4


def test_choose_both_empty():
    assert _choose_extraction('', '') == ''
    assert _choose_extraction(None, None) == ''


# ── _extract_with_bs4 폴백 분기 ─────────────────────────────────────────────

def test_bs4_extracts_article_tag():
    html = '<html><body><article><p>' + ('통신 표준 정책 뉴스 본문 문장. ' * 10) + '</p></article></body></html>'
    assert '통신 표준 정책' in _extract_with_bs4(html)


def test_bs4_paragraph_aggregation_without_article():
    # <article> 없이 긴 <p>들만 — 문단 수집 분기
    ps = ''.join(f'<p>{"통신 표준화 관련 상세 본문 문장이 충분히 깁니다. " * 3}</p>' for _ in range(3))
    html = f'<html><body><div>{ps}</div></body></html>'
    assert '통신 표준화' in _extract_with_bs4(html)


def test_bs4_empty_html_returns_empty():
    assert _extract_with_bs4('<html></html>') == ''
