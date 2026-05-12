# 변경사항 보고서

**IRONAGE AI Analytics System — 인텔리전스 매트릭스 고도화 (Phase 1~4)**
**작성일:** 2026-04-28
**작업 기간:** 2026-04-27 ~ 2026-04-28
**작업 유형:** 기능 추가 (인텔리전스 매트릭스 고도화 · 신규 분석 모듈 3개 추가)
**참조 계획:** `doc/intelligence-matrix-upgrade-plan-20260427.md`

---

## 작업 개요

기존 인텔리전스 매트릭스가 단순 빈도 Top-5 테이블(삼성이 5번 등장 수준)만 제공하던 한계를 극복하여 4개 Phase로 고도화.
Phase 1(급등 알림·히트맵), Phase 3(지식 그래프), Phase 4(자율 인텔리전스 리포트)를 새로 구현하고, 기존 Phase 2(RAG 검색)와 통합.

---

## 수정·신규 파일 목록

| 파일 | 변경 유형 |
|------|---------|
| `main_app.py` | 수정 (인텔리전스 매트릭스 탭 3개 추가, 리포트 페이지 4번째 탭 추가) |
| `knowledge_graph.py` | **신규** (Phase 3 — 지식 그래프 모듈) |
| `auto_intel_report.py` | **신규** (Phase 4 — 자율 인텔리전스 리포트 오케스트레이터) |
| `requirements.txt` | 수정 (networkx, pyvis 추가) |
| `CLAUDE.md` | 수정 (신규 모듈 및 Phase 완료 현황 문서화) |

---

## Phase 1 — 급등 알림 · 공출현 히트맵 (2026-04-27)

**위치:** `main_app.py` 인텔리전스 매트릭스 섹션 (기존 L.1134~1168 대체)

### 변경 전
기업·기술·국가 Top 5를 3-column 데이터프레임으로만 표시.

### 변경 후
기존 Top-5 테이블을 유지하면서 하단에 3개 탭 추가:

```
st.tabs(["🔥 급등 알림", "🔲 공출현 히트맵", "🕸️ 지식 그래프"])
```

#### 탭 1 — 🔥 급등 알림
- `detect_surge_entities(news_current, news_prev, threshold=0.5, min_current=2)` 호출
- 이전 기간 대비 50% 이상 증가한 엔티티를 자동 감지
- 증가율에 따라 카드 색상 분류:
  - 신규 등장: `#e74c3c` (빨강)
  - +100% 이상: `#e67e22` (주황)
  - +50% 이상: `#f39c12` (노랑)
- `st.markdown(unsafe_allow_html=True)`로 HTML 카드 렌더링

#### 탭 2 — 🔲 공출현 히트맵
- `get_co_occurrence_matrix(news_list, top_companies=N, top_techs=N)` 호출
- 슬라이더로 상위 N개 조정 가능 (기업 3~10, 기술 3~10)
- `px.imshow()` Blues 컬러스케일, text_auto=True
- 행=기업, 열=기술, 값=같은 기사 내 공출현 횟수

---

## Phase 2 — RAG 의미 검색 (기존 모듈 유지)

**위치:** `rag_search.py` (기존), 뉴스 검색 페이지

Phase 1~4 고도화의 기반이 되는 벡터 검색 모듈. 이번 작업에서 신규 구현하지 않았으나 Phase 4 파이프라인에서 직접 호출.

| 함수 | 역할 |
|------|------|
| `embed_unprocessed_articles(limit)` | 미임베딩 기사 OpenAI 임베딩 처리 |
| `answer_with_rag(query, top_k, days)` | 코사인 유사도 검색 → GPT-4o 답변 생성 |
| `get_embedding_stats()` | 임베딩 처리 현황 통계 반환 |

---

## Phase 3 — 지식 그래프 (2026-04-27~28)

### 신규 파일: `knowledge_graph.py`

NetworkX + Pyvis 기반 엔티티 공출현 그래프 모듈. 총 5개 공개 함수.

#### 핵심 데이터 구조

기사의 `extracted_keywords` JSON에서 `related_companies`, `key_technologies`, `target_countries`를 파싱하여 엔티티 추출. 같은 기사에 함께 등장한 엔티티 쌍에 엣지 가중치 +1.

#### 노드 시각 스타일

