"""섀도 계측 테스트 — _persist_score_impact_samples.

선별점수 × impact_level 상관 표본이 analysis_cache 전체(Critical~Low)에 대해
정확히 기록되는지 검증. DB는 conftest의 임시 SQLite 사용.
"""
import news_engine
from news_engine import _persist_score_impact_samples, ScoreImpactSample, get_db_session


def _clear():
    with get_db_session() as s:
        s.query(ScoreImpactSample).delete()
        s.commit()


def test_records_all_analyzed_including_medium_low():
    _clear()
    analysis_cache = {
        'a': {'impact_level': 'Critical'},
        'b': {'impact_level': 'High'},
        'c': {'impact_level': 'Medium'},
        'd': {'impact_level': 'Low'},
        'e': {},   # impact 누락 → 'Medium' 기본
    }
    sel_info = {'selected_scores': {'a': 5, 'b': 4, 'c': 2}}   # a,b,c만 선별됨
    link_unit = {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 1}

    n = _persist_score_impact_samples(analysis_cache, sel_info, link_unit)
    assert n == 5

    with get_db_session() as s:
        rows = {r.link: r for r in s.query(ScoreImpactSample).all()}
    assert len(rows) == 5
    # 선별된 것은 점수·was_selected 기록
    assert rows['a'].phase26_score == 5 and rows['a'].was_selected is True
    assert rows['b'].phase26_score == 4 and rows['b'].impact_level == 'High'
    assert rows['c'].phase26_score == 2 and rows['c'].was_selected is True
    # 미선별은 score NULL, was_selected False — 게이트가 '잘못 버릴' 후보 측정용
    assert rows['d'].phase26_score is None and rows['d'].was_selected is False
    assert rows['d'].impact_level == 'Low'
    # impact 누락은 Medium 기본
    assert rows['e'].impact_level == 'Medium'
    assert rows['e'].unit_id == 1


def test_missing_selected_scores_key_is_safe():
    _clear()
    n = _persist_score_impact_samples({'x': {'impact_level': 'High'}}, {}, {'x': 2})
    assert n == 1
    with get_db_session() as s:
        r = s.query(ScoreImpactSample).filter_by(link='x').first()
    assert r.phase26_score is None and r.was_selected is False
