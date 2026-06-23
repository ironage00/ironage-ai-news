-- TTA Intelligence Radar — 전체 Supabase 스키마
-- Supabase 대시보드 > SQL Editor 에 전체 붙여 넣고 실행합니다.
-- 이미 테이블이 있어도 안전하게 실행됩니다 (IF NOT EXISTS).

-- ──────────────────────────────────────────
-- 1. news_articles (메인 뉴스 테이블)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_articles (
    id              BIGSERIAL PRIMARY KEY,
    title           VARCHAR(500),
    link            VARCHAR(1000) UNIQUE NOT NULL,
    source          VARCHAR(100),
    published       TIMESTAMPTZ,
    collected_at    TIMESTAMPTZ DEFAULT NOW(),
    content         TEXT,
    quality_score   DOUBLE PRECISION,
    is_selected     BOOLEAN DEFAULT FALSE,
    is_analyzed     BOOLEAN DEFAULT FALSE,
    analysis_result TEXT,
    ai_model        VARCHAR(50),
    extracted_keywords TEXT,
    keywords        VARCHAR(500),
    ai_model_fallback VARCHAR(100),
    unit_id         INTEGER,
    unit_ids        TEXT
);

CREATE INDEX IF NOT EXISTS idx_news_collected   ON news_articles (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_analyzed    ON news_articles (is_analyzed);
CREATE INDEX IF NOT EXISTS idx_news_unit        ON news_articles (unit_id);
CREATE INDEX IF NOT EXISTS idx_news_published   ON news_articles (published DESC);

-- ──────────────────────────────────────────
-- 2. article_embeddings (RAG 검색용 벡터)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS article_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    article_id      INTEGER NOT NULL UNIQUE,
    embedding_json  TEXT NOT NULL,
    embedded_at     TIMESTAMPTZ DEFAULT NOW(),
    model_name      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_embed_article ON article_embeddings (article_id);

-- ──────────────────────────────────────────
-- 3. report_artifacts (보고서 보관함)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS report_artifacts (
    id                   BIGSERIAL PRIMARY KEY,
    report_type          TEXT NOT NULL,
    title                TEXT NOT NULL,
    period_start         DATE,
    period_end           DATE,
    google_doc_url       TEXT,
    excel_file_url       TEXT,
    source_article_count INTEGER DEFAULT 0,
    generated_at         TIMESTAMPTZ DEFAULT NOW(),
    owner                TEXT,
    visibility           TEXT DEFAULT 'tta_internal',
    status               TEXT DEFAULT 'draft',
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (report_type, title, period_start)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_period ON report_artifacts (period_end DESC, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_status ON report_artifacts (status, report_type);

-- ──────────────────────────────────────────
-- 4. issue_actions (표준화 대응 보드)
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS issue_actions (
    id              BIGSERIAL PRIMARY KEY,
    article_link    TEXT NOT NULL UNIQUE,
    article_id      INTEGER,
    article_title   TEXT,
    owner_unit      TEXT DEFAULT '공통',
    review_status   TEXT DEFAULT '미검토',
    action_memo     TEXT,
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actions_status  ON issue_actions (review_status, owner_unit);
CREATE INDEX IF NOT EXISTS idx_actions_updated ON issue_actions (updated_at DESC);
