# TTA Trend Portal

TTA 직원용 ICT 뉴스 인텔리전스 포털을 Google Sites에 먼저 구성하기 위한 작업 폴더입니다.

이 폴더는 기존 운영 코드(`news_engine.py`, `main_app.py`)와 별도입니다. Google Sites는 직원용 진입점과 보고서 허브로 사용하고, 실제 검색/RAG/GraphRAG 실행은 별도 대시보드(`tta_staff_search_dashboard`) 또는 이후 배포되는 검색 엔진으로 연결합니다.

## 목표 구조

```text
Google Sites: TTA Trend Portal
  - 직원용 첫 화면
  - 오늘의 레이더 요약
  - AI 검색/이슈맵 바로가기
  - Google Docs/Excel 보고서 보관함
  - 활용 가이드

Streamlit Dashboard
  - Supabase/SQLite 검색
  - RAG 답변
  - GraphRAG식 관계 분석
  - 운영 점검

Supabase
  - news_articles
  - article_embeddings
  - 향후 report_artifacts, article_entities, issue_candidates
```

## 폴더 구성

| 경로 | 용도 |
|---|---|
| `google-sites-setup.md` | Google Sites 생성 및 게시 절차 |
| `site-map.md` | 사이트 메뉴 구조 |
| `page-copy/` | Google Sites 각 페이지에 붙여 넣을 문구 |
| `embeds/` | Sites 임베드용 HTML/iframe 코드 |
| `deploy/` | Streamlit 대시보드 내부 실행/자동시작 스크립트 |
| `templates/` | 보고서 링크와 Sites 링크 관리 템플릿 |
| `implementation-roadmap.md` | 최적안 단계별 추진 계획 |
| `site-config.json` | 포털 설정 초안 |

## 진행 순서

1. `google-sites-setup.md`에 따라 새 Google Sites 생성
2. `site-map.md` 기준으로 페이지 구성
3. `page-copy/` 문구를 각 페이지에 붙여 넣기
4. 홈에는 `embeds/home-cards.html`을 삽입하고 URL placeholder를 교체
5. `deploy/Run-Portal-Dashboard.cmd` 또는 내부 서버 배포 방식으로 Streamlit 대시보드 실행
6. `embeds/streamlit-embed.html`의 URL을 실제 대시보드 배포 URL로 교체
7. `templates/report-links.csv`에 Google Docs/Excel 링크 정리
8. Sites 공유 범위를 `tta.or.kr` 내부 사용자로 제한
9. 이후 `implementation-roadmap.md`에 따라 RAG/GraphRAG 기능을 단계적으로 연결

## 지금 만든 후 바로 할 일

```text
1. Google Sites 홈 페이지에 embeds/home-cards.html 삽입
2. STREAMLIT_URL, GOOGLE_DOCS_WEEKLY_URL, GOOGLE_SHEETS_OR_EXCEL_URL 교체
3. AI 검색 페이지에 embeds/streamlit-embed.html 삽입
4. 보고서 보관함 페이지에 embeds/report-library.html 삽입
5. 운영 현황 페이지에 embeds/status-summary.html 삽입
6. templates/sites-link-inventory.csv에 실제 링크 기록
```
