"""Phase 2.6 선별 순수 함수 테스트.

대상: _parse_selection_response(응답 파싱), _apply_unit_floor(하한 보장),
_classify_article_to_units(단 분류). AI 호출·DB 쓰기는 다루지 않는다.
"""
import sys
import types

import news_engine
from news_engine import (
    _parse_selection_response,
    _apply_unit_floor,
    _classify_article_to_units,
    _encode_unit_ids,
    _decode_unit_ids,
    _interleave_pools,
    _dedup_by_embedding,
    run_phase26_selection,
    ai_select_articles,
    OPENAI_SELECTION_MODEL_DEFAULT,
    OPENAI_MODEL_DEFAULT,
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


# ── _dedup_by_embedding (Phase D2) ───────────────────────────────────────────

def _install_fake_rag(monkeypatch, vec_map):
    """rag_search._embed_texts/_cosine_similarity를 가짜로 주입.

    vec_map: {정제된_텍스트: [벡터]} — 실제 API 호출 없이 결정적으로 검증.
    """
    fake = types.ModuleType('rag_search')

    def _embed_texts(texts):
        return [vec_map[t] for t in texts]

    def _cosine_similarity(a, b):
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    fake._embed_texts = _embed_texts
    fake._cosine_similarity = _cosine_similarity
    monkeypatch.setitem(sys.modules, 'rag_search', fake)


def test_dedup_by_embedding_merges_near_duplicates(monkeypatch):
    # A와 B는 거의 같은 방향(중복), C는 직교(다른 기사)
    vecs = {'a': [1.0, 0.0], 'a2': [0.98, 0.02], 'c': [0.0, 1.0]}
    _install_fake_rag(monkeypatch, vecs)
    items = [{'title': 'a', 'link': '1'}, {'title': 'a2', 'link': '2'}, {'title': 'c', 'link': '3'}]
    result, removed = _dedup_by_embedding(items, threshold=0.70)
    assert removed == 1
    assert [r['link'] for r in result] == ['1', '3']  # 앞 기사 대표 유지, c는 별개


def test_dedup_by_embedding_keeps_distinct(monkeypatch):
    vecs = {'x': [1.0, 0.0], 'y': [0.0, 1.0]}
    _install_fake_rag(monkeypatch, vecs)
    items = [{'title': 'x', 'link': '1'}, {'title': 'y', 'link': '2'}]
    result, removed = _dedup_by_embedding(items, threshold=0.70)
    assert removed == 0 and len(result) == 2


def test_dedup_by_embedding_single_item_noop(monkeypatch):
    result, removed = _dedup_by_embedding([{'title': 'x', 'link': '1'}], threshold=0.70)
    assert removed == 0 and len(result) == 1


def test_dedup_by_embedding_graceful_on_embed_failure(monkeypatch):
    fake = types.ModuleType('rag_search')
    def _boom(texts): raise RuntimeError('API down')
    fake._embed_texts = _boom
    fake._cosine_similarity = lambda a, b: 0.0
    monkeypatch.setitem(sys.modules, 'rag_search', fake)
    items = [{'title': 'a', 'link': '1'}, {'title': 'b', 'link': '2'}]
    result, removed = _dedup_by_embedding(items, threshold=0.70)
    assert removed == 0 and result is items  # 실패 시 원본 그대로 (파이프라인 보호)


def test_dedup_by_embedding_length_mismatch_guard(monkeypatch):
    # 임베딩 개수가 입력과 다르면 조용히 원본 유지 (인덱스 어긋남 방지)
    fake = types.ModuleType('rag_search')
    fake._embed_texts = lambda texts: [[1.0, 0.0]]   # 2개 요청에 1개만 반환
    fake._cosine_similarity = lambda a, b: 0.0
    monkeypatch.setitem(sys.modules, 'rag_search', fake)
    items = [{'title': 'a', 'link': '1'}, {'title': 'b', 'link': '2'}]
    result, removed = _dedup_by_embedding(items, threshold=0.70)
    assert removed == 0 and result is items


def test_dedup_by_embedding_rag_import_unavailable(monkeypatch):
    # rag_search 모듈에 _embed_texts가 없으면 ImportError → 원본 유지
    fake = types.ModuleType('rag_search')  # 헬퍼 미정의
    monkeypatch.setitem(sys.modules, 'rag_search', fake)
    items = [{'title': 'a', 'link': '1'}, {'title': 'b', 'link': '2'}]
    result, removed = _dedup_by_embedding(items, threshold=0.70)
    assert removed == 0 and result is items


def test_dedup_by_embedding_transitive_representative_only(monkeypatch):
    """A~B, B~C 이지만 A와 C는 임계값 미만 — 대표(A)에만 비교하므로
    C는 A에 병합되지 않고 자기 대표로 남는다(greedy 표준 동작 고정)."""
    # A=[1,0], B=[0.8,0.6](A와 0.8), C=[0.2,0.98](B와 높지만 A와는 0.2)
    vecs = {'A': [1.0, 0.0], 'B': [0.8, 0.6], 'C': [0.2, 0.98]}
    _install_fake_rag(monkeypatch, vecs)
    items = [{'title': 'A', 'link': '1'}, {'title': 'B', 'link': '2'}, {'title': 'C', 'link': '3'}]
    result, removed = _dedup_by_embedding(items, threshold=0.70)
    # B는 A(0.8)에 병합, C는 A(0.2)와 미달 → 별개 유지
    assert [r['link'] for r in result] == ['1', '3']
    assert removed == 1


# ── ai_select_articles: 선별 모델 선택 (Phase B4) ────────────────────────────

class _FakeChoice:
    def __init__(self, content, finish_reason='stop'):
        self.message = type('M', (), {'content': content})
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    """model 인자를 기록만 하는 가짜 OpenAI 클라이언트."""
    def __init__(self, captured):
        self.captured = captured
        self.chat = self
        self.completions = self

    def create(self, model, **kwargs):
        self.captured.append(model)
        return _FakeResponse('{"selections": [{"index": 0, "score": 5, "reason": "x"}]}')


def test_selection_uses_mini_model_by_default(monkeypatch):
    captured = []
    monkeypatch.setattr(news_engine, 'get_ai_client', lambda name: _FakeClient(captured))
    ai_select_articles([{'title': '기사1'}], ai_model='openai', target_count=5)
    assert captured == [OPENAI_SELECTION_MODEL_DEFAULT]
    assert OPENAI_SELECTION_MODEL_DEFAULT != OPENAI_MODEL_DEFAULT  # 심층분석과 분리됐는지 확인


def test_selection_model_config_override(monkeypatch):
    captured = []
    monkeypatch.setattr(news_engine, 'get_ai_client', lambda name: _FakeClient(captured))
    monkeypatch.setitem(news_engine.CONFIG, 'selection_openai_model', 'gpt-4o')
    ai_select_articles([{'title': '기사1'}], ai_model='openai', target_count=5)
    assert captured == ['gpt-4o']  # 설정으로 즉시 롤백 가능
