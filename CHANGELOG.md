# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다.
형식: [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/), 버전: MAJOR.MINOR.PATCH.MICRO

## [0.1.0.0] - 2026-07-02

### Added
- **Phase 2.6 전역 AI 선별 (섀도 모드)** — daily 파이프라인에 정책 중요도 기반 AI 선별 재도입.
  `selection_mode` 설정(shadow=기록만·기본 / active=뉴스레터 반영 / off)으로 제어.
  섀도 기간 동안 `selection_log` 테이블에 선별 결과·점수(1~5)·사유를 기록하고,
  실제 발송 결과와 비교 검증 후 활성화하는 구조 (과거 revert 사고 재발 방지)
- 제목+요약 기반 선별, JSON 구조화 응답(점수·사유), 단별 하한 보장(기본 15개, 과압축 방지),
  단별 라운드로빈 후보 병합(큰 단이 후보 상한을 독식하는 편향 방지)
- 외부 피드 제목의 프롬프트 인젝션 완화 (제어문자 제거 + 데이터/지시 분리 시스템 메시지)
- pytest 테스트 인프라 도입 — 선별 순수 함수 24개 테스트 + CI 테스트 워크플로 (`test.yml`)
- 선별 품질 리포트에 "AI 선별 시뮬레이션" 섹션 추가 (섀도 로그 vs 실제 발송 비교)

### Changed
- `selection_log` 90일 보존 정책 (매 실행 시 자동 정리)
- 선별 설정값 안전 파싱 (오타 시 파이프라인 중단 대신 기본값 + 경고)

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
