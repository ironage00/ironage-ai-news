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


def issue_board(df: pd.DataFrame, limit: int = 30, unit_names: dict[int, str] | None = None) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        title = clean_text(row.get("title"), 300)
        if not is_home_title_relevant(title):
            continue
        ict_score = ict_relevance_score(row)
        if ict_score < 3:
            continue
        impact, urgency = issue_scores(row)
        entities = [name for name, _ in keyword_items(row)][:6]
        rows.append(
            {
                "이슈 후보": clean_text(row.get("title"), 180),
                "담당 단": article_unit_label(row, unit_names),
                "검토 상태": "미검토",
                "영향도": impact,
                "긴급도": urgency,
                "관련 엔티티": ", ".join(entities),
                "관련 기사": row.get("link", ""),
                "출처": clean_text(row.get("source"), 80),
                "권장 조치": recommended_action(row, impact, urgency),
                "조치 메모": "",
                "_score": impact * 1.2 + urgency + min(ict_score, 10) * 0.4,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["이슈 후보", "담당 단", "검토 상태", "영향도", "긴급도", "관련 엔티티", "관련 기사", "출처", "권장 조치", "조치 메모"]
        )
    board = pd.DataFrame(rows)
    board = board.drop_duplicates(subset=["이슈 후보"])
    return board.sort_values(["_score", "긴급도", "영향도"], ascending=False).drop(columns=["_score"]).head(limit)


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