| 유형 | 색상 | 모양 | 접두사 |
|------|------|------|--------|
| company | `#4a90e2` (파랑) | dot | 🏢 |
| tech | `#e74c3c` (빨강) | diamond | 🛠️ |
| country | `#2ecc71` (초록) | square | 🌍 |

#### 주요 함수

**`build_entity_graph(news_list, tech_synonyms, min_weight)`**
- `min_weight` 미달 엣지 및 고립 노드 자동 제거
- `tech_synonyms` 딕셔너리로 동의어 정규화 지원

**`render_graph_html(G, height)`**
- NetworkX → Pyvis Network 변환
- 다크 배경(`#0f1117`), barnesHut 물리 엔진, 인터랙티브 내비게이션
- `tempfile.mkstemp()`로 임시 파일 생성 후 HTML 읽기, `finally`에서 삭제
- 반환값: Streamlit `st.components.v1.html()` 직접 삽입 가능한 HTML 문자열

**`get_co_occurrence_matrix(news_list, top_companies, top_techs)`**
- 행=상위 기업, 열=상위 기술, 값=공출현 횟수
- 빈 데이터 시 빈 DataFrame 반환 (에러 없음)

**`detect_surge_entities(news_current, news_prev, threshold, min_current)`**
- `pct_change = (curr - prev) / prev`
- `prev == 0` 이면 `float('inf')` (신규 등장)
- 반환: `[{name, node_type, prev_count, curr_count, pct_change}, ...]` 내림차순 정렬

**`get_graph_stats(G)`**
- 노드 수, 엣지 수, 유형별 카운트, 상위 5개 중심성 노드, 밀도 반환

#### UI 구현 (main_app.py 탭 3)

```
build_entity_graph() → render_graph_html() → st.components.v1.html(height=540)
```
- 그래프 통계: 노드수 / 연결수 / 밀도 3-column 메트릭
- 최소 공출현 횟수 슬라이더 (1~5)
- 노드 범례 (기업·기술·국가 색상 안내)
- 중심성 상위 노드 expander

---

## Phase 4 — 자율 인텔리전스 리포트 (2026-04-28)

### 신규 파일: `auto_intel_report.py`

LangGraph 개념을 순수 Python 상태 기계로 구현. 실제 LangGraph 마이그레이션 시 각 `node_*` 함수를 `add_node()`에 그대로 등록 가능.

#### 설계 원칙
- **LangGraph 없이 동일 패턴 구현**: `langgraph`, `langchain` 패키지 의존성 없음
- **State dict 불변성**: 각 노드는 state를 받아 수정 후 반환
- **장애 격리**: 개별 노드 오류는 `state['errors']`에 누적, 치명적 실패 시에만 파이프라인 중단

#### State 구조 (`make_state()`)

| 키 | 타입 | 내용 |
|----|------|------|
| `period` | str | `'weekly'` \| `'monthly'` |
| `days` | int | 7 또는 30 |
| `news_current` | list | 현재 기간 분석 완료 기사 |
| `news_prev` | list | 이전 기간 기사 |
| `surges` | list | 급등 엔티티 목록 (최대 6개) |
| `rag_context` | dict | `{entity: {answer, sources}}` |
| `surge_narrative` | str | GPT-4o 생성 종합 내러티브 |
| `analysis_result` | dict | trend_analyzer 분석 결과 |
| `doc_url` | str | 생성된 Google Doc URL |
| `doc_id` | str | 문서 ID (batchUpdate용) |
| `email_sent` | bool | 이메일 발송 여부 |
| `log` | list | 진행 로그 |
| `errors` | list | 경고/오류 누적 |
| `_progress_cb` | callable | UI 진행 콜백 |

#### 파이프라인 노드 순서

```
node_load_data
    → node_detect_surges
    → node_rag_retrieve      ← 급등 엔티티 없으면 건너뜀
    → node_gen_narrative     ← 급등 엔티티 없으면 건너뜀
    → node_build_report
    → node_append_to_doc     ← doc_id 없거나 급등 엔티티 없으면 건너뜀
    → node_send_report       ← skip_email=True 이면 건너뜀
```

#### 주요 노드 상세

**`node_load_data`**
- `load_news_from_db(days)` 호출 후 `extracted_keywords` 있는 기사만 필터
- 이전 기간 = `days*2` 범위에서 cutoff 이전 기사 추출

