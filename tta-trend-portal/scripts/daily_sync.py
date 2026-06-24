"""
scripts/daily_sync.py
SQLite news.db → Supabase 증분 동기화

news_engine.py (daily 수집) 직후 실행하거나,
cron-job.org / GitHub Actions로 독립 실행합니다.

사용법:
    DATABASE_URL=postgresql://... python scripts/daily_sync.py
    DATABASE_URL=postgresql://... python scripts/daily_sync.py --full
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = Path(__file__).resolve().parents[3] / "data" / "news.db"
BATCH_SIZE = 500


def _load_env():
    """상위 디렉토리의 .env 파일에서 환경변수 로드"""
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

COLUMNS = [
    "title", "link", "source", "published", "collected_at", "content",
    "quality_score", "is_selected", "is_analyzed", "analysis_result",
    "ai_model", "extracted_keywords", "keywords", "ai_model_fallback", "unit_id",
]
BOOL_COLS = {"is_selected", "is_analyzed"}

# 제목에 이 단어가 있으면 ICT 무관 기사로 간주해 sync 제외
_NON_ICT_BLOCK = [
    "선거", "대선", "총선", "후보", "여론조사",
    "부동산", "아파트", "재건축", "분양",
    "맛집", "연예", "스포츠", "야구", "축구", "골프",
    "주가", "증시", "공약", "사설", "횡령", "배임",
    "굿즈", "항암", "신약", "임플란트", "화장품",
    "농업", "도축", "리테일", "retailer", "daiso",
]

# 제목에 이 단어가 있으면 ICT 관련이므로 _NON_ICT_BLOCK을 무시하고 통과
_ICT_OVERRIDE = [
    "통신", "이동통신", "5G", "6G", "B5G", "AI-RAN", "NTN",
    "위성", "오픈랜", "O-RAN", "양자", "표준", "표준화",
    "ITU", "3GPP", "IEEE", "ETSI", "네트워크", "주파수",
    "반도체", "클라우드", "보안", "사이버", "인공지능", "AI",
]


def _is_ict(title: str, analysis: str | None) -> bool:
    """Return False for obvious non-ICT articles."""
    combined = f"{title or ''} {analysis or ''}".lower()
    for term in _NON_ICT_BLOCK:
        if term.lower() in combined:
            if any(t.lower() in combined for t in _ICT_OVERRIDE):
                return True
            return False
    return True


def pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def existing_links(cur) -> set[str]:
    cur.execute("SELECT link FROM news_articles")
    return {row[0] for row in cur.fetchall()}


def sync_articles(src: sqlite3.Connection, dst, full: bool = False, ict_filter: bool = True) -> int:
    # analyzed_only: Supabase에는 AI 분석 완료 기사만 올린다 (비분석 기사는 포털에서 미사용)
    where = "WHERE is_analyzed = 1" if ict_filter else ""
    rows = src.execute(
        f"SELECT {', '.join(COLUMNS)} FROM news_articles {where}"
    ).fetchall()
    if not rows:
        print("SQLite에 기사 없음")
        return 0

    if ict_filter:
        title_idx = COLUMNS.index("title")
        analysis_idx = COLUMNS.index("analysis_result")
        before = len(rows)
        rows = [r for r in rows if _is_ict(r[title_idx], r[analysis_idx])]
        print(f"ICT 필터: {before}건 → {len(rows)}건 (제외 {before - len(rows)}건)")

    if not full:
        with dst.cursor() as cur:
            already = existing_links(cur)
        new_rows = [r for r in rows if r[COLUMNS.index("link")] not in already]
        print(f"신규: {len(new_rows)}건 / 필터 후: {len(rows)}건")
        rows = new_rows

    if not rows:
        print("동기화할 신규 기사 없음")
        return 0

    def convert(row):
        return tuple(
            bool(v) if col in BOOL_COLS and v is not None else v
            for col, v in zip(COLUMNS, row)
        )

    values = [convert(r) for r in rows]
    col_str = ", ".join(f'"{c}"' for c in COLUMNS)
    update_set = ", ".join(
        f'"{c}" = EXCLUDED."{c}"'
        for c in ("is_analyzed", "analysis_result", "ai_model",
                  "extracted_keywords", "keywords", "unit_id")
    )

    success = 0
    with dst.cursor() as cur:
        for i in range(0, len(values), BATCH_SIZE):
            batch = values[i : i + BATCH_SIZE]
            execute_values(
                cur,
                f"""INSERT INTO news_articles ({col_str}) VALUES %s
                    ON CONFLICT (link) DO UPDATE SET {update_set}""",
                batch,
                template=f"({', '.join(['%s'] * len(COLUMNS))})",
            )
            dst.commit()
            success += len(batch)
            print(f"  {min(i + BATCH_SIZE, len(values))}/{len(values)}건 완료")

    return success


def sync_embeddings(src: sqlite3.Connection, dst, full: bool = False) -> int:
    try:
        rows = src.execute(
            "SELECT article_id, embedding_json, embedded_at, model_name FROM article_embeddings"
        ).fetchall()
    except Exception:
        print("article_embeddings 테이블 없음, 건너뜀")
        return 0

    if not rows:
        return 0

    if not full:
        with dst.cursor() as cur:
            cur.execute("SELECT article_id FROM article_embeddings")
            already = {r[0] for r in cur.fetchall()}
        rows = [r for r in rows if r[0] not in already]

    if not rows:
        print("동기화할 신규 임베딩 없음")
        return 0

    success = 0
    with dst.cursor() as cur:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = [tuple(r) for r in rows[i : i + BATCH_SIZE]]
            execute_values(
                cur,
                """INSERT INTO article_embeddings (article_id, embedding_json, embedded_at, model_name)
                   VALUES %s ON CONFLICT (article_id) DO NOTHING""",
                batch,
            )
            dst.commit()
            success += len(batch)

    print(f"임베딩 {success}건 동기화 완료")
    return success


def main():
    parser = argparse.ArgumentParser(description="SQLite → Supabase 동기화")
    parser.add_argument("--full", action="store_true", help="전체 재동기화 (기본: 신규만)")
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="ICT 필터 비활성화 — 미분석 기사 포함 전체 sync (비권장)",
    )
    args = parser.parse_args()

    if not SQLITE_PATH.exists():
        sys.exit(f"SQLite 없음: {SQLITE_PATH}")

    ict_filter = not args.no_filter
    print(f"ICT 필터: {'ON (is_analyzed=1 + 비ICT 제목 제외)' if ict_filter else 'OFF (전체 sync)'}")

    src = sqlite3.connect(SQLITE_PATH)
    dst = psycopg2.connect(pg_url())

    try:
        print(f"{'전체' if args.full else '증분'} 동기화 시작...")
        n = sync_articles(src, dst, full=args.full, ict_filter=ict_filter)
        print(f"기사 {n}건 동기화 완료")
        sync_embeddings(src, dst, full=args.full)
        print("완료")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
