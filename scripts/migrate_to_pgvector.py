"""
pgvector 마이그레이션 스크립트
embedding_json (TEXT ~13KB/row) → embedding (vector(1536) ~6KB/row)

실행:
    python scripts/migrate_to_pgvector.py

단계:
  1. vector 확장 활성화
  2. embedding vector(1536) 컬럼 추가
  3. embedding_json → vector 데이터 이관 (배치)
  4. HNSW 인덱스 생성
  5. embedding_json 컬럼 삭제

효과: article_embeddings 약 480MB → 약 220MB (55% 절감)
"""
import sys, os, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import tomllib
from sqlalchemy import create_engine, text

def get_engine():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        toml_path = ROOT / 'streamlit_secrets.toml'
        with open(toml_path, 'rb') as f:
            db_url = tomllib.load(f).get('DATABASE_URL', '')
    if not db_url:
        raise RuntimeError('DATABASE_URL을 찾을 수 없습니다.')
    if db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    return create_engine(db_url, pool_pre_ping=True, pool_size=3)


def run(engine):
    t0 = time.time()

    # ── Step 1: vector 확장 활성화 ──────────────────────────────
    print('\n[1/5] vector 확장 활성화...')
    with engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    print('  ✅ vector 확장 활성화 완료')

    # ── Step 2: embedding vector(1536) 컬럼 추가 ────────────────
    print('\n[2/5] embedding vector(1536) 컬럼 추가...')
    with engine.connect() as conn:
        has_col = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='article_embeddings' AND column_name='embedding'"
        )).scalar()
    if has_col:
        print('  ℹ️  embedding 컬럼 이미 존재 — 건너뜀')
    else:
        with engine.begin() as conn:
            conn.execute(text(
                'ALTER TABLE article_embeddings ADD COLUMN embedding vector(1536)'
            ))
        print('  ✅ embedding 컬럼 추가 완료')

    # ── Step 3: 데이터 이관 (배치 UPDATE) ───────────────────────
    print('\n[3/5] embedding_json → vector 데이터 이관...')
    with engine.connect() as conn:
        total_to_migrate = conn.execute(text(
            "SELECT COUNT(*) FROM article_embeddings WHERE embedding IS NULL"
        )).scalar()
        has_json_col = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='article_embeddings' AND column_name='embedding_json'"
        )).scalar()

    if not has_json_col:
        print('  ℹ️  embedding_json 컬럼 없음 — 이미 마이그레이션됨')
    elif total_to_migrate == 0:
        print('  ℹ️  이관할 데이터 없음 — 건너뜀')
    else:
        print(f'  이관 대상: {total_to_migrate:,}건')
        BATCH = 2000
        migrated = 0
        t_step = time.time()

        while True:
            with engine.begin() as conn:
                result = conn.execute(text(
                    """
                    UPDATE article_embeddings
                    SET    embedding = embedding_json::vector
                    WHERE  id IN (
                        SELECT id FROM article_embeddings
                        WHERE  embedding IS NULL
                        ORDER  BY id
                        LIMIT  :batch
                    )
                    """
                ), {'batch': BATCH})
                rows_affected = result.rowcount

            if rows_affected == 0:
                break

            migrated += rows_affected
            elapsed = time.time() - t_step
            pct = min(100, round(100 * migrated / total_to_migrate))
            rate = migrated / elapsed if elapsed > 0 else 1
            eta  = int((total_to_migrate - migrated) / rate)
            print(f'  [{pct:3d}%] {migrated:,}/{total_to_migrate:,}건  '
                  f'({elapsed:.0f}s, 잔여 ~{eta//60}분{eta%60}초)')

        print(f'  ✅ 데이터 이관 완료 ({time.time()-t_step:.0f}s)')

    # ── Step 4: HNSW 인덱스 생성 ────────────────────────────────
    print('\n[4/5] HNSW 코사인 인덱스 생성...')
    with engine.connect() as conn:
        has_idx = conn.execute(text(
            "SELECT 1 FROM pg_indexes "
            "WHERE tablename='article_embeddings' AND indexname='idx_ae_embedding_hnsw'"
        )).scalar()

    if has_idx:
        print('  ℹ️  인덱스 이미 존재 — 건너뜀')
    else:
        t_idx = time.time()
        # Supabase 기본 statement_timeout(30s)을 우회하여 인덱스 빌드
        try:
            with engine.begin() as conn:
                conn.execute(text("SET statement_timeout = '0'"))   # timeout 해제
                conn.execute(text(
                    'CREATE INDEX idx_ae_embedding_hnsw '
                    'ON article_embeddings '
                    'USING hnsw (embedding vector_cosine_ops)'
                ))
            print(f'  ✅ HNSW 인덱스 생성 완료 ({time.time()-t_idx:.0f}s)')
        except Exception as e:
            print(f'  ⚠️  HNSW 타임아웃 — IVFFlat으로 재시도...')
            try:
                with engine.begin() as conn:
                    conn.execute(text("SET statement_timeout = '0'"))
                    conn.execute(text(
                        'CREATE INDEX idx_ae_embedding_hnsw '
                        'ON article_embeddings '
                        'USING ivfflat (embedding vector_cosine_ops) '
                        'WITH (lists = 100)'
                    ))
                print(f'  ✅ IVFFlat 인덱스 생성 완료 ({time.time()-t_idx:.0f}s)')
            except Exception as e2:
                print(f'  ❌ 인덱스 자동 생성 실패: {e2}')
                print()
                print('  👉 Supabase 대시보드 SQL 에디터에서 수동 실행:')
                print('     CREATE INDEX idx_ae_embedding_hnsw')
                print('     ON article_embeddings')
                print('     USING hnsw (embedding vector_cosine_ops);')

    # ── Step 5: embedding_json 컬럼 삭제 ────────────────────────
    print('\n[5/5] embedding_json 컬럼 삭제...')
    with engine.connect() as conn:
        has_json_col = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='article_embeddings' AND column_name='embedding_json'"
        )).scalar()

    if not has_json_col:
        print('  ℹ️  embedding_json 이미 없음 — 건너뜀')
    else:
        # 이관 완전 완료 확인
        with engine.connect() as conn:
            null_cnt = conn.execute(text(
                'SELECT COUNT(*) FROM article_embeddings WHERE embedding IS NULL'
            )).scalar()
        if null_cnt > 0:
            print(f'  ⚠️  embedding IS NULL 행이 {null_cnt:,}건 남아 있습니다.')
            print('  Step 3을 다시 실행하거나 수동 확인 후 삭제하세요.')
        else:
            with engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE article_embeddings DROP COLUMN embedding_json'
                ))
            print('  ✅ embedding_json 컬럼 삭제 완료')

    # ── 최종 현황 ────────────────────────────────────────────────
    print('\n' + '='*55)
    with engine.connect() as conn:
        size = conn.execute(text(
            "SELECT pg_size_pretty(pg_total_relation_size('article_embeddings'))"
        )).scalar()
        cnt  = conn.execute(text(
            'SELECT COUNT(*) FROM article_embeddings'
        )).scalar()
        # 컬럼 목록 확인
        cols = conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='article_embeddings' ORDER BY ordinal_position"
        )).fetchall()

    print(f'  article_embeddings: {cnt:,}건  크기: {size}')
    print('  컬럼 목록:')
    for col_name, col_type in cols:
        print(f'    {col_name:<20} {col_type}')
    print(f'\n  전체 소요시간: {time.time()-t0:.0f}s')
    print('='*55)


if __name__ == '__main__':
    print('=== pgvector 마이그레이션 시작 ===')
    engine = get_engine()
    print('✅ DB 연결 성공')
    run(engine)
    print('\n✅ 마이그레이션 완료')
