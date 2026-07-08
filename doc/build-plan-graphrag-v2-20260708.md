# 구축 계획 v2: GraphRAG → LangGraph → MCP + 시스템 성숙도 로드맵

- 작성일: 2026-07-08
- 상태: 검토 대기 (v1은 2026-06-15 APPROVED)
- Supersedes: `build-plan-graphrag-langgraph-mcp-20260615.md` (v1)
- 대상 repo: `ironage00/ironage-ai-news` (백엔드) + `ironage00/tta-trend-portal` (포털, 독립 private repo)

---

## 1. v1 이후 바뀐 것 (재계획의 근거)

| 변화 (v1 승인 후) | 계획에 미치는 영향 |
|---|---|
| **포털 독립 repo 분리** (2026-07-01) | v1의 Phase 1 타깃(`main_app.py`+`rag_search.py`)은 이제 관리자용. 직원이 실제 질문하는 곳은 포털 "질문형 분석실"(`dashboard/search.py`) → **타깃 변경** |
| 포털에 `graph_utils.build_edges()` 존재 (pandas 공출현 그래프) | v1의 NetworkX `build_entity_graph()` 대신 포털 자산 재사용 → 신규 의존성 0 |
| 유사 과거 이슈·TTA 기여 기회·출처등급·활용지표 기능 추가 (Phase 3 인텔리전스, 2026-07-06) | GraphRAG 결과를 얹을 UI 자리 이미 존재 |
| dual-AI(GPT-4o→Claude 검증) → GPT-4o 단독 축소 **진행 중** (미커밋) | Phase 2(LangGraph)가 감쌀 파이프라인이 변경 중 → 안정화 전 착수 금지 |
| 클러스터 스케줄 유실 사고(7/1~7/6, 435건) + `report_artifacts` 자동화 부재 발견 | "연결 지점이 늘면 조용히 고장" 패턴 확인 → 기반 정리를 Phase 0으로 선행 |
| 카드 피드백(👍/👎) 버튼 + `issue_actions.feedback` 컬럼 신설 | 피드백 데이터가 쌓이기 시작 — 소비하는 루프가 없음 (→ A-1) |
| PR + CI + 스모크 테스트 배포 관례 확립 (포털 repo) | 모든 Phase의 배포 경로로 채택 |

## 2. 재계획 원칙

1. **사용자가 있는 곳에 먼저** — GraphRAG는 포털(직원용)에 구현. 모노레포 `main_app.py`는 대상에서 제외.
2. **연결 지점을 늘리기 전에 기존 연결부터 고친다** — Phase 0 없이 Phase 1 착수 안 함.
3. **바뀌는 중인 것은 감싸지 않는다** — LangGraph 전환은 dual-AI 정리가 커밋·안정화된 후에만.
4. **측정 없이 개선 없음** — GraphRAG on/off 판정은 평가 하네스(B-3) 숫자로.

---

## 3. 로드맵 (Phase 0 → 3 + 병렬 트랙)

### Phase 0 — 기반 정리 (선행 필수, ~1일)

| # | 작업 | 위치 |
|---|---|---|
| 0-1 | `report_artifacts` 자동 등록 — `weekly-report.yml` 끝에 생성된 Docs URL을 Supabase에 upsert하는 단계 추가 | 모노레포 |
| 0-2 | `daily_sync.py` 실사용 여부 확정 → 죽은 코드면 제거, 아니면 포털 README 정정 (백엔드가 Supabase 직접 기록 확인됨 — `rag_search.embed_unprocessed_articles` 직접 호출) | 포털 |
| 0-3 | 월간 리포트 자동화 존재 여부 확인 — cron-job.org에 monthly 트리거 등록 여부 (**회원님 확인 필요**) | — |
| 0-4 | 본 문서(v2) + v1 문서 git 커밋 (v1은 로컬 untracked 상태였음) | 모노레포 `doc/` |
| 0-5 | **[C-7] 아침 캐시 워밍** — cron-job.org에 09:40 KST `https://tta-radar.streamlit.app/?embed=1` 핑 등록. 첫 접속자의 캐시 빌드 대기 제거. 코드 변경 없음, 10분 | cron-job.org |

**완료 기준**: 포털 "보고서 보관함"이 사람 손 없이 최신 주간 리포트를 표시.

### Phase 1a — 평가 하네스 [B-3] (GraphRAG 선행, ~1.5일)

v1 Phase 1 성공 기준("품질 비교")이 주관적이라는 약점 보완. **GraphRAG보다 먼저 구축.**

