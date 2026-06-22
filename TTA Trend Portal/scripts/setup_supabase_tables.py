from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required.")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    schema_path = root / "supabase" / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    engine = create_engine(database_url(), pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text(sql))
    print(f"Applied schema: {schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
