from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd

from search import clean_text, parse_keywords


KEYWORD_FIELDS = {
    "key_technologies": "기술",
    "standards_keywords": "표준",
    "related_companies": "기업",
    "target_countries": "국가",
}

IMPACT_TERMS = [
    "표준",
    "표준화",
    "ITU",
    "3GPP",
    "IEEE",
    "ETSI",
    "6G",
    "AI-RAN",
    "NTN",
    "위성",
    "보안",
    "규제",
    "정책",
    "주파수",
    "망",
]

URGENCY_TERMS = [
    "발표",
    "상용화",
    "출시",
    "승인",
    "규제",
    "제재",
    "보안",
    "긴급",
    "경쟁",
    "투자",
    "협력",
]

ICT_TERMS = [
    "ICT",
    "통신",
    "이동통신",
    "무선",
    "네트워크",
    "망",
    "주파수",
    "전파",
    "5G",
    "6G",
    "B5G",
    "AI",
    "인공지능",
    "AI-RAN",
    "오픈랜",
    "O-RAN",
    "RAN",
    "NTN",
    "위성",
    "위성통신",
    "양자",
    "양자통신",
    "보안",
    "사이버",
    "클라우드",
    "데이터센터",
    "반도체",
    "디스플레이",
    "IoT",
    "사물인터넷",
    "로봇",
    "자율주행",
    "스마트",
    "표준",
    "표준화",
    "ITU",
    "3GPP",
    "IEEE",
    "ETSI",
    "MPEG",
    "Wi-Fi",
    "와이파이",
    "블루투스",
    "UAM",
    "드론",
    "메타버스",
    "XR",
    "AR",
    "VR",
]

FOCUS_ICT_TERMS = [
    "통신",
    "이동통신",
    "네트워크",
    "주파수",
    "전파",
    "5G",
    "6G",
    "B5G",
    "AI-RAN",
    "오픈랜",
    "O-RAN",
    "NTN",
    "위성통신",
    "양자통신",
    "보안",
    "사이버",
    "표준",
    "표준화",
    "ITU",
    "3GPP",
    "IEEE",
    "ETSI",
]

NON_ICT_TERMS = [
    "선거",
    "대선",
    "총선",
    "후보",
    "여론조사",
    "부동산",
    "아파트",
    "재건축",
    "분양",
    "맛집",
    "연예",
    "스포츠",
    "야구",
    "축구",
    "주가",
    "증시",
    "공약",
    "사설",
    "횡령",
    "배임",
    "오너",
    "굿즈",
    "캐릭터",
    "협찬",
]

TITLE_ICT_TERMS = FOCUS_ICT_TERMS + [
    "ICT",
    "AI",
    "인공지능",
    "양자",
    "위성",
    "인공위성",
    "반도체",
    "클라우드",
    "데이터센터",
    "로봇",
    "자율주행",
    "디스플레이",
    "보안",
    "해킹",
    "satellite",
    "direct-to-device",
    "standards-based",
    "standard",
    "telecom",
    "wireless",
    "network",
    "cyber",
    "security",
    "quantum",
    "semiconductor",
]

TITLE_STRONG_ICT_TERMS = FOCUS_ICT_TERMS + [
    "ICT",
    "인공지능",
    "위성",
    "인공위성",
    "반도체",
    "클라우드",
    "데이터센터",
    "로봇",
    "자율주행",
    "디스플레이",
    "해킹",
    "satellite",
    "direct-to-device",
    "standards-based",
    "standard",
    "telecom",
    "wireless",
    "network",
    "cyber",
    "security",
    "quantum",
    "semiconductor",
]

TITLE_LOW_VALUE_TERMS = [
    "선거",
    "대선",
    "총선",
    "여론조사",
    "부동산",
    "아파트",
    "재건축",
    "분양",
    "사설",
    "공약",
    "주가",
    "증시",
    "횡령",
    "배임",
    "오너",
    "굿즈",
    "춘식이",
    "증권",
    "주식",
    "리서치",
    "리포트 발간",
    "회담",
    "종전협상",
    "이란",
    "대만",
    "트럼프",
    "서울시장",
    "오세훈",
    "후보",
    "금융권",
    "핀테크",
    "항암",
    "신약",
    "임플란트",
    "화장품",
    "발효",
    "물류",
    "요금제",
    "번역",
    "리테일",
    "retailer",
    "goods",
    "daiso",
    "retail",
    "농축업",
    "농업",
    "도축",
    "오이",
    "딸기",
]

TITLE_ALWAYS_EXCLUDE_TERMS = [
    "양자 토론",
]

AI_TITLE_CONTEXT_TERMS = [
    "표준",
    "표준화",
    "국제표준",
    "인증",
    "보안",
    "공격",
    "사이버",
    "해킹",
    "반도체",
    "데이터센터",
    "클라우드",
    "통신",
    "네트워크",
    "망",
    "관제",
    "주파수",
    "5G",
    "6G",
    "KT",
    "LG유플러스",
    "LGU+",
    "SK텔레콤",
    "SKT",
    "NHN",
    "AX",
]


