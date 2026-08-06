"""단 내부 뉴스레터 노출 순위(_newsletter_rank_key) 테스트.

2026-08-05: 상위 20건 컷이 Phase 2 룰 점수(제목 키워드 카운트) 순서를 그대로
물려받아, impact_level=High로 필터를 통과한 기사도 제목에 단 키워드가 한 번만
매칭되면 하위로 밀려 "추가 수집 뉴스"로 넘어가던 문제 대응. 실측 사례:
"[동북아 정세 브리핑] 미중 경쟁, 남중국해·공급망·6G로 확전" — 룰점수=1로 컷됨.
"""
from news_engine import _newsletter_rank_key


def _article(**overrides):
    base = {
        'title': '',
        'impact_level': 'Medium',
        'tta_action_item': '',
        'standardization_gap': '',
        'impact_reason': '',
        '_unit_tags': {},
    }
    base.update(overrides)
    return base


def test_critical_outranks_high_regardless_of_rule_score():
    critical = _article(impact_level='Critical', _unit_tags={1: 1})
    high = _article(impact_level='High', _unit_tags={1: 10})
    assert _newsletter_rank_key(critical, 1) > _newsletter_rank_key(high, 1)


def test_standardization_signal_breaks_tie_within_same_impact_level():
    """실측 재현 — 룰점수가 낮아도 표준화 신호가 있으면 룰점수만 높은 기사를 앞선다."""
    geopolitics_6g = _article(
        title='[동북아 정세 브리핑] 미중 경쟁, 남중국해·공급망·6G로 확전',
        impact_level='High',
        tta_action_item='2026년 ITU-R WP 5D 회의에서 6G 주파수 및 기술표준 논의에 적극 참여',
        standardization_gap='기사에서 표준화 현황 정보 미확인',
        _unit_tags={4: 1},
    )
    generic_high_rule_score = _article(
        title='SKT-KT, 5G 네트워크 장비 공동 조달',
        impact_level='High',
        _unit_tags={4: 5},
    )
    assert _newsletter_rank_key(geopolitics_6g, 4) > _newsletter_rank_key(generic_high_rule_score, 4)


def test_rule_score_is_final_tiebreaker_when_impact_and_standardization_equal():
    a = _article(impact_level='High', _unit_tags={1: 2})
    b = _article(impact_level='High', _unit_tags={1: 7})
    assert _newsletter_rank_key(b, 1) > _newsletter_rank_key(a, 1)


def test_placeholder_standardization_gap_text_not_counted_as_signal():
    """AI가 채운 기본 placeholder 문구("정보 미확인")는 실질 신호로 치지 않는다."""
    with_placeholder = _article(impact_level='High', standardization_gap='기사에서 표준화 현황 정보 미확인', _unit_tags={1: 3})
    without_gap = _article(impact_level='High', standardization_gap='', _unit_tags={1: 3})
    assert _newsletter_rank_key(with_placeholder, 1) == _newsletter_rank_key(without_gap, 1)


def test_standard_body_mention_in_title_counts_as_signal():
    with_body = _article(title='3GPP, 6G 표준화 일정 확정', impact_level='High', _unit_tags={1: 1})
    without_body = _article(title='어느 통신사 신규 요금제 출시', impact_level='High', _unit_tags={1: 1})
    assert _newsletter_rank_key(with_body, 1) > _newsletter_rank_key(without_body, 1)


def test_missing_fields_do_not_crash():
    bare = {'_unit_tags': {}}
    assert _newsletter_rank_key(bare, 1) == (0, 0, 0)


def test_unit_tags_missing_uid_falls_back_to_zero_rule_score():
    article = _article(impact_level='High', _unit_tags={2: 9})  # uid=1 not present
    assert _newsletter_rank_key(article, 1) == (2, 0, 0)
