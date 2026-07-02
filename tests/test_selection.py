"""Phase 2.6 선별 순수 함수 테스트.

대상: _parse_selection_response(응답 파싱), _apply_unit_floor(하한 보장),
_classify_article_to_units(단 분류). AI 호출·DB 쓰기는 다루지 않는다.
"""
from news_engine import (
    _parse_selection_response,
    _apply_unit_floor,
    _classify_article_to_units,
)


# ── _parse_selection_response ────────────────────────────────────────────────

def test_parse_json_object_with_selections():
    raw = '{"selections": [{"index": 0, "score": 5, "reason": "FCC 규제"}, {"index": 3, "score": 2, "reason": "산업 동향"}]}'
    out = _parse_selection_response(raw, max_index=10)
    assert [it['index'] for it in out] == [0, 3]
    assert out[0]['score'] == 5
    assert out[0]['reason'] == 'FCC 규제'


def test_parse_code_fenced_json():
    raw = '```json\n{"selections": [{"index": 1, "score": 4, "reason": "3GPP"}]}\n```'
    out = _parse_selection_response(raw, max_index=5)
    assert out == [{'index': 1, 'score': 4, 'reason': '3GPP'}]


def test_parse_top_level_array():
    raw = '[{"index": 2, "score": 3, "reason": "국내 정책"}]'
    out = _parse_selection_response(raw, max_index=5)
    assert out[0]['index'] == 2


def test_parse_fallback_to_plain_numbers():
    raw = '0, 3, 7, 12'
    out = _parse_selection_response(raw, max_index=10)
    assert [it['index'] for it in out] == [0, 3, 7]  # 12는 범위 밖
    assert all(it['score'] is None for it in out)


def test_parse_out_of_range_and_duplicates_removed():
    raw = '{"selections": [{"index": 1, "score": 5, "reason": "a"}, {"index": 1, "score": 4, "reason": "b"}, {"index": 99, "score": 5, "reason": "c"}]}'
    out = _parse_selection_response(raw, max_index=10)
    assert [it['index'] for it in out] == [1]
    assert out[0]['reason'] == 'a'  # 첫 항목 유지


def test_parse_non_digit_score_becomes_none():
    raw = '{"selections": [{"index": 0, "score": "높음", "reason": "x"}]}'
    out = _parse_selection_response(raw, max_index=3)
    assert out[0]['score'] is None


def test_parse_empty_and_garbage():
    assert _parse_selection_response('', max_index=5) == []
    assert _parse_selection_response('선별할 뉴스가 없습니다.', max_index=5) == []


# ── _apply_unit_floor ────────────────────────────────────────────────────────

def _pool(*links):
    return [{'link': l, 'title': l} for l in links]


def test_floor_keeps_only_selected_when_above_floor():
    pools = {1: _pool('a', 'b', 'c', 'd')}
    new_pools, supp = _apply_unit_floor(pools, selected_links={'a', 'c', 'd'}, floor=2)
    assert [it['link'] for it in new_pools[1]] == ['a', 'c', 'd']
    assert supp == set()


def test_floor_supplements_in_original_order():
    pools = {1: _pool('a', 'b', 'c', 'd', 'e')}
    new_pools, supp = _apply_unit_floor(pools, selected_links={'d'}, floor=3)
    # 선별 d 유지 + 원래 순서(a, b)로 보충
    assert [it['link'] for it in new_pools[1]] == ['d', 'a', 'b']
    assert supp == {'a', 'b'}


def test_floor_pool_smaller_than_floor_keeps_whole_pool():
    pools = {1: _pool('a', 'b')}
    new_pools, supp = _apply_unit_floor(pools, selected_links=set(), floor=15)
    assert [it['link'] for it in new_pools[1]] == ['a', 'b']
    assert supp == {'a', 'b'}


def test_floor_zero_selection_never_empties_pool():
    """과압축(258→9) 재발 방지의 핵심 — 선별 0개여도 하한만큼 남는다."""
    pools = {1: _pool(*[f'l{i}' for i in range(30)])}
    new_pools, _ = _apply_unit_floor(pools, selected_links=set(), floor=15)
    assert len(new_pools[1]) == 15


def test_floor_multiple_units_independent():
    pools = {1: _pool('a', 'b'), 2: _pool('c', 'd', 'e')}
    new_pools, _ = _apply_unit_floor(pools, selected_links={'c'}, floor=1)
    assert [it['link'] for it in new_pools[1]] == ['a']   # 보충 1개
    assert [it['link'] for it in new_pools[2]] == ['c']   # 선별 1개로 하한 충족


# ── _classify_article_to_units ───────────────────────────────────────────────

def test_classify_counts_keyword_matches():
    kw_map = {1: ['위성', '주파수'], 2: ['ai', '6g']}
    tags = _classify_article_to_units('저궤도 위성 주파수 정책과 6G', kw_map)
    assert tags == {1: 2, 2: 1}


def test_classify_no_match_returns_empty():
    assert _classify_article_to_units('오늘의 맛집 추천', {1: ['위성']}) == {}
