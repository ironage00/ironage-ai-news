"""
SQLite → Supabase(PostgreSQL) 1회용 마이그레이션 스크립트
실행: python migrate_sqlite_to_postgres.py
"""
import sqlite3
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
from psycopg2.extras import execute_values

DB_URL = os.environ.get('DATABASE_URL', '')
SQLITE_PATH = 'data/news.db'

if not DB_URL:
    print("❌ .env 파일에 DATABASE_URL이 없습니다.")
    exit(1)

if not Path(SQLITE_PATH).exists():
    print(f"❌ SQLite 파일을 찾을 수 없습니다: {SQLITE_PATH}")
    exit(1)

if DB_URL.startswith('postgresql+psycopg2://'):
    pg_url = DB_URL.replace('postgresql+psycopg2://', 'postgresql://', 1)
else:
    pg_url = DB_URL

print(f"📂 SQLite 경로: {SQLITE_PATH}")
print(f"🌐 Supabase 연결 중...")

src = sqlite3.connect(SQLITE_PATH)
src.row_factory = sqlite3.Row
dst = psycopg2.connect(pg_url)


def get_pg_schema(cursor, table_name):
    """PostgreSQL 테이블의 컬럼명과 데이터 타입 조회"""
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return {row[0]: row[1] for row in cursor.fetchall()}


def convert_row(row, col_names, pg_schema):
    """SQLite 행을 PostgreSQL 타입에 맞게 변환"""
    result = []
    for col, val in zip(col_names, row):
        pg_type = pg_schema.get(col, '')
        if pg_type == 'boolean' and val is not None:
            result.append(bool(val))
        else:
            result.append(val)
    return tuple(result)


def migrate_table(table_name, conflict_col, batch_size=1000):
    rows = src.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        print(f"  → {table_name}: 데이터 없음")
        return

    sqlite_cols = list(rows[0].keys())

    with dst.cursor() as cur:
        pg_schema = get_pg_schema(cur, table_name)

    valid_cols = [c for c in sqlite_cols if c in pg_schema]
    skipped_cols = [c for c in sqlite_cols if c not in pg_schema]
    if skipped_cols:
        print(f"  ℹ️  PostgreSQL에 없는 컬럼 제외: {skipped_cols}")

    bool_cols = [c for c in valid_cols if pg_schema[c] == 'boolean']
    if bool_cols:
        print(f"  ℹ️  boolean 변환 컬럼: {bool_cols}")

    col_indices = [sqlite_cols.index(c) for c in valid_cols]
    values = [
        convert_row(
            [row[i] for i in col_indices],
            valid_cols,
            pg_schema
        )
        for row in rows
    ]

    placeholders = ','.join(['%s'] * len(valid_cols))
    col_str = ','.join(f'"{c}"' for c in valid_cols)

    success = 0
    with dst.cursor() as cur:
        for i in range(0, len(values), batch_size):
            batch = values[i:i + batch_size]
            try:
                execute_values(
                    cur,
                    f"""INSERT INTO {table_name} ({col_str})
                        VALUES %s
                        ON CONFLICT ({conflict_col}) DO NOTHING""",
                    batch,
                    template=f"({placeholders})"
                )
                dst.commit()
                success += len(batch)
                print(f"  ✅ {min(i+batch_size, len(values))}/{len(rows)}건 완료")
            except Exception as e:
                dst.rollback()
                print(f"  ⚠️ 배치 {i}~{i+batch_size} 실패: {e}")

    print(f"  → {table_name}: {success}건 이전 완료")


try:
    print("\n[1/2] news_articles 이전 중...")
    migrate_table('news_articles', 'link', batch_size=1000)

    print("\n[2/2] article_embeddings 이전 중...")
    try:
        migrate_table('article_embeddings', 'article_id', batch_size=500)
    except Exception as e:
        print(f"  ⚠️ article_embeddings 테이블 없음 또는 오류: {e}")

    print("\n📊 이전 결과 확인:")
    with dst.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM news_articles")
        print(f"  • news_articles: {cur.fetchone()[0]:,}건")
        try:
            cur.execute("SELECT COUNT(*) FROM article_embeddings")
            print(f"  • article_embeddings: {cur.fetchone()[0]:,}건")
        except Exception:
            pass

    print("\n✅ 마이그레이션 완료!")

finally:
    src.close()
    dst.close()
