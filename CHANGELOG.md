# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다.
형식: [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/), 버전: MAJOR.MINOR.PATCH.MICRO

## [0.3.3.0] - 2026-07-03

### Added
- `scripts/rebalance_unit_keywords.py` — 단별 키워드 재설계 반영 스크립트 (Fix B).
  dry-run 기본(변경 diff + 배정 수 시뮬레이션), `--confirm`으로 DB 반영. keywords만
  교체하고 RSS·수신자 등은 보존. 프로덕션 unit_settings에 1회 반영 완료.

### Changed (프로덕션 DB unit_settings — 코드 아닌 데이터)
- **표준혁신단**: 단독 `AI` 제거(AI 기사 폭주 원인). 인공지능 PG 4대 소관 영역
  (기반기술·모델·시스템·신뢰성) 결합어 41개로 재구성 — 일반 AI 기사는 배제하고
  AI 표준화 특화 기사만. 제목 기준 배정 725→21로 정상화(본문 기반 재배정이 추가 보강).
- **AI융합단**: AI 일반 홈으로 `AI`/`인공지능` 유지, `피지컬 AI`는 표준혁신단으로 이관.
  `생성형 AI`·`LLM`·`온디바이스 AI` 추가.
- **전파네트워크단**: `ITS`(영어 단어 'its' 충돌) → `C-ITS`/`지능형교통`으로 교체.
  `NTN`·`비지상`·`스펙트럼`·`스타링크`·`기지국`·`mmWave` 보강. 배정 147→113
  (감소분은 잘못 걸리던 영어 'its' 기사 제거).

## [0.3.2.0] - 2026-07-03

### Fixed
- **단 분류 키워드 매칭에 단어 경계 도입 (Fix A)** — `_classify_article_to_units`가
  순수 ASCII 키워드('ai', '5g', 'ax', 'iot' 등)를 부분 문자열이 아니라 단어 경계로
  매칭. 'ai'가 'Ukrainian'·'against', 'ax'가 'tax', '6g'가 '6GHz'(주파수 단위) 속에서
  오매칭되던 문제 해소. 한글 키워드(위성통신 등)는 조사·복합어 때문에 부분 문자열 유지.
  실측: 표본 3,000건에서 'ai' 오매칭 145건, 'ax' 14건 제거.
- 정규식은 `functools.lru_cache`로 키워드별 1회만 컴파일.

### Notes
- 'ITS'(지능형교통) 키워드는 영어 단어 'its'(소유격)와 철자가 같아 단어 경계로도
  구분 불가 — 표준 단어로 등장하면 여전히 매칭됨. 이는 키워드 자체를 바꿔야
  해결(후속 Fix B: 'ITS' → 'C-ITS'/'지능형교통'). 회귀 감지 테스트로 한계 문서화.

## [0.3.1.0] - 2026-07-03

### Changed
- **Phase 2.6 선별 후보 상한 150 → 300 상향** — 그날 고유 후보 526건 중 150건만
  AI에 전달돼 376건이 검토조차 안 되던 문제 완화. gpt-4o-mini는 input이 저렴하고
  컨텍스트 128k라 후보를 늘려도 비용·용량 부담이 작다(선별 응답 길이는 목표 개수에만
  좌우됨). `CONFIG.selection_candidates_max`로 배포 없이 조정 가능(50~2000). 크게 잡으면
  사실상 전체 후보를 AI에 전달.
- `daily_global_select_count`(목표 개수) 상한 클램프를 상수(150)가 아닌 실제 후보 수로
  변경 — 후보보다 큰 목표를 요청하는 모순 제거.

## [0.3.0.0] - 2026-07-03

