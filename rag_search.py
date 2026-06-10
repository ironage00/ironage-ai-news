"""
IRONAGE AI Analytics System v5.0
RAG(Retrieval-Augmented Generation) 뉴스 검색 모듈

기능:
- 뉴스 기사를 OpenAI 임베딩으로 벡터화하여 ArticleEmbedding 테이블에 저장
- 자연어 쿼리로 의미적으로 유사한 기사 검색 (코사인 유사도)
- 검색 결과를 바탕으로 GPT-4o가 종합 답변 생성
"""

import json
import math
import re
import html
import datetime
from typing import List, Dict, Optional


def _clean_title(text: str) -> str:
    """RSS 제목의 HTML 태그·엔티티·파이프 접두사를 제거"""
    if not text:
        return ''
    text = html.unescape(text)           # &amp; → &, &lt; → < 등
    text = re.sub(r'<[^>]+>', '', text)  # <b>, </b> 등 태그 제거
    text = re.sub(r'\s*\|\s*\S+\s*$', '', text)   # 끝 "| 출처명" 패턴 제거
    return text.strip()

from sqlalchemy import text as _sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from news_engine import (
    log_info, log_warning, log_error,
    get_db_session, NewsArticle, ArticleEmbedding,
    DB_ENGINE,
    performance_monitor,
    get_openai_client,
    OPENAI_MODEL_DEFAULT,
)

# PostgreSQL(Supabase) 여부 — pgvector INSERT/SEARCH 분기에 사용
_IS_PG = not DB_ENGINE.url.drivername.startswith('sqlite')

EMBEDDING_MODEL = 'text-embedding-3-small'
EMBED_BATCH_SIZE = 200    # 한 번에 임베딩할 기사 수
TOP_K_DEFAULT = 5         # 기본 검색 결과 수


# ==============================================================================
# --- 유사도 계산 ---
# ==============================================================================

def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """두 벡터 간 코사인 유사도 계산"""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ==============================================================================
# --- 임베딩 생성 및 저장 ---
# ==============================================================================

def _embed_texts(texts: List[str]) -> List[List[float]]:
    """OpenAI API로 텍스트 리스트 임베딩 (배치)"""
    client = get_openai_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


@performance_monitor
def embed_unprocessed_articles(limit: int = EMBED_BATCH_SIZE) -> int:
    """
    아직 임베딩되지 않은 기사를 배치로 임베딩하여 DB에 저장.
    우선순위: ① is_analyzed=True (title+analysis_result) → ② content 있음 (title+content)
              → ③ quality_score>0.5 (title만)
    Returns: 새로 임베딩된 기사 수
    """
    log_info(f"🔍 미임베딩 기사 처리 중 (최대 {limit}개)...")

    try:
        with get_db_session() as session:
            embedded_ids = {
                row.article_id
                for row in session.query(ArticleEmbedding.article_id).all()
            }
            not_embedded = ~NewsArticle.id.in_(embedded_ids) if embedded_ids else True

            # ① 분석 완료 기사 (가장 고품질)
            analyzed = (
                session.query(NewsArticle)
                .filter(NewsArticle.is_analyzed == True, not_embedded)
                .order_by(NewsArticle.collected_at.desc())
                .limit(limit)
                .all()
            )

            remaining = limit - len(analyzed)
            analyzed_ids = {a.id for a in analyzed}

            # ② 본문 저장된 미분석 기사 (방안 B로 스크래핑 본문 저장된 경우)
            with_content = []
            if remaining > 0:
                with_content = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.is_analyzed != True,
                        NewsArticle.content != None,
                        NewsArticle.content != '',
                        not_embedded,
                        ~NewsArticle.id.in_(analyzed_ids),
                    )
                    .order_by(NewsArticle.collected_at.desc())
                    .limit(remaining)
                    .all()
                )
                remaining -= len(with_content)
                content_ids = {a.id for a in with_content}
            else:
                content_ids = set()

            # ③ 품질 필터 통과 미분석 기사 (제목만 — 낮은 품질이지만 커버리지 확대)
            quality_only = []
            if remaining > 0:
                quality_only = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.is_analyzed != True,
                        (NewsArticle.content == None) | (NewsArticle.content == ''),
                        NewsArticle.quality_score > 0.5,
                        not_embedded,
                        ~NewsArticle.id.in_(analyzed_ids | content_ids),
                    )
                    .order_by(NewsArticle.collected_at.desc())
                    .limit(remaining)
                    .all()
                )

            articles = analyzed + with_content + quality_only

            if not articles:
                log_info("  ✅ 모든 기사 임베딩 완료 상태")
                return 0

            # 임베딩 텍스트 구성: 가용 정보 우선순위에 따라 분기
            texts = []
            for a in articles:
                if a.is_analyzed and a.analysis_result:
                    body = f"{a.title}\n{a.analysis_result[:500]}"
                elif a.content:
                    body = f"{a.title}\n{a.content[:500]}"
                else:
                    body = a.title or ''
                texts.append(body)

            embeddings = _embed_texts(texts)

            # ON CONFLICT DO NOTHING: 이미 임베딩된 기사는 건너뜀 (UniqueViolation 방지)
            now = datetime.datetime.now(datetime.timezone.utc)
            rows = [
                {
                    "article_id": article.id,
                    # PostgreSQL: str(list) → '[0.1,0.2,...]' (pgvector literal 호환)
                    # SQLite: json.dumps(list) → '[0.1, 0.2, ...]' (JSON text)
                    "embedding": str(emb) if _IS_PG else json.dumps(emb),
                    "model_name": EMBEDDING_MODEL,
                    "embedded_at": now,
                }
                for article, emb in zip(articles, embeddings)
            ]
            if rows:
                if _IS_PG:
                    # PostgreSQL + pgvector: vector(1536) 타입으로 직접 INSERT
                    session.execute(_sa_text(
                        'INSERT INTO article_embeddings '
                        '(article_id, embedding, model_name, embedded_at) '
                        'VALUES (:article_id, CAST(:embedding AS vector), :model_name, :embedded_at) '
                        'ON CONFLICT (article_id) DO NOTHING'
                    ), rows)
                else:
                    # SQLite 폴백: JSON 텍스트 그대로 저장
                    stmt = pg_insert(ArticleEmbedding).values(rows)
                    stmt = stmt.on_conflict_do_nothing()
                    session.execute(stmt)

        count = len(articles)
        n_analyzed = len(analyzed)
        n_content = len(with_content)
        n_title_only = len(quality_only)
        log_info(
            f"  ✅ {count}개 임베딩 완료 "
            f"(분석완료:{n_analyzed} / 본문있음:{n_content} / 제목만:{n_title_only})"
        )
        return count

    except Exception as e:
        log_error(f"❌ 임베딩 처리 실패: {e}")
        return 0