- 골든 질문셋 15~20개 (예: "NTN 최근 동향", "삼성-6G 관계", "양자내성암호 표준화 현황") + 각 질문의 기대 근거 기사(링크) 정의 → `dashboard/tests/golden_queries.json`
- 평가 스크립트: 각 질문을 `hybrid_search`로 실행 → 기대 기사가 top-k에 포함되는 비율(recall@k) + 응답 시간 기록
- CI에 주기 실행(주 1회 스케줄) — 선별 품질엔 `eval_selection.py`가 이미 있으나 RAG엔 회귀 검증이 없던 공백을 메움
- **용도**: GraphRAG on/off A/B 정량 비교, 이후 모델·프롬프트 변경 시 회귀 감지

### Phase 1b — GraphRAG (포털 질문형 분석실, ~2일)

v1의 설계 사상(벡터+그래프 쿼리 시점 결합, 플래그 롤백, graceful fallback) 유지. 구현 위치·재료만 포털 자산으로 교체.

```
질문 입력
  ↓ 엔티티 추출 (GPT-4o, 기존 build_answer의 client 재사용)
  ├─ hybrid_search()          ← 기존 그대로 (기사 풀 확보)
  └─ build_edges() 서브그래프  ← graph_utils 재사용 (관계 컨텍스트)
  ↓
build_answer()에 관계 컨텍스트 주입 → 답변 + "엔티티 관계 분석" 섹션
```

- 신규 파일: 포털 `dashboard/graph_rag.py` — v1의 `extract_query_entities()`/`get_graph_context()` 로직 이식, NetworkX 이웃 탐색 → edges DataFrame 필터로 대체
- UI 적용 범위: "근거 기반 답변 생성" 버튼 흐름에만 (버튼 클릭 시에만 GPT 2회 호출 — 상시 비용 증가 없음)
- 캐싱: `build_edges` 결과 `@st.cache_data(ttl=7200)` — 기존 `cached_tech_matrix` 관례와 동일
- 롤백: `USE_GRAPH_RAG` 환경변수 (v1 그대로). 기본 off 배포 → 평가 하네스 A/B 통과 후 on
- 성공 기준: ① 골든셋 recall@k 동등 이상 + 관계 질문 3종에서 개선, ② 지연 +3초 이내, ③ 그래프 비면 기존 답변 그대로(silent fallback)
- 배포: PR + CI + 스모크 테스트 (확립된 관례)

### Phase 1c — 데이터 축적 시작 [A-2, A-1] (GraphRAG 직후, ~2.5일)

축적형이라 빨리 심을수록 이득 — GraphRAG 평가 대기 기간에 병행 가능.

**[A-2] 일별 board 스냅샷 (~1일)**
- Supabase 테이블 `daily_board_snapshot(snapshot_date, article_link, rank, score, impact_level)` — 매일 6행
- 포털 repo에 스케줄 워크플로 추가 (cluster-articles.yml 패턴 재사용, 09:30 KST)
- 해금되는 것: "N일째 부상 ↗" 뱃지(이전에 인프라 부재로 보류), 신규 진입/이탈 표시, 주간 리포트 "뜨고 진 이슈" 섹션, "어제와 뭐가 달라졌나"에 대한 정확한 답

**[A-1] 피드백 루프 → 선별 연결 (~1.5일, 데이터 수십 건 축적 후 활성화)**
- 👎 누적 기사의 공통 패턴(출처·키워드) 주간 집계 → `filter_news_by_ai` 프롬프트에 few-shot 반례 주입
- 👍 비율을 `EXECUTIVE_BRIEF_WEIGHTS` 조정 근거로
- 근거: 선별 품질은 revert까지 갔던 검증된 아픔(이중게이트 과압축) — 사람 피드백 기반 조정이 재발 방지책
- 지금 심고 2~3주 데이터 축적 후 적용 (8월 초 예상)

### Phase 1.5 게이트 — 엔티티 정규화 [B-4] (GraphRAG 확대 전, ~2일)

- 문제: `extracted_keywords`의 dict/str 혼재, "삼성"/"삼성전자" 분산을 매 화면 `COMPANY_NORMALIZE`로 땜질 중
- 수정: 정규화를 분석 파이프라인(쓰기 시점) 1곳으로 이동 — 그래프·클러스터 라벨·매트릭스·GraphRAG 품질 동시 개선
- GraphRAG가 "확신에 찬 틀린 관계"를 답할 위험의 근본 처방 → **GraphRAG 기본 on 전환의 게이트 조건**

### Phase 2 — LangGraph 전환 (조건부, ~3일)

**착수 게이트**: ① dual-AI→GPT-4o 단독 축소 작업 커밋·배포 완료, ② 주간 리포트 2회 연속 정상 발송.

