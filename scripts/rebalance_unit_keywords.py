#!/usr/bin/env python3
"""
단별 키워드 재설계 반영 스크립트.

이력:
  Fix B(2026-07-03) — 'AI'/'인공지능' 표준혁신·AI융합단 양쪽 중복으로 인한 AI 기사
  폭주, 'ITS'(지능형교통) 영어 'its' 오매칭을 진단해 1차 재설계.

  Fix C(2026-07-04) — 사용자가 제공한 4개 단의 공식 업무분장 문서를 근거로 전면
  재설계. 핵심 변경점:
    - 표준기획단: 처음에는 "표준화 전략/정책/대응전략 수립, 공식표준화기구 총괄·
      글로벌 표준 협력" 업무만 보고 전략·정책 중심 키워드를 처음부터 새로 설계했으나,
      dry-run 결과 기존 27개(Horizon Europe·ETSI·AI Act·Cyber Resilience Act·
      JTC1/3/4·SEP 등)를 지우면 배정 수가 37→1로 폭락함을 확인(과압축 재발 위험) —
      기존 목록은 그대로 두고 전략/정책 어휘 10개만 추가(합집합)로 수정.
    - 표준혁신단: 업무분장에 "인공지능, AX, 피지컬 AI 등 표준화"가 명시 — AX를
      키워드에 추가. 표준연구성과 검증·보급/확산·중소기업 지원·국제표준화 전문가·
      정보통신용어 표준화 등 업무 자체를 키워드로 보강.
    - AI융합표준단: 업무분장에 "자율주행차 국제표준 개발, Physical AI 표준화"가
      명시 — 이전 Fix B에서 '피지컬 AI'를 표준혁신단 전용으로 이관했던 것과 충돌.
      사용자 확인 결과 두 단 모두 배정(멀티 유닛 태깅)하기로 결정 — 실제로 두 단
      모두 관련 업무가 있으므로 중복 배정이 맞다. TC4/TC6, oneM2M, G3AM/QuINSA 등
      위원회 운영 실무를 반영해 키워드 보강.
    - 전파네트워크표준단: "이동통신", "전자파"(IEC), "방송"(전파방송 표준)이 업무에
      명시돼 있으나 키워드에 없었음 — 추가. 업무분장에 근거 없는 UAM/SDV는 제거
      (자율주행차 도메인은 AI융합표준단이 이미 커버).

안전장치:
  - 기본 dry-run — 변경 diff와 배정 수 시뮬레이션만 표시, 저장하지 않음
  - --confirm 플래그를 명시해야 실제 DB(unit_settings) 반영
  - keywords만 교체하고 google_alerts_rss·email_recipients 등 나머지 설정은 보존
  - 실행 전 반드시 dry-run 결과(추가/제거 diff, 배정 수 증감)를 검토할 것 —
    이 스크립트는 프로덕션 DB 접근 권한이 있는 환경에서 실행해야 한다.

사용법:
  python scripts/rebalance_unit_keywords.py            # dry-run
  python scripts/rebalance_unit_keywords.py --confirm  # 실제 반영
"""
import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news_engine import (  # noqa: E402
    NewsArticle,
    get_db_session,
    get_all_units,
    load_unit_settings,
    save_unit_settings,
    _classify_article_to_units,
)

