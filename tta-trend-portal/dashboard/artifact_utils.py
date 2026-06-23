from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db import is_postgres


REPORT_COLUMNS = [
    "report_type",
    "title",
    "period_start",
    "period_end",
    "google_doc_url",
    "excel_file_url",
    "source_article_count",
    "generated_at",
    "owner",
    "visibility",
    "status",
    "notes",
]


def portal_root() -> Path:
    return Path(__file__).resolve().parents[1]


def report_artifacts_csv_path() -> Path:
    env_path = os.getenv("TTA_REPORT_ARTIFACTS_CSV", "").strip()
    if env_path:
        return Path(env_path)
    return portal_root() / "data" / "report_artifacts.csv"


def table_exists(engine: Engine, table_name: str) -> bool:
    try:
        if is_postgres(engine):
            sql = """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_name = :table_name
                ) AS exists
            """
            return bool(pd.read_sql(text(sql), engine, params={"table_name": table_name}).iloc[0]["exists"])
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
        return not pd.read_sql(text(sql), engine, params={"table_name": table_name}).empty
    except Exception:
        return False


def normalize_report_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in REPORT_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = ""
    normalized = normalized[REPORT_COLUMNS]
    for col in ["period_start", "period_end", "generated_at"]:
        normalized[col] = normalized[col].astype(str).str.slice(0, 19)
    normalized["source_article_count"] = pd.to_numeric(
        normalized["source_article_count"],
        errors="coerce",
    ).fillna(0).astype(int)
    return normalized.sort_values(["period_end", "generated_at", "title"], ascending=False)


def fetch_report_artifacts(engine: Engine) -> tuple[pd.DataFrame, str]:
    if table_exists(engine, "report_artifacts"):
        try:
            cols = ", ".join(REPORT_COLUMNS)
            sql = f"SELECT {cols} FROM report_artifacts ORDER BY period_end DESC, generated_at DESC"
            return normalize_report_artifacts(pd.read_sql(text(sql), engine)), "database"
        except Exception:
            pass

    csv_path = report_artifacts_csv_path()
    if csv_path.exists():
        return normalize_report_artifacts(pd.read_csv(csv_path)), str(csv_path)

    template_path = portal_root() / "templates" / "report-links.csv"
    if template_path.exists():
        return normalize_report_artifacts(pd.read_csv(template_path)), str(template_path)

    return normalize_report_artifacts(pd.DataFrame()), "not configured"


def upsert_report_artifacts(engine: Engine, artifacts: pd.DataFrame) -> int:
    if not is_postgres(engine) or not table_exists(engine, "report_artifacts"):
        return 0
    normalized = normalize_report_artifacts(artifacts)
    if normalized.empty:
        return 0
    sql = text(
        """
        INSERT INTO report_artifacts (
            report_type,
            title,
            period_start,
            period_end,
            google_doc_url,
            excel_file_url,
            source_article_count,
            generated_at,
            owner,
            visibility,
            status,
            notes
        )
        VALUES (
            :report_type,
            :title,
            NULLIF(:period_start, '')::date,
            NULLIF(:period_end, '')::date,
            :google_doc_url,
            :excel_file_url,
            :source_article_count,
            NULLIF(:generated_at, '')::timestamptz,
            :owner,
            :visibility,
            :status,
            :notes
        )
        ON CONFLICT (report_type, title, period_start) DO UPDATE SET
            period_end = EXCLUDED.period_end,
            google_doc_url = EXCLUDED.google_doc_url,
            excel_file_url = EXCLUDED.excel_file_url,
            source_article_count = EXCLUDED.source_article_count,
            generated_at = EXCLUDED.generated_at,
            owner = EXCLUDED.owner,
            visibility = EXCLUDED.visibility,
            status = EXCLUDED.status,
            notes = EXCLUDED.notes
        """
    )
    rows = normalized.to_dict("records")
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)
