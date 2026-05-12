# 인텔리전스 매트릭스 고도화 방안

**IRONAGE AI Analytics System — 🧭 인텔리전스 매트릭스 (심층 엔티티 분석) 발전 로드맵**
**작성일:** 2026-04-27
**참조:** `main_app.py` L.1134 ~ L.1168 (인텔리전스 매트릭스 섹션)

---

## 현재 구조 및 한계

### 현재 동작
```python
# main_app.py L.1144 — 단순 빈도 카운팅
comp_top = Counter(all_companies).most_common(5)
tech_top = Counter(all_technologies).most_common(5)
country_top = Counter(all_countries).most_common(5)
```

3개 컬럼 데이터프레임으로 **"삼성이 5번 등장"** 수준만 표시.

### 한계
| 질문 | 현재 답변 가능 여부 |
|------|------------------|
| 이번 주 삼성 언급이 지난 주보다 증가했나? | ❌ |
| 삼성과 6G가 함께 언급된 기사는 몇 개? | ❌ |
| "5G 주파수 미국 vs 한국 비교 요약"해줘 | ❌ |
| 기업-기술-국가 간 연결 관계 시각화 | ❌ |

---

## 고도화 단계별 로드맵

### Phase 1 — 시계열 트렌드 + 공출현 히트맵
> **난이도:** ★☆☆☆☆ | **기간:** 1~2일 | **추가 패키지:** 없음

#### 1-1. 주간 엔티티 트렌드 차트
기존 DB에서 `collected_at` 기준으로 주 단위 집계 → Plotly `px.line()` 시각화

```python
# 예시 구조
weekly_trend = {
    '2026-W15': {'삼성': 4, '에릭슨': 2, '화웨이': 1},
    '2026-W16': {'삼성': 7, '에릭슨': 3, '화웨이': 0},
}
# → "삼성 3주 연속 증가" 자동 코멘트 생성 가능
```

#### 1-2. 기업 × 기술 공출현 히트맵
같은 기사에 함께 등장한 엔티티 쌍의 빈도를 Plotly `px.imshow()`로 표현

```
         6G   5G  Open RAN  NTN
삼성      12    8      3      1
에릭슨     5   11      9      2
노키아     3    7      6      4
```

#### 1-3. 자동 트렌드 코멘트 생성
```python
# 전주 대비 +50% 이상 급등 시 강조 표시
if this_week > last_week * 1.5:
    st.warning(f"📈 {entity} 언급 급증 (+{pct:.0f}%)")
```

**장점:** 기존 `extracted_keywords` JSON 재활용, 추가 인프라 불필요
**이게 전체 가치의 70%입니다. Phase 1부터 시작하세요.**

---

### Phase 2 — RAG (의미 기반 검색)
> **난이도:** ★★☆☆☆ | **기간:** 1~2주 | **추가 패키지:** `chromadb`, `openai`

#### 개념
RAG(Retrieval-Augmented Generation): 질문을 받으면 관련 기사를 벡터 검색으로 먼저 찾고, 찾은 기사를 컨텍스트로 LLM에 전달해 정확한 답변을 생성하는 방식.

#### 파이프라인
```
뉴스 본문 (SQLite)
    → 텍스트 임베딩 (text-embedding-3-small, $0.00002/기사)
    → 벡터 저장 (ChromaDB — 로컬 파일, 서버 불필요)
    ↓
사용자 질의: "5G 주파수 정책에서 미국 vs 한국 입장 차이 요약"
    → 질의 임베딩 → 유사 기사 k개 검색
    → GPT-4o가 검색 결과 기반으로 답변 생성
    → Streamlit 대화 UI로 표시
```

#### 비용 추정
| 항목 | 비용 |
|------|------|
| 기사 1,000건 임베딩 (최초 1회) | ~$0.02 |
| 질의당 검색 + GPT-4o 답변 | ~$0.01~0.03 |
| ChromaDB 서버 | 무료 (로컬) |

#### 구현 포인트
```python
import chromadb
from openai import OpenAI

# 인덱싱 (최초 1회 + 신규 기사마다)
collection.add(
    documents=[article['content']],
    metadatas=[{'title': article['title'], 'source': article['source']}],
    ids=[article['link']]
)

# 질의
results = collection.query(query_texts=[user_query], n_results=5)
# → results를 컨텍스트로 GPT-4o 호출
```

**트레이드오프:**
- 장점: 수백 건 뉴스에서 맥락 기반 질의 가능, 기존 DB 구조 그대로 유지
- 단점: 첫 인덱싱 시간 (1,000건 기준 약 2~3분), 신규 기사 증분 인덱싱 필요

---

### Phase 3 — Knowledge Graph (지식 그래프)
> **난이도:** ★★★☆☆ | **기간:** 1~2주 | **추가 패키지:** `networkx`, `pyvis`

#### 개념
지식 그래프: 엔티티(기업·기술·국가)를 노드로, 공출현/관계를 엣지로 표현한 네트워크. "삼성과 Ericsson을 모두 언급한 기사를 통해 연결된 기술은?"처럼 경로 탐색이 가능해짐.

#### 도구 선택

| 도구 | 특징 | 권장 상황 |
|------|------|---------|
| **NetworkX + Pyvis** | 로컬, 설치 즉시 사용, Streamlit HTML 임베드 | 현재 규모 (수천 건) |
| **Neo4j** | 본격 그래프 DB, Cypher 쿼리 언어 | 10만 건 이상, 복잡한 경로 탐색 |

