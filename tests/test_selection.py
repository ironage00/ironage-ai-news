"""Phase 2.6 선별 순수 함수 테스트.

대상: _parse_selection_response(응답 파싱), _apply_unit_floor(하한 보장),
_classify_article_to_units(단 분류). AI 호출·DB 쓰기는 다루지 않는다.
"""
from news_engine import (
    _parse_selection_response,
    _apply_unit_floor,
    _classify_article_to_units,
    _encode_unit_ids,
    _decode_unit_ids,
    _interleave_pools,
    run_phase26_selection,
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


def test_parse_truncated_json_returns_empty_not_garbage():
    """max_tokens로 잘린 JSON — score·사유 속 숫자를 인덱스로 오인하면 안 됨."""
    raw = '{"selections": [{"index": 0, "score": 5'
    assert _parse_selection_response(raw, max_index=10) == []


def test_parse_score_clamped_to_1_5_range():
    raw = ('{"selections": [{"index": 0, "score": 0, "reason": "a"}, '
           '{"index": 1, "score": 5, "reason": "b"}, '
           '{"index": 2, "score": 99, "reason": "c"}]}')
    out = _parse_selection_response(raw, max_index=10)
    assert [it['score'] for it in out] == [None, 5, None]


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


# ── _interleave_pools ────────────────────────────────────────────────────────

def test_interleave_no_starvation_by_large_first_pool():
    """큰 첫 풀이 상한을 독식해 뒤 단이 AI에 전달되지 않는 편향 방지."""
    pools = {1: _pool(*[f'a{i}' for i in range(100)]), 2: _pool('b0', 'b1')}
    merged = _interleave_pools(pools, cap=10)
    links = [it['link'] for it in merged]
    assert 'b0' in links and 'b1' in links
    assert len(merged) == 10


def test_interleave_dedups_shared_articles():
    shared = {'link': 's', 'title': 's'}
    pools = {1: [shared, {'link': 'a', 'title': 'a'}], 2: [shared, {'link': 'b', 'title': 'b'}]}
    merged = _interleave_pools(pools, cap=10)
    assert [it['link'] for it in merged].count('s') == 1
    assert len(merged) == 3


def test_interleave_preserves_intra_pool_order():
    pools = {1: _pool('a0', 'a1', 'a2')}
    merged = _interleave_pools(pools, cap=2)
    assert [it['link'] for it in merged] == ['a0', 'a1']


# ── _encode_unit_ids / _decode_unit_ids ──────────────────────────────────────

def test_unit_ids_roundtrip():
    assert _decode_unit_ids(_encode_unit_ids({3, 1})) == [1, 3]
    assert _encode_unit_ids({1, 2}) == ',1,2,'
    assert _encode_unit_ids(set()) == ''
    assert _decode_unit_ids('') == []
    assert _decode_unit_ids(None) == []


# ── run_phase26_selection 안전 불변식 (AI·DB 호출은 monkeypatch) ─────────────

import contextlib

import news_engine


class _FakeSession:
    """SelectionLog 기록을 흡수하는 no-op 세션."""
    def add(self, obj): pass
    def commit(self): pass
    def query(self, *a, **k): raise RuntimeError('테스트에서 DB 조회 금지')


@contextlib.contextmanager
def _fake_db_session():
    yield _FakeSession()


def _pools_with_tags():
    def art(link):
        return {'link': link, 'title': link, '_unit_tags': {1: 1}}
    return {1: [art(f'l{i}') for i in range(30)]}


def test_shadow_mode_never_alters_pools(monkeypatch):
    """섀도 모드의 핵심 계약 — 뉴스레터(풀)에 절대 영향 없음."""
    monkeypatch.setitem(news_engine.CONFIG, 'selection_mode', 'shadow')
    monkeypatch.setattr(news_engine, 'ai_select_articles',
                        lambda *a, **k: [{'index': 0, 'score': 5, 'reason': 'x'}])
    monkeypatch.setattr(news_engine, 'get_db_session', _fake_db_session)
    pools = _pools_with_tags()
    snapshot = [it['link'] for it in pools[1]]
    new_pools, info = run_phase26_selection(pools, {1: {'display': 'T'}}, 'openai')
    assert [it['link'] for it in new_pools[1]] == snapshot
    assert info['mode'] == 'shadow' and info['selected'] == 1


def test_ai_failure_keeps_original_pools(monkeypatch):
    """AI 호출 실패 시 graceful fallback — 원본 풀 유지 (과압축 재발 방지)."""
    monkeypatch.setitem(news_engine.CONFIG, 'selection_mode', 'active')
    def _boom(*a, **k): raise RuntimeError('API down')
    monkeypatch.setattr(news_engine, 'ai_select_articles', _boom)
    pools = _pools_with_tags()
    snapshot = [it['link'] for it in pools[1]]
    new_pools, info = run_phase26_selection(pools, {1: {'display': 'T'}}, 'openai')
    assert [it['link'] for it in new_pools[1]] == snapshot
    assert info['selected'] == 0


def test_active_mode_applies_floor(monkeypatch):
    """활성 모드: 선별 1개여도 하한(15)만큼 보충되어 풀이 비지 않는다."""
    monkeypatch.setitem(news_engine.CONFIG, 'selection_mode', 'active')
    monkeypatch.setitem(news_engine.CONFIG, 'selection_unit_floor', 15)
    monkeypatch.setattr(news_engine, 'ai_select_articles',
                        lambda *a, **k: [{'index': 0, 'score': 5, 'reason': 'x'}])
    monkeypatch.setattr(news_engine, 'get_db_session', _fake_db_session)
    pools = _pools_with_tags()
    new_pools, info = run_phase26_selection(pools, {1: {'display': 'T'}}, 'openai')
    assert len(new_pools[1]) == 15
    assert new_pools[1][0]['link'] == 'l0'          # 선별 기사 우선
    assert info['supplemented'] == 14


def test_off_mode_skips_everything(monkeypatch):
    monkeypatch.setitem(news_engine.CONFIG, 'selection_mode', 'off')
    called = []
    monkeypatch.setattr(news_engine, 'ai_select_articles',
                        lambda *a, **k: called.append(1))
    pools = _pools_with_tags()
    new_pools, info = run_phase26_selection(pools, {1: {'display': 'T'}}, 'openai')
    assert new_pools is pools and not called and info['candidates'] == 0


# ── _classify_article_to_units ───────────────────────────────────────────────

def test_classify_counts_keyword_matches():
    kw_map = {1: ['위성', '주파수'], 2: ['ai', '6g']}
    tags = _classify_article_to_units('저궤도 위성 주파수 정책과 6G', kw_map)
    assert tags == {1: 2, 2: 1}


def test_classify_no_match_returns_empty():
    assert _classify_article_to_units('오늘의 맛집 추천', {1: ['위성']}) == {}
