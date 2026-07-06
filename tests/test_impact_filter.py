"""뉴스레터 중요도(영향도) 필터 테스트 — Critical/High만 게재, Medium/Low 제외.

impact_level은 심층분석의 산출물이라 '분석 전 제외'는 불가능하므로, 이 필터는
분석 후 이메일 게재 목록에서 Medium 이하를 걸러낸다(_impact_at_least).
"""
from news_engine import _impact_at_least


def test_critical_and_high_pass_default():
    assert _impact_at_least('Critical') is True
    assert _impact_at_least('High') is True


def test_medium_and_low_excluded_default():
    assert _impact_at_least('Medium') is False
    assert _impact_at_least('Low') is False


def test_case_insensitive():
    assert _impact_at_least('critical') is True
    assert _impact_at_least('HIGH') is True
    assert _impact_at_least('medium') is False


def test_unknown_treated_as_medium_excluded():
    """파싱 실패/누락 등 알 수 없는 값은 Medium으로 간주 → 기본(High) 기준에서 제외."""
    assert _impact_at_least(None) is False
    assert _impact_at_least('') is False
    assert _impact_at_least('무엇') is False


def test_min_low_disables_filter():
    """min_level='Low'면 전량 통과 — 필터 해제 롤백 경로."""
    for lv in ('Critical', 'High', 'Medium', 'Low', None, 'xxx'):
        assert _impact_at_least(lv, 'Low') is True


def test_min_critical_only_critical():
    assert _impact_at_least('Critical', 'Critical') is True
    assert _impact_at_least('High', 'Critical') is False


def test_filter_pipeline_semantics():
    """실제 사용 패턴 — 분석 리스트에서 Critical/High만 남긴다."""
    analyzed = [
        {'link': 'a', 'impact_level': 'Critical'},
        {'link': 'b', 'impact_level': 'High'},
        {'link': 'c', 'impact_level': 'Medium'},
        {'link': 'd', 'impact_level': 'Low'},
        {'link': 'e'},  # impact_level 누락
    ]
    kept = [a for a in analyzed if _impact_at_least(a.get('impact_level'), 'High')]
    assert [a['link'] for a in kept] == ['a', 'b']