#### NetworkX 구현 예시
```python
import networkx as nx
from pyvis.network import Network

G = nx.Graph()
# 기사에서 기업-기술 쌍 추출 → 엣지 가중치 누적
for article in articles:
    for company in article['companies']:
        for tech in article['technologies']:
            if G.has_edge(company, tech):
                G[company][tech]['weight'] += 1
            else:
                G.add_edge(company, tech, weight=1)

# Pyvis로 인터랙티브 시각화
net = Network(height='600px', bgcolor='#1a1a2e', font_color='white')
net.from_nx(G)
net.save_graph('graph.html')
# → Streamlit에 st.components.v1.html()로 삽입
```

**트레이드오프:**
- 장점: 인터랙티브 네트워크 뷰, 현재 매트릭스 대비 시각적 임팩트 큼, 3일이면 구현 가능
- 단점: 엔티티 정규화(동의어 처리)가 품질을 좌우함 (기존 `TECH_SYNONYMS` 확장 필요)

---

### Phase 4 — ReAct / LangGraph (자율 인텔리전스 리포트)
> **난이도:** ★★★★☆ | **기간:** 2~4주 | **추가 패키지:** `langgraph`, `langchain`

#### 개념
- **ReAct (Reasoning + Acting):** LLM이 "생각 → 도구 호출 → 관찰 → 다시 생각" 루프를 돌며 복잡한 분석을 단계적으로 수행하는 패턴
- **LangGraph:** 이 루프를 노드(상태)와 엣지(전이)로 정의하는 워크플로우 프레임워크. 분기·루프·병렬 실행을 그래프로 관리

#### 자율 인텔리전스 리포트 워크플로우
```
[Start: 리포트 생성 요청]
    ↓
[Node 1] 엔티티 트렌드 분석 도구 호출 (DB 쿼리)
    ↓
[Node 2] 이상 급등 탐지 (전주 대비 +50% 이상)
    ↓
[Node 3] RAG 검색 — 급등 엔티티 관련 기사 추출 (Phase 2 활용)
    ↓
[Node 4] GPT-4o 내러티브 생성
         "이번 주 핵심: 삼성전자의 6G 상용화 일정 발표(+180% 급증)..."
    ↓
[Node 5] Google Docs 리포트 자성 (기존 generate_google_doc_report 호출)
    ↓
[Node 6] Gmail 발송 (기존 send_gmail_report 호출)
    ↓
[End: 완료]
```

#### LangGraph 구조 스케치
```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(IntelligenceState)
workflow.add_node("analyze_trends", analyze_entity_trends)
workflow.add_node("detect_anomalies", detect_surge)
workflow.add_node("retrieve_articles", rag_search)   # Phase 2 연동
workflow.add_node("generate_narrative", llm_narrate)
workflow.add_node("create_report", create_google_doc) # 기존 함수 재사용
workflow.add_node("send_report", send_gmail)          # 기존 함수 재사용

workflow.set_entry_point("analyze_trends")
workflow.add_edge("analyze_trends", "detect_anomalies")
workflow.add_conditional_edges(
    "detect_anomalies",
    lambda s: "retrieve" if s["anomalies"] else "generate",
    {"retrieve": "retrieve_articles", "generate": "generate_narrative"}
)
# ...
app = workflow.compile()
```

**트레이드오프:**
- 장점: 완전 자동화된 주간/월간 인텔리전스 리포트, 분석 깊이 LLM 수준으로 향상
- 단점: Phase 2(RAG)가 선행되어야 의미 있음, 디버깅 복잡도 높음, LangGraph 학습 곡선

---

## 기술 스택 요약

| Phase | 핵심 기술 | 패키지 | 비고 |
|-------|---------|-------|------|
| 1 | 시계열 집계 + 히트맵 | `plotly`, `pandas` | 기존 스택 |
| 2 | RAG 의미 검색 | `chromadb`, `openai` | 로컬 벡터 DB |
| 3 | 지식 그래프 | `networkx`, `pyvis` | 서버 불필요 |
| 4 | 자율 리포트 에이전트 | `langgraph`, `langchain` | Phase 2+3 선행 필요 |

---

## 권장 구현 순서

```
[현재] 단순 빈도 카운팅 (Top 5 테이블)
   ↓ 1~2일
[Phase 1] 시계열 트렌드 + 공출현 히트맵 + 급등 알림
          → 즉시 착수 권장. 추가 비용 없음.
   ↓ 1~2주
[Phase 2] RAG 의미 검색 (ChromaDB + text-embedding-3-small)
          → 대화형 질의 인터페이스 추가
   ↓ 1~2주
[Phase 3] NetworkX 지식 그래프 시각화
          → 엔티티 관계망 인터랙티브 뷰
   ↓ 필요 시
[Phase 4] LangGraph 자율 인텔리전스 리포트
          → Phase 2+3 완성 후 접착제 역할
```

---

## 데이터 소스 현황

현재 `extracted_keywords` JSON에 이미 포함된 필드:

```json
{
  "keywords": [...],
  "related_companies": ["삼성전자", "에릭슨"],
  "key_technologies": ["6G", "Open RAN"],
  "target_countries": ["한국", "미국"],
  "impact_level": "High",
  "tta_action_item": "...",
  "standardization_gap": "..."
}
```

Phase 1~3 구현에 필요한 엔티티 데이터는 **이미 DB에 누적 중**입니다.
추가 AI 분석 없이 기존 데이터만으로 Phase 1은 즉시 구현 가능합니다.