# ==============================================================================
# --- 유사 기사 검색 ---
# ==============================================================================

@performance_monitor
def search_similar_articles(
    query: str,
    top_k: int = TOP_K_DEFAULT,
    days: Optional[int] = None,
    min_similarity: float = 0.25,
    unit_id: Optional[int] = None,
) -> List[Dict]:
    """
    자연어 쿼리와 의미적으로 유사한 기사를 검색한다.

    Args:
        query: 검색 질문
        top_k: 반환할 최대 기사 수
        days: None이면 전체, 숫자면 최근 N일 내 기사만
        min_similarity: 최소 유사도 임계값
        unit_id: None이면 전체 단, 숫자면 해당 단 기사만

    Returns:
        List[Dict]: 유사도 내림차순 기사 목록
    """
    log_info(f"🔎 RAG 검색: '{query[:50]}...' (top_k={top_k}, unit_id={unit_id})")

    try:
        # 쿼리 임베딩
        query_emb = _embed_texts([query])[0]

        if _IS_PG:
            # ── PostgreSQL + pgvector: <=> 코사인 거리 연산자 (HNSW 인덱스 활용) ──
            query_str = str(query_emb)   # '[0.1, 0.2, ...]' 형식

            # 필터 조건 동적 구성
            where_clauses = ['1=1']
            params: dict = {
                'q':       query_str,
                'fetch_k': top_k * 10,   # 후보 여유있게 확보 후 min_similarity 필터링
            }
            if days:
                cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                where_clauses.append('na.collected_at >= :cutoff')
                params['cutoff'] = cutoff
            if unit_id is not None:
                where_clauses.append('na.unit_id = :unit_id')
                params['unit_id'] = unit_id

            where_sql = ' AND '.join(where_clauses)
            sql = _sa_text(f"""
                SELECT na.id, na.title, na.link, na.source, na.published,
                       na.analysis_result,
                       1 - (ae.embedding <=> CAST(:q AS vector)) AS similarity
                FROM   article_embeddings ae
                JOIN   news_articles na ON ae.article_id = na.id
                WHERE  {where_sql}
                ORDER  BY ae.embedding <=> CAST(:q AS vector)
                LIMIT  :fetch_k
            """)

            with DB_ENGINE.connect() as conn:
                db_rows = conn.execute(sql, params).fetchall()

            if not db_rows:
                log_warning("  ⚠️ 검색 결과 없음.")
                return []

            results = []
            for r in db_rows:
                sim = float(r.similarity)
                if sim < min_similarity:
                    continue
                results.append({
                    'id':              r.id,
                    'title':           _clean_title(r.title or ''),
                    'link':            r.link or '',
                    'source':          r.source or '',
                    'published':       r.published.strftime('%Y-%m-%d') if r.published else '',
                    'analysis_result': r.analysis_result or '',
                    'similarity':      round(sim, 4),
                })
                if len(results) >= top_k:
                    break

        else:
            # ── SQLite 폴백: Python 코사인 유사도 계산 (기존 방식) ──
            with get_db_session() as session:
                q = (
                    session.query(ArticleEmbedding, NewsArticle)
                    .join(NewsArticle, NewsArticle.id == ArticleEmbedding.article_id)
                )
                if days:
                    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                    q = q.filter(NewsArticle.collected_at >= cutoff)
                if unit_id is not None:
                    q = q.filter(NewsArticle.unit_id == unit_id)
                rows = q.all()

            if not rows:
                log_warning("  ⚠️ 임베딩된 기사가 없습니다.")
                return []

            scored = []
            for emb_row, article in rows:
                vec = json.loads(emb_row.embedding)
                sim = _cosine_similarity(query_emb, vec)
                if sim >= min_similarity:
                    scored.append((sim, article))
            scored.sort(key=lambda x: x[0], reverse=True)

            results = []
            for sim, a in scored[:top_k]:
                results.append({
                    'id':              a.id,
                    'title':           _clean_title(a.title or ''),
                    'link':            a.link or '',
                    'source':          a.source or '',
                    'published':       a.published.strftime('%Y-%m-%d') if a.published else '',
                    'analysis_result': a.analysis_result or '',
                    'similarity':      round(sim, 4),
                })

        log_info(f"  ✅ {len(results)}개 결과 반환")
        return results

    except Exception as e:
        log_error(f"❌ RAG 검색 실패: {e}")
        return []


