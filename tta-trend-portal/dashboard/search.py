import json
import os
import re
from html import unescape
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db import NEWS_COLUMNS, existing_news_columns, fetch_articles, is_postgres


EMBEDDING_MODEL = "text-embedding-3-small"
ANSWER_MODEL = os.getenv("TTA_SEARCH_ANSWER_MODEL", "gpt-4o")


def clean_text(value: Any, max_len: int = 1200) -> str:
    text_value = "" if value is None else str(value)
    text_value = unescape(text_value)
    text_value = re.sub(r"<[^>]+>", " ", text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value[:max_len]


def parse_keywords(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def embed_query(query: str) -> List[float]:
    client = get_openai_client()
    if client is None:
        return []
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    return response.data[0].embedding


def keyword_rank(df: pd.DataFrame, query: str, top_k: int = 20) -> pd.DataFrame:
    tokens = [t for t in re.split(r"\s+", query.lower()) if t]
    if df.empty or not tokens:
        return df.head(top_k)

    def score(row) -> float:
        haystack = " ".join(
            clean_text(row.get(col), 500)
            for col in ["title", "content", "analysis_result", "extracted_keywords", "source"]
        ).lower()
        title = clean_text(row.get("title"), 300).lower()
        value = 0.0
        for token in tokens:
            if token in title:
                value += 3.0
            if token in haystack:
                value += 1.0
        if row.get("is_analyzed"):
            value += 0.5
        try:
            value += float(row.get("quality_score") or 0) * 0.2
        except Exception:
            pass
        return value

    ranked = df.copy()
    ranked["similarity"] = ranked.apply(score, axis=1)
    return ranked.sort_values("similarity", ascending=False).head(top_k)


def vector_search(engine: Engine, query: str, days: int, unit_id: int | None, top_k: int = 20) -> pd.DataFrame:
    if not is_postgres(engine):
        return pd.DataFrame()
    q_vec = embed_query(query)
    if not q_vec:
        return pd.DataFrame()

    conditions = [
        "na.is_analyzed = true",
        "na.analysis_result IS NOT NULL",
        "na.collected_at >= NOW() - CAST(:days_interval AS interval)",
    ]
    existing = existing_news_columns(engine)
    params: Dict[str, Any] = {
        "q": str(q_vec),
        "days": days,
        "days_interval": f"{days} days",
        "limit": top_k,
    }
    if unit_id:
        unit_conditions = []
        if "unit_id" in existing:
            unit_conditions.append("na.unit_id = :unit_id")
        if "unit_ids" in existing:
            unit_conditions.append("COALESCE(na.unit_ids, '') LIKE :unit_token")
        if unit_conditions:
            conditions.append(f"({' OR '.join(unit_conditions)})")
        params["unit_id"] = unit_id
        params["unit_token"] = f"%,{unit_id},%"

    select_columns = ", ".join(
        f"na.{col}" if col in existing else f"NULL AS {col}"
        for col in NEWS_COLUMNS
    )
    sql = f"""
        SELECT
            {select_columns},
            1 - (ae.embedding <=> CAST(:q AS vector)) AS similarity
        FROM article_embeddings ae
        JOIN news_articles na ON na.id = ae.article_id
        WHERE {" AND ".join(conditions)}
        ORDER BY ae.embedding <=> CAST(:q AS vector)
        LIMIT :limit
    """
    try:
        return pd.read_sql(text(sql), engine, params=params)
    except Exception:
        return pd.DataFrame()


def hybrid_search(
    engine: Engine,
    query: str,
    days: int,
    unit_id: int | None,
    top_k: int = 20,
    analyzed_only: bool = True,
) -> tuple[pd.DataFrame, str]:
    vec = vector_search(engine, query, days=days, unit_id=unit_id, top_k=top_k) if analyzed_only else pd.DataFrame()
    if analyzed_only and not vec.empty:
        vec["search_type"] = "vector"
        return vec, "vector"

    base = fetch_articles(engine, days=days, query="", unit_id=unit_id, analyzed_only=analyzed_only, limit=600)
    ranked = keyword_rank(base, query, top_k=top_k)
    ranked["search_type"] = "keyword"
    return ranked, "keyword"


def build_answer(query: str, sources: pd.DataFrame) -> str:
    if sources.empty:
        return "검색 결과가 없습니다."
    client = get_openai_client()
    snippets = []
    for _, row in sources.head(8).iterrows():
        snippets.append(
            "\n".join(
                [
                    f"제목: {clean_text(row.get('title'), 200)}",
                    f"출처: {clean_text(row.get('source'), 80)}",
                    f"일자: {clean_text(row.get('published') or row.get('collected_at'), 80)}",
                    f"분석: {clean_text(row.get('analysis_result') or row.get('content'), 900)}",
                    f"링크: {clean_text(row.get('link'), 300)}",
                ]
            )
        )

    if client is None:
        titles = "\n".join(f"- {clean_text(r.get('title'), 120)}" for _, r in sources.head(5).iterrows())
        return f"OPENAI_API_KEY가 없어 생성형 답변은 생략합니다.\n\n관련 기사:\n{titles}"

    prompt = f"""TTA 직원용 ICT 뉴스 검색 답변을 작성하세요.

질문:
{query}

근거 기사:
{chr(10).join(snippets)}

작성 규칙:
- 근거 기사에 있는 내용만 사용
- 5줄 이내 요약
- 표준화 시사점이 있으면 별도 bullet로 제시
- 마지막에 근거 부족 여부를 명시
"""
    response = client.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=700,
    )
    return response.choices[0].message.content.strip()


def dataframe_to_sources(df: pd.DataFrame) -> List[Dict[str, Any]]:
    cols = ["id", "title", "source", "published", "link", "similarity", "search_type"]
    available = [c for c in cols if c in df.columns]
    return df[available].to_dict("records")
