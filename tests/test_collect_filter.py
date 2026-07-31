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


# ── 2026-07-27: 방송평가 필터가 '방송통신위원회' 정식 명칭에 우회당하던 버그 ──
# 실측 재현: "방송평가" 기사는 감독기관 정식명칭 "방송통신위원회"를 거의 항상
# 인용하는데, 그 안의 '통신'이 바레 강한 마커라 즉시 조기 반환(None)돼 07-23에
# 추가한 politics_partisan/broadcast_industry_rating/culture_export_promo가
# 아예 검사되지 않았음(전파네트워크표준단 풀이 07-24 이후 계속 붕괴한 원인 중 하나).
# 우선순위 비ICT 패턴(_PRIORITY_NON_ICT_PATTERNS)으로 승격해 하드 정크와 동급으로
# 강한 마커보다 먼저 판정하도록 수정.

@pytest.mark.parametrize('title,summary,expected_reason', [
    ('TBN 교통방송, 방송평가 9년 연속 1위',
     '방송통신위원회가 실시한 2024년도 방송평가에서 라디오 부문 1위를 차지했다',
     'broadcast_industry_rating'),
    ('KBS1, 지상파 방송평가 1위',
     '방송통신위원회 발표에 따르면 종합편성채널 중 MBN이 최고점을 받았다',
     'broadcast_industry_rating'),
])
def test_broadcast_rating_not_bypassed_by_commission_full_name(title, summary, expected_reason):
    """summary에 '방송통신위원회'(강한 마커 '통신' 포함)가 있어도 방송평가
    비ICT 판정이 강한 마커 예외에 우회당하지 않는다(우선순위 패턴으로 승격)."""
    assert _reason(title, summary) == expected_reason


@pytest.mark.parametrize('title', [
    'SKT-KT, 5G 통신망 공동 구축 협력 발표',
    '방송통신위원회, 5G 주파수 재할당 정책 발표',
    '통신 3사 요금제 개편, 데이터 무제한 확대',
    '과기정통부-방송통신위, AI 기반 재난방송 표준화 공동 추진',
])
def test_broadcast_priority_patterns_dont_catch_legit_telecom(title):
    """우선순위 패턴 승격이 '방송통신위원회'를 언급하는 정상 통신·표준 기사까지
    걸러내지 않아야 한다(politics_partisan/broadcast_rating/culture_export_promo
    문구가 실제로 없으면 통과)."""
    assert _reason(title) is None


# ── 2026-07-28: 시상식 은유·제품 마케팅·군사 용어 커버리지 공백/동음이의어 ──
# 사용자가 실제 뉴스레터 후보에서 발견한 4건. 그 중 2건('주파수'가 시상식
# 화제성 은유, '전파인증'이 제품 출시 마케팅 부속 정보로 쓰인 경우)은 강한
# 마커와 충돌해 우선순위 패턴으로 승격 필요했고, 나머지 2건은 순수 커버리지
# 공백(강한 마커 없음, 기존 카테고리에 매칭 문구 부재)이었다.

@pytest.mark.parametrize('title,expected_reason', [
    ('"저런 옷입고 방송?" 화제의 기상캐스터 누구', 'culture_entertainment'),
    ('삼성, 갤럭시 탭 S12·S26 FE 출격 임박…국내 전파인증 완료', 'product_launch_hype'),
    ("[제5회 BSA] '꿀잼' 송신한 다섯 주파수…'청룡 안테나'가 향할 작품은?", 'entertainment_metaphor'),
    ('이란 방송 "이라크 서부서 미군 드론 격추"', 'geopolitics_trade'),
])
def test_20260728_reported_false_negatives_now_filtered(title, expected_reason):
    """기상캐스터 가십·제품 마케팅·시상식 은유·군사 드론 보도가 이제 수집
    단계에서 정확히 제외된다."""
    assert _reason(title) == expected_reason


@pytest.mark.parametrize('title', [
    '국립전파연구원, 전파인증 제도 개편…규제 완화',
    'SK텔레콤, 6G 주파수 대역 실증 성공',
    'ITU-R, 6G 표준 주파수 대역 논의 착수',
    'KBS, 지상파 UHD 안테나 송출 방식 개선',
])
def test_entertainment_and_product_priority_patterns_dont_catch_legit_ict(title):
    """entertainment_metaphor/product_launch_hype 승격이 진짜 전파·주파수·
    안테나 정책/기술 기사까지 걸러내지 않아야 한다."""
    assert _reason(title) is None


# ── 2026-07-31: 라이브커머스 매출 홍보·K팝 음악방송 순위 커버리지 공백 ────────
# 사용자가 뉴스레터 후보에서 발견해 신고. 둘 다 강한 마커 충돌이 아니라
# 순수 커버리지 공백('방송'은 강한 마커가 아니라 다른 검사가 아예 안 걸림).

@pytest.mark.parametrize('title,expected_reason', [
    ("LF몰, 한여름 '역시즌 세일' 적중… 라이브 방송 역대 최고 매출 달성", 'marketing_promo'),
    ("제니, '레스 댄 어 러버'로 '엠카' 1위⋯방송 출연 없이 음악방송 1위", 'culture_entertainment'),
])
def test_20260731_reported_false_negatives_now_filtered(title, expected_reason):
    """라이브커머스 매출 홍보·K팝 음악방송 순위 기사가 이제 수집 단계에서
    정확히 제외된다."""
    assert _reason(title) == expected_reason


@pytest.mark.parametrize('title', [
    'SK텔레콤, 라이브 커머스 플랫폼 T딜 매출 두 배 성장',
    '네이버, AI 기반 라이브 커머스 추천 시스템 고도화',
])
def test_live_commerce_marketing_pattern_requires_bangsong_not_commerce(title):
    """'라이브 방송'(마케팅 홍보성 표현)만 잡고 '라이브 커머스'(플랫폼 기술
    기사에 흔한 표현)는 건드리지 않아야 한다."""
    assert _reason(title) is None