# ==============================================================================
# --- 키워드 텍스트 검색 (하이브리드용) ---
# ==============================================================================

def _keyword_search_articles(
    query: str,
    top_k: int = 15,
    days: Optional[int] = None,
    unit_id: Optional[int] = None,
) -> List[Dict]:
    """
    쿼리 토큰을 title / analysis_result 에서 LIKE 매칭하여 DB 전체를 커버.
    임베딩 없는 기사도 검색 대상에 포함.
    ICT 키워드 재필터로 비관련 기사 제거.
    unit_id: None이면 전체 단, 숫자면 해당 단 기사만.
    """
    from news_engine import CONFIG, DEFAULT_ICT_KEYWORDS
    from sqlalchemy import or_

    _stopwords = {
        '이다', '이며', '하여', '있다', '하는', '에서', '에서의', '에', '를', '이', '가',
        '은', '는', '으로', '의', '기술', '동향', 'and', 'the', 'for', 'with', 'that',
    }
    tokens = [t for t in re.findall(r'[가-힣]{2,}|[a-zA-Z0-9]{2,}', query)
              if t.lower() not in _stopwords]
    if not tokens:
        return []
    tokens = tokens[:12]

    # ICT 관련성 판단용 키워드 (소문자)
    ict_kw = [k.lower() for k in (CONFIG.get('ict_keywords') or DEFAULT_ICT_KEYWORDS)]

    try:
        with get_db_session() as session:
            base_q = session.query(NewsArticle)
            if days:
                cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                base_q = base_q.filter(NewsArticle.collected_at >= cutoff)
            if unit_id is not None:
                base_q = base_q.filter(NewsArticle.unit_id == unit_id)

            conditions = []
            for tok in tokens:
                conditions.append(NewsArticle.title.ilike(f'%{tok}%'))
                conditions.append(NewsArticle.analysis_result.ilike(f'%{tok}%'))

            rows = (
                base_q
                .filter(or_(*conditions))
                .order_by(NewsArticle.collected_at.desc())
                .limit(top_k * 10)   # 충분한 풀 확보 후 ICT 필터 적용
                .all()
            )

        # 매칭 토큰 비율 점수 계산 + ICT 관련성 확인
        scored = []
        for a in rows:
            clean = _clean_title(a.title or '')
            searchable = f"{clean} {a.analysis_result or ''}".lower()
            hit = sum(1 for t in tokens if t.lower() in searchable)
            if hit == 0:
                continue
            # ICT 키워드가 제목 또는 분석결과에 하나라도 있어야 포함
            has_ict = any(k in searchable for k in ict_kw)
            if not has_ict:
                continue
            scored.append((hit / len(tokens), a, clean))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, a, clean in scored[:top_k]:
            results.append({
                'id': a.id,
                'title': clean,
                'link': a.link or '',
                'source': a.source or '',
                'published': a.published.strftime('%Y-%m-%d') if a.published else '',
                'analysis_result': a.analysis_result or '',
                'content': a.content or '',
                'similarity': round(score * 0.6, 4),
                'search_type': 'keyword',
            })
        return results

    except Exception as e:
        log_error(f"❌ 키워드 검색 실패: {e}")
        return []


