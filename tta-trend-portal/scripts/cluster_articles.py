"""T11 기사 클러스터 배치.

article_embeddings(pgvector)를 읽어 sklearn K-means로 군집화하고
news_articles.cluster_id / cluster_label을 채운다.

- 멱등: 시작 시 ADD COLUMN IF NOT EXISTS 실행 (마이그레이션 미적용 환경도 안전)
- NULL 임베딩 제외 (article_embeddings.embedding IS NOT NULL)
- 라벨: 각 클러스터에서 가장 빈번한 키워드/기술 2개

실행:
  로컬:  python tta-trend-portal/scripts/cluster_articles.py            (.env에서 DATABASE_URL 로드)
  CI:    DATABASE_URL=... python tta-trend-portal/scripts/cluster_articles.py

옵션(환경변수):
  CLUSTER_N         군집 수 (기본 10)
  CLUSTER_DAYS      최근 N일만 (기본 0 = 전체 임베딩 대상)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path


def load_env() -> None:
    """로컬 실행 시 프로젝트 루트 .env에서 DATABASE_URL 로드 (CI는 env가 이미 설정됨)."""
    if os.environ.get("DATABASE_URL"):
        return
    # scripts/ → tta-trend-portal/ → 프로젝트 루트
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def ensure_columns(cur) -> None:
    """멱등 마이그레이션 — 배치 단독 실행도 안전하게."""
    cur.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS cluster_id INTEGER")
    cur.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS cluster_label TEXT")


def parse_keywords(raw) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _term_str(item) -> str:
    """key_technologies/keywords 항목이 string 또는 dict({'term': ...}) 혼재 → 용어 문자열로 정규화."""
    if isinstance(item, dict):
        return str(item.get("term", "")).strip()
    return str(item).strip()


def article_terms(extracted_keywords) -> list[str]:
    """기사 1건의 기술·키워드 용어 목록 (기사 내 중복 제거)."""
    data = parse_keywords(extracted_keywords)
    terms: list[str] = []
    for field in ("key_technologies", "keywords"):
        v = data.get(field, [])
        if isinstance(v, (str, dict)):
            v = [v]
        if isinstance(v, list):
            for raw in v:
                t = _term_str(raw)
                if t:
                    terms.append(t)
    return list(dict.fromkeys(terms))


def cluster_label_terms(cluster_metas: list, global_counts: Counter) -> str:
    """변별도 기반 라벨 — 전역 빈도 대비 이 클러스터에서 과대표집된 용어 2개.
    (단순 빈도 라벨은 'AI'가 모든 클러스터를 도배하므로 distinctiveness 사용)"""
    local: Counter = Counter()
    for ek in cluster_metas:
        for t in article_terms(ek):
            local[t] += 1
    if not local:
        return "기타"
    # score = 클러스터 내 빈도 × (클러스터 점유율 / 전역 점유율). 너무 희귀한 용어는 제외.
    scored = []
    for term, lc in local.items():
        if lc < 3:
            continue
        gc = global_counts.get(term, lc)
        distinctiveness = lc / gc  # 이 클러스터에 얼마나 집중됐는가
        scored.append((distinctiveness * lc, term))
    if not scored:
        scored = [(lc, t) for t, lc in local.most_common(2)]
    scored.sort(reverse=True)
    top = [t for _, t in scored[:2]]
    return " · ".join(top) if top else "기타"


def main() -> int:
    load_env()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL 미설정", file=sys.stderr)
        return 1
    if not url.startswith("postgresql"):
        print("ERROR: 이 배치는 PostgreSQL(Supabase) 전용입니다.", file=sys.stderr)
        return 1

    import numpy as np
    import psycopg2
    from psycopg2.extras import execute_values
    from sklearn.cluster import KMeans

    n_clusters = int(os.environ.get("CLUSTER_N", "10"))
    days = int(os.environ.get("CLUSTER_DAYS", "0"))

    con = psycopg2.connect(url, connect_timeout=30)
    con.autocommit = False
    cur = con.cursor()
    ensure_columns(cur)

    # 임베딩 + 메타 로드 (NULL 임베딩 제외)
    day_filter = "AND na.collected_at >= NOW() - CAST(%s AS interval)" if days > 0 else ""
    params = [f"{days} days"] if days > 0 else []
    cur.execute(
        f"""
        SELECT na.id, ae.embedding::text, na.extracted_keywords
        FROM news_articles na
        JOIN article_embeddings ae ON ae.article_id = na.id
        WHERE ae.embedding IS NOT NULL
        {day_filter}
        """,
        params,
    )
    rows = cur.fetchall()
    if len(rows) < n_clusters:
        print(f"임베딩 {len(rows)}건 < 군집 {n_clusters}개 — 건너뜀")
        con.close()
        return 0

    ids = [r[0] for r in rows]
    vectors = np.array([json.loads(r[1]) for r in rows], dtype=np.float32)
    ek_by_id = {r[0]: r[2] for r in rows}
    print(f"임베딩 로드: {len(ids)}건 × {vectors.shape[1]}차원")

    # 전역 용어 빈도 (변별도 라벨용)
    global_counts: Counter = Counter()
    for ek in ek_by_id.values():
        for t in article_terms(ek):
            global_counts[t] += 1

    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = km.fit_predict(vectors)

    # 클러스터별 라벨 생성 (변별도 기반)
    cluster_to_ids: dict[int, list[int]] = {}
    for art_id, cl in zip(ids, labels):
        cluster_to_ids.setdefault(int(cl), []).append(art_id)
    cluster_label: dict[int, str] = {
        cl: cluster_label_terms([ek_by_id[i] for i in id_list], global_counts)
        for cl, id_list in cluster_to_ids.items()
    }
    for cl, id_list in sorted(cluster_to_ids.items()):
        print(f"  cluster {cl}: {len(id_list)}건 — {cluster_label[cl]}")

    # 일괄 업데이트
    updates = [(int(cl), cluster_label[int(cl)], art_id) for art_id, cl in zip(ids, labels)]
    execute_values(
        cur,
        """
        UPDATE news_articles AS na
        SET cluster_id = v.cluster_id, cluster_label = v.cluster_label
        FROM (VALUES %s) AS v(cluster_id, cluster_label, id)
        WHERE na.id = v.id
        """,
        updates,
        template="(%s, %s, %s)",
    )
    con.commit()
    print(f"업데이트 완료: {len(updates)}건")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