내용은 v1 유지 (설계 여전히 유효):
- `IntelState` TypedDict + `_progress_cb` 모듈 변수 분리
- 7개 노드 `add_node` 등록, 급등 없음 → END 조건부 엣지
- 의존성 충돌 검증 선행 (`pip check`), `langgraph>=0.2,<0.4` 핀닝
- `run_auto_intel_report()` API 유지 → Streamlit/Actions 무수정

단, "라이브러리 표준 준수" 목적은 즉시 가치가 낮음 → Phase 1 효과 확인 후 진행 여부 재판단 가능. 건너뛰어도 Phase 3에 지장 없도록 MCP 툴은 기존 함수를 직접 감싸는 설계.

### Phase 3 — MCP 서버화 (최소 범위, ~2일)

v1의 6개 툴 → **읽기 전용 4개로 축소**:

| 유지 | 제외 (사유) |
|---|---|
| `search_news` (GraphRAG) | `run_daily_collection` — cron-job.org 트리거와 이중 실행 위험 + 타임아웃 |
| `get_db_stats` | `run_intel_report` — 동일 + 이메일 발송 부작용 |
| `get_recent_articles` | |
| `get_surge_entities` | |

로컬 개발자 PC 전용(v1 그대로), 쓰기/발송 작업 전부 범위 외 → 타임아웃·이중실행·보안 문제가 한번에 소멸.

### 병렬 트랙 — 독립 항목 (아무 때나, 각 ~1일)

**[C-5] 긴급 이슈 즉시 알림 (계정 불필요)**
- 긴급도 9+ 이슈 발생 시 해당 단 리더에게 즉시 메일
- 기존 Gmail 인프라 + 워치독 패턴 재사용, `config.json`에 단별 수신자 추가
- 엔티티 팔로우(v1 이후 제안)는 계정 인프라 부재로 기각했으나, 단 단위 알림은 계정이 필요 없음
- "포털에 들어와야 안다" → "중요한 건 찾아온다"

**[C-6] AI 비용 관측**
- OpenAI 호출 5곳(선별·분석·임베딩·RAG·탑시그널)에 토큰 로깅 → 월간 자동 집계
- GraphRAG가 호출을 늘리기 **전에** 기준선 확보 — "도입 후 비용이 얼마 늘었나"에 답하기 위함

---

## 4. 타임라인 & 게이트

```
Phase 0  (기반+워밍)        ██ ~1일
   └ 게이트: 보관함 자동 갱신 확인
Phase 1a (평가 하네스)      ███ ~1.5일
Phase 1b (GraphRAG)         ████ ~2일
   └ 게이트: 골든셋 A/B 통과 → USE_GRAPH_RAG=on
Phase 1c (스냅샷+피드백루프) █████ ~2.5일 (1b 평가 대기와 병행 가능)
Phase 1.5 (엔티티 정규화)    ████ ~2일
   └ 게이트: GraphRAG 기본 on 전환 조건
Phase 2  (LangGraph)        ██████ ~3일
   └ 게이트: dual-AI 정리 커밋 + 주간 2회 정상
Phase 3  (MCP 최소)         ████ ~2일
병렬     (알림+비용관측)     ████ ~2일 (아무 때나)

핵심 경로 합계: ~12일 (v1 8.5일 + 기반/측정/축적 3.5일)
```

## 5. v1 대비 변경 요약

| 항목 | v1 (2026-06-15) | v2 (2026-07-08) |
|---|---|---|
| Phase 1 타깃 | 모노레포 `main_app.py` | 포털 질문형 분석실 |
| 그래프 엔진 | `knowledge_graph.py` (NetworkX) | 포털 `graph_utils.py` (pandas, 의존성 0) |
| Phase 0 | 없음 | 신설 (기반 신뢰성 + 캐시 워밍) |
| 품질 판정 | 5개 쿼리 수동 비교 | 평가 하네스(golden set) 정량 A/B |
| Phase 2 | 무조건 진행 | 게이트 조건부 (dual-AI 정리 후) |
| Phase 3 툴 | 6개 (수집·리포트 실행 포함) | 읽기 4개 |
| 신규 트랙 | — | 피드백 루프, 일별 스냅샷, 엔티티 정규화, 긴급 알림, 비용 관측 |
| 배포 경로 | 명시 없음 | PR + CI + 스모크 + 플래그 롤백 |

## 6. 오픈 질문 (v1에서 승계 + 신규)

1. (v1 승계) MCP 긴 작업 처리 — 읽기 전용 축소로 1차 해소, 2차에서 재검토
2. (v1 승계) LangGraph 체크포인팅 — 1차 인메모리만
3. (신규) 월간 리포트 자동화 — cron-job.org 트리거 등록 여부 회원님 확인 필요 (Phase 0-3)
4. (신규) 피드백 루프 활성화 시점 — 피드백 표본 최소 몇 건부터? (제안: 30건)
