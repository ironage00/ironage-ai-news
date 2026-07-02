# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다.
형식: [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/), 버전: MAJOR.MINOR.PATCH.MICRO

## [0.0.1.0] - 2026-07-02

### Added
- 선별 품질 평가 스크립트 `scripts/eval_selection.py` — 비ICT 유입률(상한/하한), AI 선별·분석 현황, 단별 뉴스레터 충족률(목표 20개 대비)을 마크다운으로 리포트. 선별 로직 변경 전후 비교의 기준 도구
- daily 파이프라인 종료 시 GitHub Actions Step Summary 자동 기록 — 수집→분류→중복제거→분석→단별 게재 건수를 실행 화면에서 바로 확인 가능
- daily 워크플로에 선별 품질 리포트 단계 추가 (매 실행 후 최근 7일 지표를 Step Summary에 표시)
- `NEWSLETTER_TARGET` 상수 도입 (단별 뉴스레터 목표 기사 수 단일 정의)

### Changed
- daily 워크플로에 `concurrency` 그룹 추가 — cron-job.org 중복 트리거 시 동시 실행으로 인한 Supabase 이중 쓰기 방지
- daily 워크플로에 `DATABASE_URL` 필수 검증 단계 추가 — 미설정 시 SQLite 폴백으로 데이터가 조용히 유실되는 사고 차단

### Removed
- `daily-supabase-sync.yml` 워크플로 삭제 — 참조하던 `tta-trend-portal/` 폴더가 독립 repo로 분리되면서 매일 실패하던 워크플로. 포털이 Supabase를 직접 읽으므로 동기화 자체가 불필요
- daily 워크플로의 SQLite 캐시 restore/save 단계 제거 — 수집이 Supabase에 직접 쓰므로 불필요
- daily 워크플로의 `cluster_articles.py` 호출 제거 — 스크립트가 포털 repo로 이동해 이미 실패 중이던 단계
