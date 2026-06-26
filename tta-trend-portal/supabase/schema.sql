-- TTA Radar supplemental tables.
-- Apply this to Supabase/PostgreSQL after the existing news tables are ready.

CREATE TABLE IF NOT EXISTS report_artifacts (
    id BIGSERIAL PRIMARY KEY,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    period_start DATE,
    period_end DATE,
    google_doc_url TEXT,
    excel_file_url TEXT,
    source_article_count INTEGER DEFAULT 0,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    owner TEXT,
    visibility TEXT DEFAULT 'tta_internal',
    status TEXT DEFAULT 'draft',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (report_type, title, period_start)
);

CREATE INDEX IF NOT EXISTS idx_report_artifacts_period
    ON report_artifacts (period_end DESC, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_report_artifacts_status
    ON report_artifacts (status, report_type);

CREATE TABLE IF NOT EXISTS issue_actions (
    id BIGSERIAL PRIMARY KEY,
    article_link TEXT NOT NULL UNIQUE,
    article_id INTEGER,
    article_title TEXT,
    owner_unit TEXT DEFAULT '공통',
    review_status TEXT DEFAULT '미검토',
    action_memo TEXT,
    updated_by TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issue_actions_status
    ON issue_actions (review_status, owner_unit);

CREATE INDEX IF NOT EXISTS idx_issue_actions_updated
    ON issue_actions (updated_at DESC);

COMMENT ON TABLE report_artifacts IS 'TTA Radar Google Docs and Excel report registry.';
COMMENT ON TABLE issue_actions IS 'TTA Radar standardization response board state.';