def normalize_datetime(value: Any) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.tz_convert(None)
        return ts
    except Exception:
        return None


def article_date(row: pd.Series) -> pd.Timestamp | None:
    return normalize_datetime(row.get("published")) or normalize_datetime(row.get("collected_at"))


def keyword_items(row: pd.Series) -> list[tuple[str, str]]:
    data = parse_keywords(row.get("extracted_keywords"))
    items: list[tuple[str, str]] = []
    for field, label in KEYWORD_FIELDS.items():
        value = data.get(field, [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            continue
        for raw in value:
            name = clean_text(raw, 80)
            if name:
                items.append((name, label))
    return list(dict.fromkeys(items))


def _keyword_counter(df: pd.DataFrame) -> Counter[tuple[str, str]]:
    counter: Counter[tuple[str, str]] = Counter()
    if df.empty:
        return counter
    for _, row in df.iterrows():
        for item in keyword_items(row):
            counter[item] += 1
    return counter


def split_recent_baseline(df: pd.DataFrame, recent_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df, df
    cutoff = pd.Timestamp(datetime.now() - timedelta(days=recent_days))
    dated = df.copy()
    dated["_radar_date"] = dated.apply(article_date, axis=1)
    recent = dated[dated["_radar_date"].notna() & (dated["_radar_date"] >= cutoff)].copy()
    baseline = dated[dated["_radar_date"].notna() & (dated["_radar_date"] < cutoff)].copy()
    return recent.drop(columns=["_radar_date"], errors="ignore"), baseline.drop(columns=["_radar_date"], errors="ignore")


def trending_keywords(recent: pd.DataFrame, baseline: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    recent_counts = _keyword_counter(recent)
    baseline_counts = _keyword_counter(baseline)
    rows = []
    for (keyword, category), count in recent_counts.items():
        base = baseline_counts.get((keyword, category), 0)
        growth = count - base
        ratio = count / max(base, 1)
        score = (count * 2.0) + max(growth, 0) + math.log1p(ratio)
        rows.append(
            {
                "키워드": keyword,
                "구분": category,
                "최근": count,
                "기준기간": base,
                "증가": growth,
                "레이더점수": round(score, 2),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["키워드", "구분", "최근", "기준기간", "증가", "레이더점수"])
    return pd.DataFrame(rows).sort_values(["레이더점수", "최근"], ascending=False).head(limit)


def new_entities(recent: pd.DataFrame, baseline: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    recent_counts = _keyword_counter(recent)
    baseline_keys = set(_keyword_counter(baseline))
    rows = [
        {"엔티티": keyword, "구분": category, "최근등장": count}
        for (keyword, category), count in recent_counts.items()
        if (keyword, category) not in baseline_keys
    ]
    if not rows:
        return pd.DataFrame(columns=["엔티티", "구분", "최근등장"])
    return pd.DataFrame(rows).sort_values(["최근등장", "엔티티"], ascending=[False, True]).head(limit)


def _text_blob(row: pd.Series) -> str:
    return " ".join(
        clean_text(row.get(col), 1200)
        for col in ["title", "content", "analysis_result", "extracted_keywords", "source"]
    )


def _term_hits(text: str, terms: Iterable[str]) -> int:
    lower = text.lower()
    hits = 0
    for term in terms:
        term_value = str(term).strip()
        if not term_value:
            continue
        if re.fullmatch(r"[A-Za-z0-9]{1,3}", term_value):
            pattern = rf"(?<![A-Za-z0-9]){re.escape(term_value)}(?![A-Za-z0-9])"
            if re.search(pattern, text, flags=re.IGNORECASE):
                hits += 1
        elif term_value.lower() in lower:
            hits += 1
    return hits


def is_home_title_relevant(title: Any) -> bool:
    clean_title = clean_text(title, 300)
    if _term_hits(clean_title, TITLE_ALWAYS_EXCLUDE_TERMS):
        return False
    if _term_hits(clean_title, TITLE_LOW_VALUE_TERMS) and not _term_hits(clean_title, TITLE_STRONG_ICT_TERMS):
        return False
    if _term_hits(clean_title, TITLE_STRONG_ICT_TERMS):
        return True
    return _term_hits(clean_title, ["AI"]) > 0 and _term_hits(clean_title, AI_TITLE_CONTEXT_TERMS) > 0


def ict_relevance_score(row: pd.Series) -> int:
    title = clean_text(row.get("title"), 300)
    if not is_home_title_relevant(title):
        return -10
    text = _text_blob(row)
    focus_hits = _term_hits(text, FOCUS_ICT_TERMS)
    score = focus_hits * 2
    score += _term_hits(text, ICT_TERMS)
    score += _term_hits(text, IMPACT_TERMS)
    for _, category in keyword_items(row):
        if category in {"기술", "표준"}:
            score += 2
        elif category == "기업":
            score += 1
    non_ict_hits = _term_hits(text, NON_ICT_TERMS)
    if non_ict_hits:
        score -= non_ict_hits if focus_hits else non_ict_hits * 4
    return score


def filter_ict_articles(df: pd.DataFrame, min_score: int = 3) -> pd.DataFrame:
    if df.empty:
        return df
    scored = df.copy()
    scored["_ict_score"] = scored.apply(ict_relevance_score, axis=1)
    filtered = scored[scored["_ict_score"] >= min_score].copy()
    return filtered.drop(columns=["_ict_score"], errors="ignore")


def filter_home_articles(df: pd.DataFrame, min_score: int = 3) -> pd.DataFrame:
    filtered = filter_ict_articles(df, min_score=min_score)
    if filtered.empty:
        return filtered
    title_mask = filtered["title"].apply(is_home_title_relevant)
    focused = filtered[title_mask].copy()
    return focused if not focused.empty else filtered


IMPACT_LEVEL_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "": 0}


# T0 실데이터(2,550건 90일 샘플) 기반 정규화 — 같은 대상의 표기 분산을 통합한다.
COUNTRY_NORMALIZE = {
    "대한민국": "한국", "Korea": "한국", "South Korea": "한국",
    "United States": "미국", "USA": "미국", "US": "미국",
    "China": "중국", "中国": "중국",
    "Japan": "일본",
    "유럽": "유럽연합", "EU": "유럽연합",
    "Iran": "이란",
    "India": "인도",
    "UK": "영국", "United Kingdom": "영국",
}

COMPANY_NORMALIZE = {
    "NVIDIA": "엔비디아", "Nvidia": "엔비디아",
    "Microsoft": "마이크로소프트",
    "Anthropic": "앤트로픽",
    "오픈AI": "OpenAI",
    "Google": "구글",
    "Apple": "애플",
    "Samsung": "삼성전자", "Samsung Electronics": "삼성전자",
    "현대차": "현대자동차", "현대차그룹": "현대자동차",
    "Meta": "메타", "Amazon": "아마존",
}


def _entity_counts(df: pd.DataFrame, target_label: str, normalize: dict[str, str]) -> pd.DataFrame:
    """keyword_items() 재사용 — 특정 구분(국가/기업)만 정규화 후 빈도 집계하는 순수 헬퍼.
    DataFrame을 직접 받아 테스트 가능 (engine·cache 의존 없음)."""
    if df.empty:
        return pd.DataFrame(columns=["name", "count"])
    counter: Counter[str] = Counter()
    for _, row in df.iterrows():
        for name, label in keyword_items(row):  # str→list 가드는 keyword_items 내부 처리
            if label == target_label:
                counter[normalize.get(name, name)] += 1
    if not counter:
        return pd.DataFrame(columns=["name", "count"])
    return (
        pd.DataFrame(counter.items(), columns=["name", "count"])
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )


def country_counts(df: pd.DataFrame) -> pd.DataFrame:
    """국가별 기사 수 (순수 헬퍼). 반환 컬럼: country, count."""
    return _entity_counts(df, "국가", COUNTRY_NORMALIZE).rename(columns={"name": "country"})


# 기술영역 정의 — key_technologies 자유 키워드를 표준 영역으로 버케팅 (동의어 포함)
TECH_AREAS: dict[str, list[str]] = {
    "6G": ["6g", "imt-2030"],
    "5G": ["5g"],
    "AI": ["ai", "인공지능", "llm", "생성형", "머신러닝", "딥러닝"],
    "위성통신": ["위성", "ntn", "스타링크", "starlink", "저궤도", "leo"],
    "사이버보안": ["보안", "사이버", "security", "암호", "해킹"],
    "반도체": ["반도체", "칩", "semiconductor", "gan", "파운드리"],
    "양자": ["양자", "quantum"],
    "데이터센터": ["데이터센터", "데이터 센터", "datacenter", "data center"],
    "자율주행": ["자율주행", "sdv", "커넥티드카", "자율주행차"],
    "네트워크": ["o-ran", "ran", "네트워크 슬라이싱", "코어망", "전송망"],
}


def article_tech_areas(row: pd.Series, tech_areas: dict[str, list[str]] | None = None) -> set[str]:
    """기사 1건이 어떤 기술영역을 다루는지 (key_technologies 키워드 → 영역 버킷)."""
    tech_areas = tech_areas or TECH_AREAS
    techs = [name.lower() for name, label in keyword_items(row) if label == "기술"]
    areas: set[str] = set()
    for area, kws in tech_areas.items():
        if any(any(kw in t for kw in kws) for t in techs):
            areas.add(area)
    return areas


def entity_tech_matrix(
    df: pd.DataFrame,
    entity_label: str,
    normalize: dict[str, str],
    tech_areas: dict[str, list[str]] | None = None,
    top_entities: int = 10,
) -> pd.DataFrame:
    """엔티티(국가/기업) × 기술영역 교차표. 셀 = 해당 영역을 다룬 기사 수.
    행=엔티티(총합 내림차순 상위 N), 열=기술영역. 빈 입력이면 빈 DataFrame."""
    tech_areas = tech_areas or TECH_AREAS
    if df.empty:
        return pd.DataFrame()
    pairs: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        items = keyword_items(row)
        ents = {normalize.get(n, n) for n, l in items if l == entity_label}
        if not ents:
            continue
        areas = article_tech_areas(row, tech_areas)
        for e in ents:
            for a in areas:
                pairs.append((e, a))
    if not pairs:
        return pd.DataFrame()
    m = pd.DataFrame(pairs, columns=["entity", "area"])
    pivot = m.groupby(["entity", "area"]).size().unstack(fill_value=0)
    pivot = pivot.reindex(columns=list(tech_areas.keys()), fill_value=0)
    pivot["__total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("__total", ascending=False).head(top_entities).drop(columns="__total")
    return pivot


def entity_detail(
    df: pd.DataFrame,
    entity_label: str,
    entity_name: str,
    normalize: dict[str, str],
    tech_areas: dict[str, list[str]] | None = None,
) -> dict:
    """특정 국가/기업의 상세: 기사 수, 집중 기술영역 top3, 관련 엔티티, 대표 기사 링크."""
    tech_areas = tech_areas or TECH_AREAS
    area_counter: Counter[str] = Counter()
    related_company: Counter[str] = Counter()
    related_country: Counter[str] = Counter()
    articles: list[dict] = []
    for _, row in df.iterrows():
        items = keyword_items(row)
        ents = {normalize.get(n, n) for n, l in items if l == entity_label}
        if entity_name not in ents:
            continue
        for a in article_tech_areas(row, tech_areas):
            area_counter[a] += 1
        for n, l in items:
            if l == "기업":
                related_company[COMPANY_NORMALIZE.get(n, n)] += 1
            elif l == "국가":
                cc = COUNTRY_NORMALIZE.get(n, n)
                if cc != entity_name:
                    related_country[cc] += 1
        articles.append({
            "title": clean_text(row.get("title"), 120),
            "link": row.get("link", ""),
            "source": clean_text(row.get("source"), 40),
            "date": article_date(row),
        })
    return {
        "entity": entity_name,
        "article_count": len(articles),
        "top_areas": [a for a, _ in area_counter.most_common(4)],
        "top_companies": [c for c, _ in related_company.most_common(5)],
        "top_countries": [c for c, _ in related_country.most_common(5)],
        "articles": sorted(articles, key=lambda x: (x["date"] is None, x["date"]), reverse=True)[:8],
    }


def entity_trend(
    recent_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    entity_label: str,
    normalize: dict[str, str],
    limit: int = 5,
) -> pd.DataFrame:
    """급부상 엔티티 — 최근 기간 기사 수와 기준기간 대비 증가. 반환: name, recent, baseline, growth."""
    def counts(df: pd.DataFrame) -> Counter:
        c: Counter[str] = Counter()
        if df.empty:
            return c
        for _, row in df.iterrows():
            for n, l in keyword_items(row):
                if l == entity_label:
                    c[normalize.get(n, n)] += 1
        return c

    rc, bc = counts(recent_df), counts(baseline_df)
    rows = [
        {"name": name, "recent": cnt, "baseline": bc.get(name, 0), "growth": cnt - bc.get(name, 0)}
        for name, cnt in rc.items()
    ]
    if not rows:
        return pd.DataFrame(columns=["name", "recent", "baseline", "growth"])
    return (
        pd.DataFrame(rows)
        .sort_values(["growth", "recent"], ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )


def cluster_counts(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    """K-means 클러스터(cluster_label)별 기사 수 (순수 헬퍼).
    cluster_articles.py 배치가 채운 cluster_id/cluster_label 사용.
    컬럼이 없거나 비면 빈 DataFrame. 반환: cluster, count."""
    if df.empty or "cluster_label" not in df.columns:
        return pd.DataFrame(columns=["cluster", "count"])
    labeled = df[df["cluster_label"].notna() & (df["cluster_label"].astype(str).str.strip() != "")]
    if labeled.empty:
        return pd.DataFrame(columns=["cluster", "count"])
    result = (
        labeled["cluster_label"].astype(str)
        .value_counts()
        .reset_index()
    )
    result.columns = ["cluster", "count"]
    return result.head(top_n) if top_n else result


def cluster_detail(df: pd.DataFrame, top_n_clusters: int = 8) -> list[dict]:
    """각 클러스터(cluster_label)별 상세 — 근거 기사 묶음 카드용 (순수 헬퍼).
    반환 리스트 항목: label, count, sources, technologies, companies, countries,
    standards, articles. cluster_label 컬럼 없으면 빈 리스트."""
    if df.empty or "cluster_label" not in df.columns:
        return []
    labeled = df[df["cluster_label"].notna() & (df["cluster_label"].astype(str).str.strip() != "")]
    if labeled.empty:
        return []
    order = labeled["cluster_label"].astype(str).value_counts().head(top_n_clusters).index.tolist()
    details: list[dict] = []
    for label in order:
        grp = labeled[labeled["cluster_label"].astype(str) == label]
        sources: Counter[str] = Counter()
        techs: Counter[str] = Counter()
        companies: Counter[str] = Counter()
        countries: Counter[str] = Counter()
        standards: Counter[str] = Counter()
        articles: list[dict] = []
        for _, row in grp.iterrows():
            src = clean_text(row.get("source"), 40)
            if src:
                sources[src] += 1
            for name, lab in keyword_items(row):
                if lab == "기술":
                    techs[name] += 1
                elif lab == "기업":
                    companies[COMPANY_NORMALIZE.get(name, name)] += 1
                elif lab == "국가":
                    countries[COUNTRY_NORMALIZE.get(name, name)] += 1
                elif lab == "표준":
                    standards[name] += 1
            gap = parse_impact(row).get("standardization_gap", "")
            if gap and "미확인" not in gap:
                standards[gap[:60]] += 1
            articles.append({
                "title": clean_text(row.get("title"), 120),
                "link": row.get("link", ""),
                "source": src,
                "date": article_date(row),
            })
        details.append({
            "label": label,
            "count": len(grp),
            "sources": [s for s, _ in sources.most_common(3)],
            "technologies": [t for t, _ in techs.most_common(5)],
            "companies": [c for c, _ in companies.most_common(4)],
            "countries": [c for c, _ in countries.most_common(4)],
            "standards": [s for s, _ in standards.most_common(2)],
            "articles": sorted(articles, key=lambda x: (x["date"] is None, x["date"]), reverse=True)[:6],
        })
    return details


def issue_timeline(df: pd.DataFrame, top_n: int = 8, max_tech_per_article: int = 3) -> pd.DataFrame:
    """기술 키워드(key_technologies)의 주차별 등장 빈도 + 단계 분류 (순수 헬퍼).
    '이슈 식별자'는 key_technologies 사용 (가장 안정적).
    반환: technology, week, count + 최신 주차 기준 stage(급등/소강/지속).
    빈 입력이면 빈 DataFrame."""
    if df.empty:
        return pd.DataFrame(columns=["technology", "week", "count", "stage"])
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        date = article_date(row)
        if date is None:
            continue
        week = pd.Timestamp(date).to_period("W").start_time
        techs = [name for name, label in keyword_items(row) if label == "기술"][:max_tech_per_article]
        for name in techs:
            rows.append({"technology": name, "week": week})
    if not rows:
        return pd.DataFrame(columns=["technology", "week", "count", "stage"])

    raw = pd.DataFrame(rows)
    # 상위 기술만 (전체 빈도 기준)
    top_terms = raw["technology"].value_counts().head(top_n).index.tolist()
    raw = raw[raw["technology"].isin(top_terms)]
    weekly = raw.groupby(["technology", "week"]).size().reset_index(name="count")

    # 단계 분류: 기술별 평균 대비 최신 주차 빈도
    stages: dict[str, str] = {}
    for tech, grp in weekly.groupby("technology"):
        grp_sorted = grp.sort_values("week")
        recent = grp_sorted.iloc[-1]["count"]
        avg = grp_sorted["count"].mean()
        if recent > avg * 1.5:
            stages[tech] = "급등"
        elif recent < avg * 0.5:
            stages[tech] = "소강"
        else:
            stages[tech] = "지속"
    weekly["stage"] = weekly["technology"].map(stages)
    return weekly.sort_values(["technology", "week"]).reset_index(drop=True)


def company_counts(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    """기업별 기사 수 (순수 헬퍼). 반환 컬럼: company, count."""
    result = _entity_counts(df, "기업", COMPANY_NORMALIZE).rename(columns={"name": "company"})
    return result.head(top_n) if top_n else result


def parse_impact(row: pd.Series) -> dict:
    """extracted_keywords에서 영향도·TTA 대응 필드 추출.
    AI 프롬프트가 채우는 impact_level / tta_action_item / standardization_gap.
    필드가 없거나 JSON이 비면 빈 문자열 반환 (침묵 실패 방지용 명시 기본값)."""
    data = parse_keywords(row.get("extracted_keywords"))
    return {
        "impact_level": clean_text(data.get("impact_level", ""), 20),
        "impact_reason": clean_text(data.get("impact_reason", ""), 400),
        "tta_action_item": clean_text(data.get("tta_action_item", ""), 400),
        "standardization_gap": clean_text(data.get("standardization_gap", ""), 400),
    }


def issue_scores(row: pd.Series) -> tuple[int, int]:
    text = _text_blob(row)
    impact = 1
    urgency = 1
    impact += min(_term_hits(text, IMPACT_TERMS), 5)
    urgency += min(_term_hits(text, URGENCY_TERMS), 4)
    try:
        impact += min(int(float(row.get("quality_score") or 0) // 2), 3)
    except Exception:
        pass
    published = article_date(row)
    if published is not None:
        age_days = max((pd.Timestamp(datetime.now()) - published).days, 0)
        if age_days <= 2:
            urgency += 3
        elif age_days <= 7:
            urgency += 2
        elif age_days <= 14:
            urgency += 1
    entities = keyword_items(row)
    impact += min(len(entities) // 3, 2)
    return min(impact, 10), min(urgency, 10)


# ─────────────────────── 5축 선정 기준 (Executive Brief) ───────────────────────
# 각 축을 0~10으로 독립 정규화한 뒤 가중합으로 종합점수 산출.
# TTA 미션을 반영해 표준화 연계성에 높은 가중을 둔다. config.json 으로 외부 조정 가능.
SCORE_WEIGHTS = {
    "impact": 0.30,           # 영향도
    "urgency": 0.20,          # 긴급도
    "ict": 0.15,              # ICT 관련성
    "standardization": 0.25,  # 표준화 연계성
    "recency": 0.10,          # 최신성
}

# AI가 부여한 영향등급 → 0~10 앵커 (term 카운트 포화 문제 해소)
IMPACT_LEVEL_SCORE = {"Critical": 10.0, "High": 7.5, "Medium": 5.0, "Low": 2.5, "": 0.0}

# 국제·국내 표준화 회의체 (본문 직접 언급 탐지용)
STANDARD_BODIES = [
    "3GPP", "ITU", "ITU-R", "ITU-T", "IEEE", "ETSI", "MPEG", "oneM2M",
    "IETF", "ISO", "IEC", "ATIS", "CCSA", "ARIB", "TSDSI", "TTA",
]

# 긴급도 가산 신호 (정책·규제·제재 등 시급한 행동을 요하는 어휘)
ESCALATION_TERMS = ["규제", "제재", "승인", "정책", "긴급", "리콜", "중단", "금지", "위반"]


def axis_impact(row: pd.Series) -> float:
    """영향도 0~10 — AI 영향등급을 앵커로, 등급 미부여 시 term 휴리스틱 폴백 + 엔티티 폭 보정."""
    data = parse_impact(row)
    base = IMPACT_LEVEL_SCORE.get(data["impact_level"], 0.0)
    if base == 0.0:
        text = _text_blob(row)
        hits = min(_term_hits(text, IMPACT_TERMS), 5)
        try:
            quality = min(int(float(row.get("quality_score") or 0) // 2), 3)
        except Exception:
            quality = 0
        base = min((hits + quality) / 8 * 10, 10.0)
    breadth = len([1 for _, label in keyword_items(row) if label in ("국가", "기업")])
    return round(min(base + min(breadth, 4) * 0.3, 10.0), 2)


def axis_urgency(row: pd.Series) -> float:
    """긴급도 0~10 — 행동 시급성(URGENCY_TERMS) + 정책/규제 가산. 최신성과 분리."""
    text = _text_blob(row)
    base = min(_term_hits(text, URGENCY_TERMS), 5) / 5 * 8
    escalation = min(_term_hits(text, ESCALATION_TERMS), 2) * 1.0
    return round(min(base + escalation, 10.0), 2)


def axis_ict(row: pd.Series) -> float:
    """ICT 관련성 0~10 — 기존 ict_relevance_score 정규화 (50점 → 만점)."""
    raw = ict_relevance_score(row)
    return round(max(min(raw, 50), 0) / 50 * 10, 2)


def axis_standardization(row: pd.Series) -> float:
    """표준화 연계성 0~10 — 독립 축. 표준 엔티티·국제 회의체 언급·표준화 격차 명시 여부."""
    data = parse_impact(row)
    text = _text_blob(row)
    std_entities = [name for name, label in keyword_items(row) if label == "표준"]
    score = min(len(std_entities), 3) * 2.0                              # 0~6
    score += min(_term_hits(text, STANDARD_BODIES), 3) * 1.0            # 0~3
    if data["standardization_gap"].strip():
        score += 2.0
    score += min(_term_hits(text, ["표준화", "기고", "워킹그룹", "표준 총회", "국제표준"]), 2) * 0.5
    return round(min(score, 10.0), 2)


def axis_recency(row: pd.Series) -> float:
    """최신성 0~10 — 기사 나이 지수 감쇠 (반감기 14일). 긴급도와 분리."""
    published = article_date(row)
    if published is None:
        return 0.0
    age_days = max((pd.Timestamp(datetime.now()) - published).days, 0)
    return round(10.0 * (0.5 ** (age_days / 14)), 2)


def issue_axis_scores(row: pd.Series) -> dict[str, float]:
    """5축 점수 묶음 (0~10)."""
    return {
        "영향도": axis_impact(row),
        "긴급도": axis_urgency(row),
        "ICT 관련성": axis_ict(row),
        "표준화 연계성": axis_standardization(row),
        "최신성": axis_recency(row),
    }


def weighted_issue_score(axes: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """5축 가중합 → 종합점수."""
    w = weights or SCORE_WEIGHTS
    return round(
        axes["영향도"] * w["impact"]
        + axes["긴급도"] * w["urgency"]
        + axes["ICT 관련성"] * w["ict"]
        + axes["표준화 연계성"] * w["standardization"]
        + axes["최신성"] * w["recency"],
        3,
    )


def categorized_entities(row: pd.Series, top: int = 3) -> dict[str, list[str]]:
    """기사 엔티티를 국가/기업/기술/표준 4분류로 (각 상위 top개). 카드 리본·다양성용."""
    out: dict[str, list[str]] = {"국가": [], "기업": [], "기술": [], "표준": []}
    for name, label in keyword_items(row):
        if label in out and name not in out[label]:
            out[label].append(name)
    return {k: v[:top] for k, v in out.items()}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _record_entity_set(record: dict) -> set[str]:
    """board 레코드의 기술/기업/국가 문자열을 하나의 집합으로 (다양성 유사도용)."""
    parts: set[str] = set()
    for col in ("기술", "기업", "국가"):
        for token in str(record.get(col, "") or "").split(","):
            token = token.strip()
            if token:
                parts.add(token)
    return parts


def _diversity_select(
    board: pd.DataFrame,
    limit: int,
    lambda_: float = 0.7,
    max_per_area: int = 2,
) -> pd.DataFrame:
    """MMR 그리디 재순위화 — 점수와 다양성을 함께 본다.
    val = λ·정규화점수 − (1−λ)·기선정집합과의 최대유사도.
    기술영역(_areas)은 6장 중 최대 max_per_area장으로 하드 제한(후보 부족 시 완화)."""
    if board.empty or len(board) <= 1:
        return board.head(limit)
    cand = board.to_dict("records")
    scores = [float(c.get("_score", 0.0)) for c in cand]
    smin, smax = min(scores), max(scores)
    span = (smax - smin) or 1.0
    for c in cand:
        c["_norm"] = (float(c.get("_score", 0.0)) - smin) / span

    selected: list[dict] = []
    area_count: Counter[str] = Counter()
    while cand and len(selected) < limit:
        best, best_val = None, None
        for c in cand:
            areas = c.get("_areas") or set()
            if areas and any(area_count[a] >= max_per_area for a in areas):
                continue
            sim = 0.0
            if selected:
                c_areas = c.get("_areas") or set()
                c_ents = _record_entity_set(c)
                sims = []
                for s in selected:
                    area_sim = _jaccard(c_areas, s.get("_areas") or set())
                    ent_sim = _jaccard(c_ents, _record_entity_set(s))
                    unit_sim = 1.0 if c.get("담당 단") == s.get("담당 단") else 0.0
                    sims.append(0.55 * area_sim + 0.30 * ent_sim + 0.15 * unit_sim)
                sim = max(sims)
            val = lambda_ * c["_norm"] - (1 - lambda_) * sim
            if best_val is None or val > best_val:
                best_val, best = val, c
        if best is None:  # 모든 후보가 영역 제한에 걸림 → 제한 완화, 최고점 선택
            best = max(cand, key=lambda c: c["_norm"])
        selected.append(best)
        for a in (best.get("_areas") or set()):
            area_count[a] += 1
        cand.remove(best)
    return pd.DataFrame(selected)


def recommended_action(row: pd.Series, impact: int, urgency: int) -> str:
    text = _text_blob(row)
    if impact >= 8 and urgency >= 7:
        return "담당 단 검토회의 안건화 및 관련 표준화 회의체 영향 확인"
    if "보안" in text or "규제" in text or "정책" in text:
        return "정책/규제 변화 여부 확인 후 대응 필요성 검토"
    if "표준" in text or "3GPP" in text or "ITU" in text or "IEEE" in text:
        return "관련 표준화 회의체, 기고서, 워킹그룹 동향 확인"
    if "투자" in text or "협력" in text or "상용화" in text:
        return "시장 확산 가능성과 국내 표준화 연계성 점검"
    return "모니터링 유지 및 유사 이슈 누적 시 후속 검토"


def article_unit_label(row: pd.Series, unit_names: dict[int, str] | None = None) -> str:
    unit_names = unit_names or {}
    raw_unit = row.get("unit_id")
    try:
        if pd.notna(raw_unit):
            return unit_names.get(int(raw_unit), "공통")
    except Exception:
        pass
    raw_units = clean_text(row.get("unit_ids"), 120)
    for token in raw_units.replace("[", "").replace("]", "").split(","):
        token = token.strip()
        if token.isdigit():
            return unit_names.get(int(token), "공통")
    return "공통"


BOARD_COLUMNS = [
    "이슈 후보", "담당 단", "검토 상태",
    "영향도", "긴급도", "ICT 관련성", "표준화 연계성", "최신성", "종합점수",
    "영향등급", "왜 중요한가", "TTA 대응과제", "표준화 격차",
    "관련 엔티티", "국가", "기업", "기술", "표준회의체",
    "관련 기사", "출처", "권장 조치", "조치 메모",
]


def issue_board(
    df: pd.DataFrame,
    limit: int = 30,
    unit_names: dict[int, str] | None = None,
    diversify: bool = False,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """표준화 대응 후보 보드.
    5축(영향도·긴급도·ICT·표준화·최신성) 가중합으로 정렬.
    diversify=True 면 MMR 재순위화로 기술영역/엔티티 편중을 줄인다 (Executive Brief용)."""
    rows = []
    for _, row in df.iterrows():
        title = clean_text(row.get("title"), 300)
        if not is_home_title_relevant(title):
            continue
        ict_score = ict_relevance_score(row)
        if ict_score < 3:
            continue
        axes = issue_axis_scores(row)
        score = weighted_issue_score(axes, weights)
        entities = [name for name, _ in keyword_items(row)][:6]
        cats = categorized_entities(row)
        impact_data = parse_impact(row)
        rows.append(
            {
                "이슈 후보": clean_text(row.get("title"), 180),
                "담당 단": article_unit_label(row, unit_names),
                "검토 상태": "미검토",
                "영향도": axes["영향도"],
                "긴급도": axes["긴급도"],
                "ICT 관련성": axes["ICT 관련성"],
                "표준화 연계성": axes["표준화 연계성"],
                "최신성": axes["최신성"],
                "종합점수": score,
                "영향등급": impact_data["impact_level"],
                "왜 중요한가": impact_data["impact_reason"],
                "TTA 대응과제": impact_data["tta_action_item"],
                "표준화 격차": impact_data["standardization_gap"],
                "관련 엔티티": ", ".join(entities),
                "국가": ", ".join(cats["국가"]),
                "기업": ", ".join(cats["기업"]),
                "기술": ", ".join(cats["기술"]),
                "표준회의체": ", ".join(cats["표준"]),
                "관련 기사": row.get("link", ""),
                "출처": clean_text(row.get("source"), 80),
                "권장 조치": recommended_action(row, int(axes["영향도"]), int(axes["긴급도"])),
                "조치 메모": "",
                "_score": score,
                "_areas": article_tech_areas(row),
            }
        )
    if not rows:
        return pd.DataFrame(columns=BOARD_COLUMNS)
    board = pd.DataFrame(rows).drop_duplicates(subset=["이슈 후보"])
    board = board.sort_values(["_score", "긴급도", "영향도"], ascending=False)
    if diversify:
        board = _diversity_select(board, limit)
    else:
        board = board.head(limit)
    internal_cols = [c for c in board.columns if str(c).startswith("_")]
    return board.drop(columns=internal_cols, errors="ignore").reset_index(drop=True)


def unit_issue_summary(df: pd.DataFrame, unit_names: dict[int, str], limit_per_unit: int = 3) -> pd.DataFrame:
    rows = []
    board = issue_board(df, limit=200, unit_names=unit_names)
    if board.empty:
        return pd.DataFrame(columns=["단", "추천 이슈", "영향도", "긴급도", "권장 조치"])

    article_lookup = df.set_index("link", drop=False) if "link" in df.columns else pd.DataFrame()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for _, issue in board.iterrows():
        unit_label = "공통"
        link = issue.get("관련 기사", "")
        if not article_lookup.empty and link in article_lookup.index:
            article = article_lookup.loc[link]
            if isinstance(article, pd.DataFrame):
                article = article.iloc[0]
            raw_unit = article.get("unit_id")
            try:
                raw_unit_int = int(raw_unit)
                unit_label = unit_names.get(raw_unit_int, "공통")
            except Exception:
                unit_label = "공통"
        grouped[unit_label].append(issue.to_dict())

    for unit_label, items in grouped.items():
        for item in items[:limit_per_unit]:
            rows.append(
                {
                    "단": unit_label,
                    "추천 이슈": item["이슈 후보"],
                    "영향도": item["영향도"],
                    "긴급도": item["긴급도"],
                    "권장 조치": item["권장 조치"],
                }
            )
    return pd.DataFrame(rows)
