#!/usr/bin/env python3
"""
단별 키워드 재설계 반영 스크립트 (Fix B).

진단(대화 기록):
  - 'AI'/'인공지능'이 표준혁신단·AI융합단 양쪽에 있어 AI 기사가 두 단에 폭주
  - 'ITS'(지능형교통)가 영어 단어 'its'와 철자 동일 → 단어 경계로도 오매칭
  - 표준기획·전파네트워크단은 후보 기근

방향(사용자 확정):
  - AI융합단 = AI 일반 홈 (AI/인공지능 유지)
  - 표준혁신단 = 피지컬 AI·AI 신뢰성 등 특화 (단독 AI 제거)
  - 'ITS' → 'C-ITS'/'지능형교통'으로 교체

안전장치:
  - 기본 dry-run — 변경 diff와 배정 수 시뮬레이션만 표시, 저장하지 않음
  - --confirm 플래그를 명시해야 실제 DB(unit_settings) 반영
  - keywords만 교체하고 google_alerts_rss·email_recipients 등 나머지 설정은 보존

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
# 각 단의 소관은 도메인 담당이 최종 확인해야 하며, 이 목록은 진단 기반 제안 초안이다.
NEW_KEYWORDS = {
    # [1] 표준기획단 — 정책·국제기구 중심으로 이미 균형. 'ITS' 없음. 유지(변경 없음).
    1: None,  # None = 변경하지 않음

    # [2] 표준혁신단 — 단독 'AI' 제거(폭주 원인). 인공지능 PG 4대 소관 영역
    #     (기반기술·모델·시스템·신뢰성) 결합어로 관련 기사를 넓히되 일반 'AI 발표'는 배제.
    2: [
        # AI 표준화 일반 (인공지능 PG)
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
        # 피지컬 AI (표준혁신단 특화)
        "피지컬 AI", "피지컬AI",
        # 표준화 프로세스
        "ICT표준확산", "ICT표준특허", "표준특허", "기업지원", "표준성과", "표준전문가", "시험인증",
    ],

    # [3] AI융합단 — AI 일반 홈. 'AI'/'인공지능' 유지, '피지컬 AI'는 표준혁신단으로 이관(제거).
    3: [
        "AI", "인공지능", "Agentic AI", "생성형 AI", "온디바이스 AI", "LLM", "AX", "AI반도체",
        "정보보호", "정보보안", "차세대보안", "AI 보안", "생체인식", "디지털신원", "AI신뢰 안전",
        "빅데이터", "클라우드", "데이터센터", "블록체인", "로봇", "드론", "UAM", "양자통신",
        "하이퍼인터커넥트", "IoT", "스마트홈", "스마트헬스", "AR", "VR", "JTC 1", "ITU-T",
        "CJK", "한중일 IT 협력",
    ],

    # [4] 전파네트워크단 — 'ITS' 교체(영어 its 충돌) + 후보 보강
    4: [
        "위성통신", "6G", "5g", "주파수", "AI-RAN", "AI네트워크", "ITU-R", "전파", "Wi-Fi",
        "재난통신", "저궤도", "LBS", "C-ITS", "지능형교통", "3GPP", "FCC", "UAM", "SDV",
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
    parser = argparse.ArgumentParser(description='단별 키워드 재설계 반영 (Fix B)')
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
    print("단별 키워드 재설계 (Fix B)" + ("  [DRY-RUN]" if not args.confirm else "  [반영]"))
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
