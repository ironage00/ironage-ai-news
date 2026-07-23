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


# ── 2026-07-23: '전파'/'방송' 동음이의어 오탐 (전파네트워크표준단 키워드 오매칭) ──
# 실제 뉴스레터 유입 사례: 정치인 발언(김장겸 의원), 문화 확산 홍보(CJ 태권도),
# 방송사 평가 순위(방미통위) 기사가 전파네트워크표준단으로 분류·선별됨.

@pytest.mark.parametrize('title,expected_reason', [
    ('[전문] 김장겸 "공영방송, 총선 앞두고서는 더 악착같이 편파편향방송할', 'politics_partisan'),
    ("CJ, 태권도로 베트남에 'K라이프스타일' 전파", 'culture_export_promo'),
    ('방미통위, 2024 방송평가서 지상파 KBS1·종편 MBN 각각 1위', 'broadcast_industry_rating'),
    ('KBS1, 지상파 방송평가 1위…종편은 MBN 최고점', 'broadcast_industry_rating'),
])
def test_jeonpa_bangsong_homonym_false_positives_now_filtered(title, expected_reason):
    """'전파'(확산의 뜻)·'방송'(방송산업 자체) 오탐으로 전파네트워크표준단에
    잘못 유입되던 비ICT 기사가 이제 수집 단계에서 제외된다."""
    assert _reason(title) == expected_reason


@pytest.mark.parametrize('title', [
    '전파법 개정안 국회 통과, 5G 주파수 재배치 추진',
    '방송통신위, AI 기반 재난방송 시스템 표준화 추진',
    '전파진흥원, 전파자원 관리 계획 발표',
])
def test_jeonpa_compound_terms_still_pass_as_legit_ict(title):
    """'전파'가 전파법/전파진흥 등 도메인 복합어로 쓰이면 여전히 정상 통과한다
    (바레 '전파' 제거가 진짜 전파 관련 기사의 회수율을 해치지 않아야 함)."""
    assert _reason(title) is None