# unit_id → 새 키워드 목록.
# 각 단의 소관은 도메인 담당이 최종 확인해야 하며, 이 목록은 업무분장 문서 기반 제안이다.
NEW_KEYWORDS = {
    # [1] 표준기획단 — 표준화 전략/정책 수립, 국내외 제도 대응, 공식표준화기구
    #     총괄 및 글로벌 표준 협력. 기존 27개(Horizon Europe·ETSI·AI Act·Cyber
    #     Resilience Act·JTC1/3/4·SEP 등 EU/국제기구 중심)가 이미 업무분장과
    #     잘 맞아 통째로 교체하면 배정 수가 37→1로 폭락함을 dry-run으로 확인
    #     (과압축 재발 위험) — 기존 27개를 보존하고 전략/정책 어휘만 보강(합집합).
    1: [
        "Horizon Europe", "호라이즌", "ETSI", "국제표준", "ICT표준", "표준화",
        "표준정책", "ICT 표준 기획", "표준화 정책", "TTA 표준", "디지털 파트너십",
        "StandICT.eu", "표준필수특허", "SEP", "피지컬AI", "과학기술정보통신부",
        "ITU", "DSIT", "디지털과학혁신부", "유럽 집행위원회", "AI Act",
        "Cyber Resilience Act", "CEN/CENELEC", "Rolling Plan for ICT Standardisation",
        "JTC 3", "JTC 4", "JTC 1",
        # 보강 (업무분장: 표준화 전략/정책/대응전략 수립)
        "ISO/IEC", "TBT 통보", "국가기술표준원", "국가표준화", "국제표준화 협력",
        "국제표준화기구", "글로벌 표준 협력", "표준화 대응전략", "표준화 로드맵", "표준화 전략",
    ],

    # [2] 표준혁신단 — 표준연구성과 검증·보급/확산, 중소기업 표준화 지원,
    #     국제표준화 전문가 선정/지원, 정보통신용어 표준화, AI/AX/피지컬AI 표준화.
    #     단독 'AI'는 제거 유지(AI융합단과의 폭주 방지) — 결합어·전문영역 위주.
    2: [
        # AI 표준화 일반 (인공지능 PG) — 업무분장 "인공지능, AX, 피지컬 AI 등 표준화"
        "AI 표준", "AI 표준화", "인공지능 표준", "AI 국제표준", "인공지능 표준화",
        # ① 기반기술: 용어·지식표현·참조구조·프레임워크
        "AI 용어", "AI 온톨로지", "지식표현", "AI 참조구조", "AI 참조모델", "AI 프레임워크",
        # ② 인공지능 모델
        "AI 모델", "인공지능 모델", "머신러닝 모델", "파운데이션 모델", "거대언어모델", "생성형 AI 모델",
        # ③ 인공지능 시스템 기술
        "AI 시스템", "인공지능 시스템", "AI 수명주기", "AI 데이터 품질", "MLOps",
        # ④ 인공지능 신뢰성
        "AI 신뢰성", "인공지능 신뢰성", "AI 안전", "AI 윤리", "AI 편향", "설명가능 AI",
        "AI 투명성", "AI 견고성", "AI 시험인증", "AI 위험관리",
        # AX (업무분장 명시)
        "AX",
        # 피지컬 AI — AI융합표준단과 공동 배정(둘 다 관련 업무 보유, 사용자 확인)
        "피지컬 AI", "피지컬AI", "Physical AI",
        # 표준연구성과 검증·보급/확산·중소기업 지원·전문가·용어 표준화
        "표준연구성과", "표준 보급", "표준 확산", "표준활용실태", "표준 자문",
        "표준구현 사업화", "중소기업 표준화", "국제표준화전문가", "정보통신용어 표준화",
        "ICT표준확산", "ICT표준특허", "표준특허", "표준성과", "시험인증",
    ],

    # [3] AI융합표준단 — AI/Data·통신망·클라우드빅데이터·IoT·정보보호·SW콘텐츠·
    #     ICT융합 표준 제개정 및 위원회(TC4/TC6) 운영, oneM2M·자율주행차·Physical AI,
    #     G3AM/QuINSA, JTC1/ITU-T 국제 협력. AI 일반 홈(AI/인공지능 유지).
    3: [
        "AI", "인공지능", "Agentic AI", "생성형 AI", "온디바이스 AI", "LLM", "AX", "AI반도체",
        "클라우드", "빅데이터", "데이터센터", "사물인터넷", "IoT", "스마트홈", "스마트헬스",
        "정보보호", "정보보안", "사이버보안", "차세대보안", "생체인식", "바이오인식",
        "AI 보안", "인공지능 보안",
        "SW", "콘텐츠", "ICT융합", "블록체인", "로봇", "드론", "AR", "VR",
        # oneM2M·자율주행차·Physical AI (업무분장 명시, 피지컬 AI는 표준혁신단과 공동 배정)
        "oneM2M", "자율주행차", "커넥티드카", "피지컬 AI", "피지컬AI", "Physical AI",
        # 표준화 포럼·사실표준화기구·위원회 운영
        "G3AM", "QuINSA", "JTC 1", "ITU-T", "CJK", "한중일 IT 협력",
    ],

    # [4] 전파네트워크표준단 — IEC 전자파, 이동통신, 전파/위성/방송, 한국ITU연구위원회/
    #     ITU-R, 3GPP. 업무분장에 없는 UAM/SDV 제거(자율주행차는 AI융합단이 커버).
    4: [
        "이동통신", "5G", "6G", "위성통신", "위성", "방송", "전파", "전자파", "주파수",
        "ITU-R", "한국ITU연구위원회", "3GPP", "AI-RAN", "AI네트워크", "Wi-Fi",
        "재난통신", "저궤도", "LBS", "C-ITS", "지능형교통", "FCC",
        "NTN", "비지상", "스펙트럼", "스타링크", "기지국", "mmWave", "밀리미터파",
    ],
}