**`node_rag_retrieve`**
- 급등 엔티티별 `embed_unprocessed_articles(limit=50)` → `answer_with_rag(query, top_k=3)` 순서로 실행
- 쿼리 형식: `"{name} 관련 최신 동향 및 표준화 시사점"`

**`node_gen_narrative`**
- GPT-4o 호출: 개조식(ㅇ) 3~5개 포인트, TTA 표준화 시사점 포함, 300자 이내
- 실패 시 폴백: 급등 엔티티 단순 목록으로 대체

**`node_append_to_doc`**
- Google Docs API `batchUpdate` → `insertText` at `index: 1`
- 삽입 내용: 구분선 + 급등 엔티티 목록 + AI 종합 분석 + RAG 상세 분석

#### 엔트리포인트

```python
run_auto_intel_report(
    period='weekly',          # 'weekly' | 'monthly'
    progress_cb=None,         # Streamlit st.write 등 콜백
    skip_email=False,         # True이면 이메일 건너뜀
) -> Dict[str, Any]           # 최종 State dict 반환
```

#### UI 구현 (main_app.py 리포트 페이지 탭 4)

리포트 페이지 탭 바 확장: 기존 3탭(일일/주간/월간) → 4탭 추가:

```python
col_tab1, col_tab2, col_tab3, col_tab4, col_spacer = st.columns([1, 1, 1, 1.4, 1])
# col_tab4: "🤖 자율 인텔리전스" 버튼 → st.session_state.report_tab = 'auto_intel'
```

탭 내용:
- 분석 기간 라디오 (주간 7일 / 월간 30일)
- 이메일 건너뜀 체크박스
- 활용 가능 기사 수 메트릭 (5개 미만 시 버튼 비활성화)
- 실시간 진행 로그 (`st.empty()` + monospace HTML, 최근 15줄)
- 완료 시 결과 요약 카드: 문서 링크 / 급등 엔티티 수 / RAG 검색 수 / 이메일 상태
- 급등 엔티티 목록 (아이콘 + 이름 + 변화율)
- 오류 expander

---

## requirements.txt 변경

```diff
+ # 지식 그래프 (Phase 3)
+ networkx>=3.0
+ pyvis>=0.3.2
```

---

## 데이터 흐름 (Phase 4 통합 후)

```
뉴스 DB (SQLite / extracted_keywords JSON)
        ↓
[Phase 3] knowledge_graph.detect_surge_entities()
        → 급등 엔티티 목록
        ↓
[Phase 2] rag_search.answer_with_rag()
        → 엔티티별 RAG 컨텍스트
        ↓
[Phase 4] GPT-4o 내러티브 생성
        ↓
trend_analyzer.generate_trend_report_doc()  ← 베이스 리포트 (Google Docs)
        ↓
Google Docs API batchUpdate                 ← 급등 섹션 삽입
        ↓
trend_analyzer.send_trend_report_email()    ← Gmail 발송 (선택)
```

---

## 검증 결과

| 항목 | 결과 |
|------|------|
| `main_app.py` 문법 검사 (`py_compile`) | ✅ 통과 |
| `knowledge_graph.py` 문법 검사 | ✅ 통과 |
| `auto_intel_report.py` 문법 검사 | ✅ 통과 |
| `from knowledge_graph import *` import 테스트 | ✅ 통과 |
| `from auto_intel_report import run_auto_intel_report` import 테스트 | ✅ 통과 |
| `from rag_search import answer_with_rag` import 테스트 | ✅ 통과 |
| Streamlit 앱 실행 (`localhost:8501`) | ✅ 정상 |

---

## Phase별 최종 상태

| Phase | 모듈 | UI 위치 | 상태 |
|-------|------|---------|------|
| Phase 1 — 급등 알림 + 히트맵 | `main_app.py` 인라인 | 대시보드 > 인텔리전스 매트릭스 > 탭1/2 | ✅ 완료 |
| Phase 2 — RAG 의미 검색 | `rag_search.py` | 뉴스 검색 페이지 | ✅ 기존 완료 |
| Phase 3 — 지식 그래프 | `knowledge_graph.py` | 대시보드 > 인텔리전스 매트릭스 > 탭3 | ✅ 완료 |
| Phase 4 — 자율 인텔리전스 | `auto_intel_report.py` | 리포트 > 🤖 자율 인텔리전스 탭 | ✅ 완료 |