### Added
- **임베딩 기반 교차언어·패러프레이즈 중복 제거 (Phase D2)** — Phase 2.6 AI 선별 직전,
  후보 풀을 text-embedding-3-small 코사인 유사도로 클러스터링해 같은 사건의 표현만 다른
  기사를 병합. 제목 단어 Jaccard(Phase 2.5)가 못 잡는 "Nvidia Launches..." vs
  "NVIDIA rolls out..." 류, 한/영 교차 중복을 제거. 기존 `rag_search`의 임베딩
  인프라(`_embed_texts`/`_cosine_similarity`) 재사용 — 신규 인프라 없음.
- 임계값 0.70은 실제 중복 쌍(Nvidia 패러프레이즈 0.80~0.92, 한/영 앤트로픽 0.84) vs
  서로 다른 쌍(최대 0.595)으로 실측 검증 — 38건 실데이터에서 오병합 0건(38→34).
  `CONFIG.selection_embed_dedup`(기본 True)·`selection_embed_threshold`(기본 0.70)로 조정.
- 실행당 임베딩 배치 1회(후보 ~150개) 추가. 실패 시 원본 유지(파이프라인 보호).
  섀도 모드에서는 후보에만 적용(unit_pools 불변)되어 뉴스레터 영향 없음.

### Notes
- 제목만으로는 표현이 크게 다른 일부 패러프레이즈(예: Meta AI컴퓨팅 3종 변형 0.62~0.68)는
  안전 임계값 아래라 잡지 못함 — 이를 잡으려 임계값을 낮추면 서로 다른 기사(예: Meta
  클라우드 vs SoftBank 클라우드 0.595)를 병합할 위험이 있어 보수적 0.70 채택. 본문 기반
  중복 제거는 후속 과제.

## [0.2.2.0] - 2026-07-03

### Fixed
- **매주 자동 발송되는 주간 리포트가 잘못된(레거시) 형식으로 나가던 문제** — 매주 월요일
  cron-job.org가 트리거하는 `weekly-report.yml`이 `python news_engine.py weekly`
  (`trend_analyzer.py`의 구 형식 — GPT-4o+Claude 검증만 있고 급등 엔티티·RAG 분석 없음)를
  호출하고 있었다. `auto_intel_report.py --period weekly`(🤖 자율 인텔리전스, Phase 4)로
  전환 — 급등 엔티티 감지(`knowledge_graph.py`) + RAG 심층분석(`rag_search.py`) 섹션이
  Google Docs에 추가된 완전한 형식으로 매주 자동 발송됨. 기존 필요 시크릿으로 충분(추가
  설정 불필요) — `node_build_report`가 내부적으로 동일한 `trend_analyzer.py` 기반 리포트를
  생성한 뒤 급등 분석을 덧붙이는 구조라 CLAUDE_API_KEY 등 기존 시크릿을 그대로 재사용.
- 레거시 `news_engine.py weekly`(`run_weekly_report()`) 경로는 코드에 그대로 유지 —
  자동 실행 경로만 전환됨

## [0.2.1.0] - 2026-07-03

### Changed
- **선별 모델 gpt-4o-mini 다운그레이드 (Phase B4)** — Phase 2.6 전역 선별(`ai_select_articles`,
  제목+요약 목록에서 번호를 고르는 판단 작업)만 `gpt-4o-mini`로 전환. 심층분석
  (`analyze_news_with_ai`) 등 다른 OpenAI 사용처는 `gpt-4o` 그대로 유지.
- `CONFIG.selection_openai_model`로 즉시 모델 재정의 가능(문제 시 롤백용).
- 실측 비교(동일 25건 후보 — 실제 후보 20건 + 명백한 쓰레기 5건): 두 모델 모두 쓰레기
  0건 선별, 최우선 항목(score 5) 완전 일치, 상위 15개 중 80% 일치(차이는 score 1~2
  경계선에서만 발생) — 섀도 모드이므로 뉴스레터 영향 없음.

## [0.2.0.0] - 2026-07-03