# ==============================================================================
# --- RAG 종합 답변 생성 ---
# ==============================================================================

@performance_monitor
def answer_with_rag(
    query: str,
    top_k: int = TOP_K_DEFAULT,
    days: Optional[int] = None,
    unit_id: Optional[int] = None,
) -> Dict:
    """
    하이브리드 검색(임베딩 유사도 + 키워드 매칭)으로 커버한 후
    GPT-4o로 종합 답변을 생성한다.

    Args:
        query: 검색 질문
        top_k: 반환할 최대 기사 수
        days: None이면 전체, 숫자면 최근 N일 내 기사만
        unit_id: None이면 전체 단, 숫자면 해당 단 기사만

    Returns:
        Dict: {answer, sources, query}
    """
    unit_label = f"unit_id={unit_id}" if unit_id is not None else "전체"
    log_info(f"💬 RAG 하이브리드 검색: '{query[:60]}' ({unit_label})")

    # ① 미임베딩 기사 처리 (최대 50개씩)
    embed_unprocessed_articles(limit=EMBED_BATCH_SIZE)

    # ② 임베딩 유사도 검색
    emb_results = search_similar_articles(query, top_k=top_k, days=days, unit_id=unit_id)
    for r in emb_results:
        r['search_type'] = 'embedding'

    # ③ 키워드 텍스트 검색 (단 필터 적용)
    kw_results = _keyword_search_articles(query, top_k=top_k, days=days, unit_id=unit_id)

    # ④ 병합 · 중복 제거 — 임베딩 우선, 같은 기사 재등장 시 스코어 최대값 유지
    emb_ids = {r['id'] for r in emb_results}
    merged: List[Dict] = list(emb_results)
    for r in kw_results:
        if r['id'] not in emb_ids:
            merged.append(r)

    # ⑤ 분석 결과 있는 기사 우선 + 유사도 내림차순
    merged.sort(
        key=lambda x: (1 if x.get('analysis_result') else 0, x.get('similarity', 0)),
        reverse=True,
    )

    # 컨텍스트에 사용할 기사: 분석 결과 보유 우선 최대 top_k*2개
    ctx_articles = merged[:top_k * 2]

    if not ctx_articles:
        return {
            'answer': '관련 기사를 찾지 못했습니다. 다른 키워드로 검색해보세요.',
            'sources': [],
            'query': query,
        }

    # ⑥ 컨텍스트 구성 — 링크 포함, body 없으면 제목만으로도 포함
    context_parts = []
    for i, art in enumerate(ctx_articles, 1):
        body = art.get('analysis_result') or art.get('content') or ''
        link_str = art.get('link', '')
        context_parts.append(
            f"[기사 {i}] {art['title']} ({art['source']}, {art['published']})"
            + (f" | URL: {link_str}" if link_str else "")
            + (f"\n{body[:500]}" if body else "")
        )
    context = "\n\n".join(context_parts)

    n_emb = sum(1 for r in ctx_articles if r.get('search_type') == 'embedding')
    n_kw  = sum(1 for r in ctx_articles if r.get('search_type') == 'keyword')
    log_info(f"  ✅ 컨텍스트 구성: 총 {len(ctx_articles)}건 (임베딩:{n_emb} / 키워드:{n_kw})")

    prompt = f"""당신은 TTA(한국정보통신기술협회) ICT 분석 전문가입니다.
아래 {len(ctx_articles)}개 뉴스 기사를 **빠짐없이 모두** 참고하여 질문에 포괄적으로 답하십시오.

[질문]
{query}

[참고 기사 — 총 {len(ctx_articles)}건]
{context}

[답변 형식 — 반드시 아래 구조를 따르십시오]

## 주요 동향 요약
(2~3문장으로 핵심 트렌드 정리)

## 국가·기관별 상세 동향

소제목 계층 순서: 국가/지역 → 기관(표준기구·정부·협회) → 기업
날짜 정렬: 각 소제목 내에서 날짜 오름차순 (오래된 기사 먼저)
기사 형식: 기사 하나당 ㅇ 한 문장, 줄바꿈으로 구분

작성 예시:
### 🌐 국제기구
#### ITU-T
ㅇ (한 문장 요약) [(출처명, YYYY-MM-DD)](URL)
ㅇ (한 문장 요약) [(출처명, YYYY-MM-DD)](URL)
#### 3GPP
ㅇ (한 문장 요약) [(출처명, YYYY-MM-DD)](URL)

### 🇰🇷 한국
#### 기관 (TTA, 과기정통부, ETRI 등)
ㅇ (한 문장 요약) [(출처명, YYYY-MM-DD)](URL)
#### 기업 (삼성전자, SK텔레콤, KT 등)
ㅇ (한 문장 요약) [(출처명, YYYY-MM-DD)](URL)

### 🇺🇸 미국 / 🇪🇺 유럽 등 (해당하는 경우만)
#### (기관명 또는 기업명)
ㅇ (한 문장 요약) [(출처명, YYYY-MM-DD)](URL)

## 시사점 및 전망
(국내 ICT 표준화 관점에서 2~3가지 핵심 시사점, ㅇ 항목으로 정리)

[작성 규칙]
1. {len(ctx_articles)}건 기사를 **모두** 언급 — 하나라도 누락 금지
2. 기사 하나 = 반드시 ㅇ 한 문장, 다음 기사는 새 줄
3. 출처: URL 있으면 [(출처명, YYYY-MM-DD)](URL), 없으면 (출처명, YYYY-MM-DD)
4. 기사에 없는 내용 추측 금지
"""

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_MODEL_DEFAULT,
            messages=[
                {"role": "system", "content": "당신은 ICT 뉴스 분석 전문가입니다. 제공된 기사를 단 하나도 빠짐없이 모두 활용하여 포괄적이고 정확한 답변을 작성하세요."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4000,
        )
        answer = response.choices[0].message.content.strip()
        log_info("  ✅ RAG 답변 생성 완료")
        return {
            'answer': answer,
            'sources': merged[:top_k * 2],  # UI에는 전체 참고 기사 노출
            'query': query,
        }

    except Exception as e:
        log_error(f"❌ RAG 답변 생성 실패: {e}")
        return {
            'answer': f'답변 생성 중 오류가 발생했습니다: {e}',
            'sources': articles,
            'query': query,
        }


# ==============================================================================
# --- 임베딩 현황 조회 ---
# ==============================================================================

def get_embedding_stats() -> Dict:
    """임베딩 현황 통계 반환 (방안 A+B 확장 기준)"""
    try:
        with get_db_session() as session:
            total_analyzed = session.query(NewsArticle).filter(NewsArticle.is_analyzed == True).count()
            total_with_content = session.query(NewsArticle).filter(
                NewsArticle.is_analyzed != True,
                NewsArticle.content != None,
                NewsArticle.content != '',
            ).count()
            # quality_score 태그 기사 (filter_news_by_ai 수정 이후 수집 기사)
            total_quality_tagged = session.query(NewsArticle).filter(
                NewsArticle.is_analyzed != True,
                (NewsArticle.content == None) | (NewsArticle.content == ''),
                NewsArticle.quality_score > 0.5,
            ).count()
            # 미태그 미분석 기사 (기존 0점 기사 — ICT 키워드 필터 전 상한)
            total_untagged = session.query(NewsArticle).filter(
                NewsArticle.is_analyzed != True,
                NewsArticle.quality_score <= 0.5,
            ).count()
            total_quality = total_quality_tagged + total_untagged
            total_embeddable = total_analyzed + total_with_content + total_quality
            total_embedded = session.query(ArticleEmbedding).count()
            pending = total_embeddable - total_embedded
            return {
                'total_analyzed': total_analyzed,
                'total_with_content': total_with_content,
                'total_quality': total_quality,
                'total_embeddable': total_embeddable,
                'total_embedded': total_embedded,
                'pending_embed': max(0, pending),
            }
    except Exception as e:
        log_error(f"❌ 임베딩 통계 조회 실패: {e}")
        return {
            'total_analyzed': 0, 'total_with_content': 0, 'total_quality': 0,
            'total_embeddable': 0, 'total_embedded': 0, 'pending_embed': 0,
        }