def _diff(old: list, new: list) -> tuple:
    old_s, new_s = set(old), set(new)
    return sorted(new_s - old_s), sorted(old_s - new_s)  # (추가, 제거)


def _load_recent_titles(limit: int = 3000) -> list:
    # 최신순 정렬 — 정렬 없이 뽑으면 실행마다 다른 표본이 나와 시뮬레이션이 흔들림
    with get_db_session() as s:
        rows = (s.query(NewsArticle.title)
                 .order_by(NewsArticle.collected_at.desc())
                 .limit(limit).all())
        return [t[0] for t in rows if t[0]]


def _simulate(unit_kw_map: dict, titles: list) -> dict:
    """제목들을 주어진 키워드맵으로 분류했을 때 단별 배정 수(중복 배정 포함)."""
    counts = {uid: 0 for uid in unit_kw_map}
    for t in titles:
        for uid in _classify_article_to_units(t, unit_kw_map):
            counts[uid] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description='단별 키워드 재설계 반영')
    parser.add_argument('--confirm', action='store_true',
                        help='실제 DB 반영 (기본은 dry-run)')
    args = parser.parse_args()

    units = {u['id']: u['display_name'] for u in get_all_units()}

    # 현재 키워드 로드
    current = {uid: load_unit_settings(uid).get('keywords', []) for uid in units}
    # 새 키워드 확정 (None이면 현재 유지)
    proposed = {uid: (NEW_KEYWORDS.get(uid) if NEW_KEYWORDS.get(uid) is not None else current[uid])
                for uid in units}

    print("=" * 70)
    print("단별 키워드 재설계" + ("  [DRY-RUN]" if not args.confirm else "  [반영]"))
    print("=" * 70)
    for uid in sorted(units):
        added, removed = _diff(current[uid], proposed[uid])
        changed = bool(added or removed)
        print(f"\n[{uid}] {units[uid]}: {len(current[uid])}개 → {len(proposed[uid])}개"
              + ("" if changed else "  (변경 없음)"))
        if added:
            print(f"    + 추가: {', '.join(added)}")
        if removed:
            print(f"    - 제거: {', '.join(removed)}")

    # 배정 수 시뮬레이션 (실 DB 제목)
    print("\n" + "-" * 70)
    print("배정 수 시뮬레이션 (최근 제목 표본, 중복 배정 포함)")
    print("-" * 70)
    titles = _load_recent_titles()
    old_map = {uid: [k.lower() for k in current[uid]] for uid in units}
    new_map = {uid: [k.lower() for k in proposed[uid]] for uid in units}
    old_counts = _simulate(old_map, titles)
    new_counts = _simulate(new_map, titles)
    print(f"  {'단':<22} {'현재':>8} {'변경후':>8} {'증감':>8}")
    for uid in sorted(units):
        d = new_counts[uid] - old_counts[uid]
        print(f"  {units[uid]:<22} {old_counts[uid]:>8} {new_counts[uid]:>8} {d:>+8}")
    print(f"  (표본 {len(titles)}개 제목 기준)")

    if not args.confirm:
        print("\n[dry-run] 실제 반영하려면 --confirm 플래그를 붙여 재실행하세요.")
        return

    # 실제 저장 (keywords만 교체, 나머지 설정 보존)
    print("\n반영 중...")
    for uid in sorted(units):
        if NEW_KEYWORDS.get(uid) is None:
            continue
        cfg = load_unit_settings(uid)
        cfg['keywords'] = proposed[uid]
        ok = save_unit_settings(uid, cfg)
        print(f"  [{uid}] {units[uid]}: {'✅ 저장' if ok else '❌ 실패'}")
    print("\n완료.")


if __name__ == '__main__':
    main()