### Changed
- **저장 시점 이동 (Phase C1)** — 일일 파이프라인이 더 이상 룰 분류 직후 원시 후보
  전체(단별 수백 건)를 저장하지 않는다. 이제 본문 스크래핑과 AI 심층분석까지 성공한
  기사만 `_upsert_analyzed_article()`로 삽입된다. 결과적으로 Supabase에는 실제로
  분석된(=AI가 다룬) 기사만 남고, 분석되지 않는 잡음 기사는 애초에 저장되지 않는다.
- Phase 2.6 활성 모드의 `is_selected` 표기가 분석 성공 삽입 시점에 함께 기록되도록 변경 —
  재실행 시 무한 누적되던 문제와 수동 큐레이션 구분 불가 문제를 함께 해소(단, 한 번이라도
  선별된 기사는 재분석에서 미선별로 나와도 강등되지 않음)

### Added
- **30일 보존 정책 (Phase C2)** — 매 실행 종료 시 30일 넘게 미선별·미분석 상태로 남은
  기사를 자동 정리(`cleanup_stale_unselected_articles`). 레거시 저장 경로·마이그레이션
  이전 잔여 데이터에 대한 백스톱. NULL 플래그 row는 `.is_(False)`로 안전하게 보호
- 저장 로직 통합 테스트 6종(`tests/test_storage.py`) — upsert 삽입/갱신, is_selected
  비강등, 교차 단 제목 중복 스킵, NULL 플래그 보호, C2 커트오프 경계

### Notes
- 주말(토·일) 미작동은 코드가 아니라 외부 cron-job.org 스케줄이 평일로만 설정된 것이
  원인. 코드에는 이미 "주말=수집·분석·저장만 하고 메일 스킵 / 월요일=주말 누적분 병합
  발송" 로직이 있으며, C1/C2는 이 흐름과 호환됨(`is_analyzed=True` 기준 유지). 주말에도
  수집·저장이 돌게 하려면 cron-job.org 스케줄을 매일로 변경 필요

## [0.1.2.0] - 2026-07-03

### Added
- `scripts/cleanup_junk_articles.py` — 기존에 쌓인 비ICT 기사(차익실현·코스피·스포츠·
  연예 등) 일회성 정리 스크립트 (Phase C3). 프로덕션 Stage 0 필터
  (`_collect_stage_filter_reason`)를 과거 데이터에 소급 적용. 기본은 dry-run,
  `--confirm` 플래그 없이는 절대 삭제하지 않음. AI 선별(`is_selected`)·심층분석
  (`is_analyzed`) 결과물은 절대 삭제 대상에서 제외
- 프로덕션 Supabase에 1회 실행 — 330건 삭제 (재실행 시 0건, 멱등성 확인)

## [0.1.1.0] - 2026-07-03

### Changed
- **본문 추출 trafilatura 도입** — `get_article_content()`가 trafilatura(정밀 추출)를
  우선 시도하고 부족할 때만 기존 BeautifulSoup 휴리스틱으로 폴백. 실측에서 BeautifulSoup이
  본문을 놓치던 사이트(aitimes 29자→3,573자, techtimes 86자→17,603자)를 복구해
  분석 실패로 인한 단별 뉴스레터 미달을 줄임
- 응답 본문을 bytes로 각 추출기에 전달해 EUC-KR/CP949 한국 사이트의 인코딩 깨짐(mojibake) 감소
- 응답 본문 5MB 스트리밍 상한 도입 — 거대·악성 페이지의 파싱 폭주로 워커가 묶이는 것 차단

### Fixed
- **정상 기사 오탈락 버그** — 본문 추출 실패 판정이 `'실패'` 같은 흔한 단어를 substring으로
  검사해, "발사 실패" 등 정상 기사가 잘못 버려지던 문제 수정. 실패 신호를 센티넬 기반
  `_is_extraction_failed()`로 일원화(4개 소비 지점 통일)

### 후속 (별도 PR)
- `get_article_content()` SSRF 방어 (리다이렉트 최종 목적지 IP 검증) — 리뷰에서 지적된
  기존 네트워크 보안 이슈로, 정상 사이트를 깨지 않도록 전용 작업으로 분리

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
