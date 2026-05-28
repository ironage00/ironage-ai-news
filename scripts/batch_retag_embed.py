"""
배치 작업: 과거 미태깅 기사 소급 unit_id 태깅 + 임베딩 커버리지 확대

실행:
    python scripts/batch_retag_embed.py [--retag] [--embed] [--all]
    --retag : unit_id=None 기사에 키워드 매칭으로 단 태깅
    --embed : is_analyzed=True & 임베딩 없는 기사 임베딩
    --all   : 둘 다 실행 (기본값)
"""
import sys, os, json, argparse, time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# ── 공통 DB 연결 ────────────────────────────────────────────
from sqlalchemy import create_engine, text


def get_engine():
    """
    DATABASE_URL을 환경변수 → streamlit_secrets.toml 순서로 읽어
    SQLAlchemy 엔진을 반환. 동시에 os.environ['DATABASE_URL']도 세팅하여
    이후 news_engine.py가 lazy-import될 때 Supabase로 연결되도록 한다.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        toml_path = ROOT / 'streamlit_secrets.toml'
        if toml_path.exists():
            import tomllib
            with open(toml_path, 'rb') as f:
                secrets = tomllib.load(f)
            db_url = secrets.get('DATABASE_URL')
    if not db_url:
        raise RuntimeError('DATABASE_URL을 찾을 수 없습니다.')
    if db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)

    # ★ 환경변수에도 저장 → news_engine lazy import 시 Supabase로 연결
    os.environ['DATABASE_URL'] = db_url

    return create_engine(db_url, pool_pre_ping=True, pool_size=5)


# ══════════════════════════════════════════════════════════════
# Task 1: 소급 unit_id 태깅
# ══════════════════════════════════════════════════════════════

def _classify(title: str, kw_map: dict) -> int | None:
    """키워드 매칭으로 primary unit_id 반환. 없으면 None."""
    tl = title.lower()
    best_uid, best_cnt = None, 0
    for uid, kws in kw_map.items():
        cnt = sum(1 for kw in kws if kw in tl)
        if cnt > best_cnt:
            best_cnt, best_uid = cnt, uid
    return best_uid if best_cnt > 0 else None


def run_retag(engine, batch_size: int = 500):
    print('\n' + '='*60)
    print('▶ Task 1: 미태깅 기사 소급 unit_id 태깅')
    print('='*60)

    with engine.connect() as conn:
        # 키워드 맵 로드
        r = conn.execute(text(
            'SELECT unit_id, keywords FROM user_settings '
            'WHERE unit_id IS NOT NULL AND keywords IS NOT NULL ORDER BY unit_id'
        ))
        kw_map = {}
        for uid, kw_json in r.fetchall():
            kws = json.loads(kw_json) if kw_json else []
            kw_map[uid] = [kw.lower() for kw in kws if kw]

        if not kw_map:
            print('  키워드 맵이 비어 있습니다. user_settings 확인 필요.')
            return

        print(f'  키워드 맵: { {k: len(v) for k, v in kw_map.items()} }')

        # 전체 미태깅 수
        total_untagged = conn.execute(
            text("SELECT COUNT(*) FROM news_articles WHERE unit_id IS NULL")
        ).scalar()
        print(f'  미태깅 기사: {total_untagged:,}건\n')

    if total_untagged == 0:
        print('  이미 모두 태깅 완료.')
        return

    tagged_cnt    = 0
    unmatched_cnt = 0
    processed_cnt = 0
    last_id       = 0          # ★ ID-cursor (OFFSET 방식 대신)
    t0 = time.time()

    while True:
        # ★ OFFSET 대신 id > last_id 커서 사용 → 중간에 행이 사라져도 안전
        with engine.connect() as conn:
            rows = conn.execute(text(
                'SELECT id, title FROM news_articles '
                'WHERE unit_id IS NULL AND id > :last_id '
                'ORDER BY id LIMIT :batch'
            ), {'last_id': last_id, 'batch': batch_size}).fetchall()

        if not rows:
            break

        last_id = rows[-1][0]   # 다음 페이지 커서 갱신

        # 분류
        updates = []   # (unit_id, article_id)
        for art_id, title in rows:
            uid = _classify(title or '', kw_map)
            if uid is not None:
                updates.append((uid, art_id))
            else:
                unmatched_cnt += 1

        # 배치 UPDATE
        if updates:
            with engine.begin() as conn:
                conn.execute(
                    text('UPDATE news_articles SET unit_id = :uid WHERE id = :aid'),
                    [{'uid': u, 'aid': a} for u, a in updates]
                )
            tagged_cnt += len(updates)

        processed_cnt += len(rows)
        elapsed = time.time() - t0
        pct = min(100, round(100 * processed_cnt / total_untagged))
        print(f'  [{pct:3d}%] 처리 {processed_cnt:,}/{total_untagged:,}건  '
              f'태깅 {tagged_cnt:,}건  미매칭 {unmatched_cnt:,}건  '
              f'({elapsed:.0f}s)')

    print(f'\n  태깅 완료: {tagged_cnt:,}건 태깅 / {unmatched_cnt:,}건 미매칭 유지')

    # 결과 확인
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT u.display_name, COUNT(na.id) "
            "FROM news_articles na LEFT JOIN units u ON na.unit_id = u.id "
            "GROUP BY u.display_name ORDER BY COUNT(na.id) DESC"
        ))
        print('\n  단별 현황 (태깅 후):')
        for row in r.fetchall():
            print(f'    {(row[0] or "단없음"):<20} {row[1]:>7,}건')


# ══════════════════════════════════════════════════════════════
# Task 2: 임베딩 커버리지 확대
# ══════════════════════════════════════════════════════════════

def run_embed(engine):
    print('\n' + '='*60)
    print('▶ Task 2: 분析 완료 기사 임베딩 배치 처리')
    print('='*60)

    # 임베딩 전 현황
    with engine.connect() as conn:
        before = conn.execute(text(
            'SELECT COUNT(*) FROM news_articles WHERE is_analyzed=TRUE '
            'AND id NOT IN (SELECT article_id FROM article_embeddings)'
        )).scalar()
        emb_before = conn.execute(
            text('SELECT COUNT(*) FROM article_embeddings')
        ).scalar()
        total_art  = conn.execute(
            text('SELECT COUNT(*) FROM news_articles')
        ).scalar()

    print(f'  임베딩 전: {emb_before:,}건 / 전체: {total_art:,}건')
    print(f'  처리 대상: {before:,}건 (분析O / 임베딩X)')

    if before == 0:
        print('  이미 모두 임베딩 완료.')
        return

    # ★ os.environ['DATABASE_URL']이 세팅된 뒤 lazy import
    #    → news_engine이 Supabase로 초기화됨
    try:
        from rag_search import embed_unprocessed_articles
    except ImportError as e:
        print(f'  ❌ rag_search 임포트 실패: {e}')
        return

    # embed_unprocessed_articles는 EMBED_BATCH_SIZE(50)씩 처리
    # remaining == 0 또는 cnt == 0 될 때까지 반복 (iterations 계산 불필요)
    BATCH = 50
    total_added = 0
    batch_num = 0
    t0 = time.time()

    while True:
        # 현재 미임베딩 수 재확인
        with engine.connect() as conn:
            remaining = conn.execute(text(
                'SELECT COUNT(*) FROM news_articles WHERE is_analyzed=TRUE '
                'AND id NOT IN (SELECT article_id FROM article_embeddings)'
            )).scalar()
        if remaining == 0:
            print('  모든 기사 임베딩 완료.')
            break

        cnt = embed_unprocessed_articles(limit=BATCH)
        batch_num += 1
        elapsed = time.time() - t0
        print(f'  [배치{batch_num}] 이번 {cnt}건  남은 {remaining:,}건  ({elapsed:.0f}s)')
        if cnt == 0:
            # 더 처리할 것이 없거나 오류
            break
        total_added += cnt

        # API 과부하 방지
        time.sleep(0.3)

    # 최종 결과
    with engine.connect() as conn:
        emb_after = conn.execute(
            text('SELECT COUNT(*) FROM article_embeddings')
        ).scalar()

    added = emb_after - emb_before
    elapsed = time.time() - t0
    print(f'\n  임베딩 완료: {emb_before:,} -> {emb_after:,}건 (+{added:,}건)  ({elapsed:.0f}s)')
    print(f'  커버리지: {emb_before/total_art*100:.1f}% -> {emb_after/total_art*100:.1f}%')


# ══════════════════════════════════════════════════════════════
# Task 3: 전체 기사 임베딩 (quality 무관, unit_id=None 포함)
# ══════════════════════════════════════════════════════════════

def run_embed_all(engine, batch_size: int = 100):
    """
    분析 여부/품질/단 배정 무관 — 모든 미임베딩 기사를 배치 임베딩.
    텍스트 우선순위: 분析결과 > 본문 > 제목
    직접 SQL INSERT로 ORM 세션 없이 명시적 커밋.
    """
    print('\n' + '='*60)
    print('▶ Task 3: 전체 미임베딩 기사 임베딩 (quality 무관)')
    print('='*60)

    # ★ lazy import — DATABASE_URL 세팅 후여야 Supabase로 연결됨
    try:
        from rag_search import _embed_texts, EMBEDDING_MODEL
    except ImportError as e:
        print(f'  ❌ rag_search 임포트 실패: {e}')
        return

    import datetime as dt

    with engine.connect() as conn:
        total = conn.execute(text(
            'SELECT COUNT(*) FROM news_articles na '
            'LEFT JOIN article_embeddings ae ON na.id = ae.article_id '
            'WHERE ae.article_id IS NULL'
        )).scalar()
        emb_before = conn.execute(
            text('SELECT COUNT(*) FROM article_embeddings')
        ).scalar()
        total_art = conn.execute(
            text('SELECT COUNT(*) FROM news_articles')
        ).scalar()

    if total == 0:
        print('  이미 모두 임베딩 완료.')
        return

    # 스토리지 경고 (18KB/row 기준)
    est_mb = total * 18 // 1024
    print(f'  임베딩 전: {emb_before:,}건 / 전체: {total_art:,}건')
    print(f'  처리 대상: {total:,}건  (예상 추가 용량: ~{est_mb:,} MB)')
    if est_mb > 400:
        print(f'  ⚠️  Supabase 용량 주의 — 대용량 작업입니다.')

    last_id   = 0
    processed = 0
    inserted  = 0
    errors    = 0
    t0 = time.time()

    while True:
        # LEFT JOIN으로 미임베딩 기사만 ID 커서 방식으로 조회
        with engine.connect() as conn:
            rows = conn.execute(text(
                'SELECT na.id, na.title, na.content, na.analysis_result, na.is_analyzed '
                'FROM news_articles na '
                'LEFT JOIN article_embeddings ae ON na.id = ae.article_id '
                'WHERE ae.article_id IS NULL AND na.id > :last_id '
                'ORDER BY na.id LIMIT :batch'
            ), {'last_id': last_id, 'batch': batch_size}).fetchall()

        if not rows:
            break

        last_id = rows[-1][0]

        # 텍스트 구성
        texts = []
        for _, title, content, analysis_result, is_analyzed in rows:
            if is_analyzed and analysis_result:
                body = f"{title}\n{analysis_result[:500]}"
            elif content:
                body = f"{title}\n{content[:500]}"
            else:
                body = title or ''
            texts.append(body)

        # 임베딩 API 호출
        try:
            embeddings = _embed_texts(texts)
        except Exception as e:
            print(f'  ❌ API 오류 (last_id={last_id}): {e}  — 2초 대기 후 재시도')
            time.sleep(2)
            last_id = rows[0][0] - 1   # 이 배치 재시도를 위해 커서 되돌리기
            errors += 1
            if errors >= 5:
                print('  ❌ 연속 오류 5회 — 중단')
                break
            continue
        else:
            errors = 0   # 성공 시 오류 카운터 리셋

        # DB INSERT (ON CONFLICT DO NOTHING)
        now = dt.datetime.now(dt.timezone.utc)
        insert_rows = [
            {
                'article_id': row[0],
                'embedding':  str(emb),   # '[f1, f2, ...]' → PostgreSQL vector literal
                'model_name': EMBEDDING_MODEL,
                'embedded_at': now,
            }
            for row, emb in zip(rows, embeddings)
        ]
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    'INSERT INTO article_embeddings '
                    '(article_id, embedding, model_name, embedded_at) '
                    'VALUES (:article_id, CAST(:embedding AS vector), :model_name, :embedded_at) '
                    'ON CONFLICT (article_id) DO NOTHING'
                ), insert_rows)
            inserted += len(rows)
        except Exception as e:
            print(f'  ❌ INSERT 오류: {e}')
            break

        processed += len(rows)
        elapsed = time.time() - t0
        pct = min(100, round(100 * processed / total))
        rate = processed / elapsed if elapsed > 0 else 1
        eta  = int((total - processed) / rate)
        print(f'  [{pct:3d}%] {processed:,}/{total:,}건  +{inserted:,}  '
              f'({elapsed:.0f}s, 잔여 ~{eta//60}분{eta%60}초)')

        time.sleep(0.1)   # API 과부하 방지

    # 최종 결과
    with engine.connect() as conn:
        emb_after = conn.execute(
            text('SELECT COUNT(*) FROM article_embeddings')
        ).scalar()

    added   = emb_after - emb_before
    elapsed = time.time() - t0
    print(f'\n  임베딩 완료: {emb_before:,} → {emb_after:,}건 (+{added:,}건)  ({elapsed:.0f}s)')
    print(f'  커버리지: {emb_before/total_art*100:.1f}% → {emb_after/total_art*100:.1f}%')


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='미태깅 소급 태깅 + 임베딩 배치')
    parser.add_argument('--retag',     action='store_true', help='unit_id 태깅만 실행')
    parser.add_argument('--embed',     action='store_true', help='분析완료 임베딩만 실행')
    parser.add_argument('--embed-all', action='store_true', help='전체 미임베딩 기사 임베딩 (quality 무관)')
    args = parser.parse_args()

    # 플래그 없으면 retag + embed (기본값); --embed-all은 명시적으로만 실행
    no_flag  = not args.retag and not args.embed and not args.embed_all
    do_retag = args.retag     or no_flag
    do_embed = args.embed     or no_flag
    do_embed_all = args.embed_all

    t_total = time.time()

    # ★ get_engine()이 DATABASE_URL을 env에 세팅해야 embed의 lazy import 전에 실행돼야 함
    engine = get_engine()
    print('✅ DB 연결 성공')

    if do_retag:
        run_retag(engine)

    if do_embed:
        run_embed(engine)

    if do_embed_all:
        run_embed_all(engine)

    print(f'\n전체 완료  (총 {time.time()-t_total:.0f}s)')
