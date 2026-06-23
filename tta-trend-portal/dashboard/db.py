import os
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


NEWS_COLUMNS = [
    "id",
    "title",
    "link",
    "source",
    "published",
    "collected_at",
    "content",
    "quality_score",
    "is_selected",
    "is_analyzed",
    "analysis_result",
    "ai_model",
    "extracted_keywords",
    "unit_id",
    "unit_ids",
]


def default_sqlite_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "news.db"
        if candidate.exists():
            return candidate
    return here.parents[2] / "data" / "news.db"


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    return f"sqlite:///{default_sqlite_path().as_posix()}"


def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


def is_postgres(engine: Engine) -> bool:
    return engine.url.drivername.startswith("postgresql")


def existing_news_columns(engine: Engine) -> set[str]:
    try:
        if is_postgres(engine):
            sql = """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'news_articles'
            """
            df = pd.read_sql(text(sql), engine)
            return set(df["column_name"].tolist())
        df = pd.read_sql(text("PRAGMA table_info(news_articles)"), engine)
        return set(df["name"].tolist())
    except Exception:
        return set()


def select_news_columns(engine: Engine) -> str:
    existing = existing_news_columns(engine)
    parts = []
    for col in NEWS_COLUMNS:
        if col in existing:
            parts.append(col)
        else:
            parts.append(f"NULL AS {col}")
    return ", ".join(parts)


def fetch_articles(
    engine: Engine,
    days: int = 30,
    query: str = "",
    source: str = "",
    unit_id: Optional[int] = None,
    analyzed_only: bool = True,
    limit: int = 300,
) -> pd.DataFrame:
    conditions = ["1=1"]
    params = {"limit": limit}

    if analyzed_only:
        conditions.append("is_analyzed = :is_analyzed")
        params["is_analyzed"] = True

    if days and days > 0:
        if is_postgres(engine):
            conditions.append("collected_at >= NOW() - CAST(:days_interval AS interval)")
            params["days_interval"] = f"{days} days"
        else:
            conditions.append("datetime(collected_at) >= datetime('now', :days_expr)")
            params["days_expr"] = f"-{days} days"
        params["days"] = days

    if query:
        like = f"%{query.lower()}%"
        conditions.append(
            "(LOWER(COALESCE(title, '')) LIKE :q OR "
            "LOWER(COALESCE(content, '')) LIKE :q OR "
            "LOWER(COALESCE(analysis_result, '')) LIKE :q OR "
            "LOWER(COALESCE(extracted_keywords, '')) LIKE :q)"
        )
        params["q"] = like

    if source:
        conditions.append("source = :source")
        params["source"] = source

    if unit_id:
        existing = existing_news_columns(engine)
        unit_conditions = []
        if "unit_id" in existing:
            unit_conditions.append("unit_id = :unit_id")
        if "unit_ids" in existing:
            unit_conditions.append("COALESCE(unit_ids, '') LIKE :unit_token")
        if unit_conditions:
            conditions.append(f"({' OR '.join(unit_conditions)})")
        params["unit_id"] = unit_id
        params["unit_token"] = f"%,{unit_id},%"

    sql = f"""
        SELECT {select_news_columns(engine)}
        FROM news_articles
        WHERE {" AND ".join(conditions)}
        ORDER BY COALESCE(published, collected_at) DESC
        LIMIT :limit
    """
    return pd.read_sql(text(sql), engine, params=params)


def fetch_sources(engine: Engine) -> list[str]:
    try:
        df = pd.read_sql(text("SELECT DISTINCT source FROM news_articles WHERE source IS NOT NULL ORDER BY source"), engine)
        return [str(v) for v in df["source"].dropna().tolist() if str(v).strip()]
    except Exception:
        return []


def fetch_stats(engine: Engine) -> dict:
    stats = {}
    queries = {
        "articles": "SELECT COUNT(*) AS n FROM news_articles",
        "analyzed": "SELECT COUNT(*) AS n FROM news_articles WHERE is_analyzed = true",
        "embeddings": "SELECT COUNT(*) AS n FROM article_embeddings",
    }
    for key, sql in queries.items():
        try:
            stats[key] = int(pd.read_sql(text(sql), engine).iloc[0]["n"])
        except Exception:
            stats[key] = 0
    return stats
