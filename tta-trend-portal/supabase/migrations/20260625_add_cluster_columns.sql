-- T11 기사 클러스터: news_articles에 클러스터 식별 컬럼 추가
-- cluster_articles.py 배치가 이 컬럼을 채운다. 멱등 (IF NOT EXISTS).
-- 배치보다 먼저 적용해야 함 (배치는 시작 시 같은 IF NOT EXISTS를 실행하므로 순서 무관하게 안전).

ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS cluster_id INTEGER;
ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS cluster_label TEXT;

-- 클러스터별 조회 가속 (선택)
CREATE INDEX IF NOT EXISTS idx_news_articles_cluster_id ON news_articles (cluster_id);
