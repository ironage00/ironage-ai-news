"""수집 단계 하드 정크 오버라이드 테스트 — Phase 2 키워드 오매칭 차단.

ITU(트라이애슬론)·ESPN·홈쇼핑·라디오 복귀 등, ICT 약어를 우연히 포함하지만
명백히 비ICT인 기사를 강한-ICT-마커 예외보다 우선해 수집 단계에서 제외한다.
정상 ICT(ITU-R, 방송통신위, 라디오 주파수 등)는 반드시 통과해야 한다.
"""
import pytest
from news_engine import _collect_stage_filter_reason


def _reason(title, summary=''):
    return _collect_stage_filter_reason({'title': title, 'summary': summary})


@pytest.mark.parametrize('title', [
    'Second-placed Gomez of Spain congratulates Brownlee on winning the ITU Sprint',
    'Crawley - Barnet (26 sep.) - ESPN (NL)',
    'World Triathlon Championship results',
    '그래비티 신상, 롯데홈쇼핑 첫 방송 2만병 팔려…분당 최고 주문액',
    '방송 뜸했던 이소라, 라디오 복귀…두시의 데이트 DJ 맡고 신곡도 발표',
])
def test_hard_junk_excluded_even_with_ict_acronym(title):
    """ICT 약어(ITU 등)를 포함해도 스포츠/홈쇼핑/연예 문맥이면 제외."""
    assert _reason(title) == 'hard_junk'


@pytest.mark.parametrize('title', [
    'ITU-R WP5D 6G 프레임워크 권고안 확정',
    'ITU 사무총장, AI 거버넌스 국제 협력 강조',
    '방송통신위원회, 주파수 재할당 정책 발표',
    '지상파 방송 UHD 표준 개정 논의',
    'KBS 라디오 주파수 대역 조정 검토',
    'SKT, 홈IoT 신규 서비스 출시',   # '홈'이 홈쇼핑으로 오탐되지 않아야
])
def test_legit_ict_not_flagged_as_hard_junk(title):
    """정상 ICT 뉴스는 하드 정크로 오탐되지 않아야 한다(강한 마커 예외 유지)."""
    assert _reason(title) != 'hard_junk'