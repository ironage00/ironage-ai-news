"""본문 추출 품질 게이트 테스트 (_finalize_article_text 순수 함수).

네트워크·trafilatura 실제 호출은 다루지 않는다 — 정제·게이트 로직만 검증.
"""
from news_engine import _finalize_article_text, _extract_with_bs4


_LONG = ('과학기술정보통신부는 6G 주파수 연구개발 로드맵을 발표했다. '
         '이번 계획은 민간 기업과의 협력으로 추진되며 총 1조원이 투입된다. '
         '삼성전자와 LG전자가 핵심 파트너로 참여한다. '
         '2030년 상용화를 목표로 테라헤르츠 대역 연구가 진행된다. '
         '위성 통합 기술도 주요 과제로 포함됐다.') * 2


def test_finalize_accepts_quality_body():
    out = _finalize_article_text(_LONG, max_length=3000)
    assert out.startswith('과학기술정보통신부')
    assert '실패' not in out and '없습니다' not in out


def test_finalize_rejects_empty():
    assert _finalize_article_text('', 3000) == "기사 본문을 추출하지 못했습니다."
    assert _finalize_article_text(None, 3000) == "기사 본문을 추출하지 못했습니다."


def test_finalize_rejects_too_short():
    assert _finalize_article_text('짧은 본문입니다.', 3000) == "본문이 너무 짧아 분석할 수 없습니다."


def test_finalize_rejects_low_sentence_count():
    # 200자 넘지만 문장(마침표 기준)이 3개 미만 — 네비게이션/목록성 텍스트
    junk = '메뉴 홈 뉴스 스포츠 연예 ' * 20
    assert _finalize_article_text(junk, 3000) == "본문 품질이 낮아 분석할 수 없습니다."


def test_finalize_truncates_to_max_length():
    out = _finalize_article_text(_LONG, max_length=100)
    assert len(out) <= 100


def test_bs4_extracts_article_tag():
    html = '<html><body><article>' + '<p>' + ('통신 표준 정책 뉴스 본문 문장. ' * 10) + '</p>' + '</article></body></html>'
    text = _extract_with_bs4(html)
    assert '통신 표준 정책' in text
