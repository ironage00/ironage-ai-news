# TTA Radar

TTA 직원용 ICT 뉴스 인텔리전스 포털을 Streamlit 단독 앱으로 운영하기 위한 작업 폴더입니다.

이 폴더는 기존 운영 코드(`news_engine.py`, `main_app.py`)와 별도입니다. 운영 URL은 `https://tta-radar.streamlit.app`이며, Supabase DB를 데이터 원장으로 사용합니다.

## 목표 구조

```text
Streamlit Cloud: https://tta-radar.streamlit.app
  - 오늘의 레이더
  - 표준화 대응 보드
  - Google Docs/Excel 보고서 보관함
  - Supabase/SQLite 검색
  - RAG 답변
  - GraphRAG식 관계 분석

Supabase
  - news_articles
  - article_embeddings
  - report_artifacts
  - issue_actions
  - 향후 article_entities, issue_candidates
```

## 폴더 구성

| 경로 | 용도 |
|---|---|
| `dashboard/` | TTA Intelligence Radar v0.1 Streamlit 앱 |
| `data/` | 보고서 산출물 목록과 대응 보드 상태 저장 CSV |
| `deploy/` | Streamlit 대시보드 내부 실행/자동시작 스크립트 |
| `scripts/` | Supabase 보조 테이블 생성과 산출물 동기화 스크립트 |
| `supabase/` | 포털 전용 보조 테이블 SQL |
| `implementation-roadmap.md` | 최적안 단계별 추진 계획 |
| `site-config.json` | Streamlit 운영 설정 |

## 진행 순서

1. `https://tta-radar.streamlit.app` 접속 확인
2. Streamlit Cloud Secrets에 `DATABASE_URL`, `OPENAI_API_KEY`, `TTA_ALLOWED_EMAIL_DOMAIN` 설정
3. Supabase `news_articles`, `article_embeddings`, `report_artifacts`, `issue_actions` 상태 확인
4. `.github/workflows/daily-supabase-sync.yml`로 SQLite → Supabase 증분 동기화
5. 로컬 개발이 필요할 때만 `deploy/Run-Portal-Dashboard.cmd` 실행

## Supabase 공유 저장소 연결

Radar 앱은 운영 코드와 분리되어 동작합니다. Supabase 보조 테이블이 없으면
`data/report_artifacts.csv`, `data/issue_actions.csv`를 사용하고, 테이블이 있으면
Supabase를 우선 사용합니다.

```powershell
$env:DATABASE_URL="postgresql://..."
python "tta-trend-portal\scripts\setup_supabase_tables.py"
python "tta-trend-portal\scripts\sync_report_artifacts.py"
```

## 운영 URL

```text
https://tta-radar.streamlit.app
https://tta-radar.streamlit.app/?embed=1
```
