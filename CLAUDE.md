# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 시스템 개요

IRONAGE AI Analytics System — ICT/통신 분야 뉴스를 자동 수집·AI 분석하여 주간/월간 리포트를 Google Docs로 생성하고 Gmail로 발송하는 Python 기반 시스템 (TTA 표준화본부 내부용).

## 실행 명령어

```bash
# 웹 대시보드 실행
streamlit run main_app.py

# CLI 모드
python news_engine.py daily    # 뉴스 수집 및 AI 분석
python news_engine.py weekly   # 주간 트렌드 리포트 생성 + 이메일 발송
python news_engine.py monthly  # 월간 종합 리포트 생성 + 이메일 발송
python news_engine.py test     # DB 통계 확인

# 패키지 설치
pip install -r requirements.txt
```

## 아키텍처

### 파일 구조
| 파일 | 역할 |
|------|------|
| `news_engine.py` | 핵심 엔진 — 뉴스 수집, DB, AI 분석, 리포트, 이메일 모두 포함. `main_app.py`가 이 모듈을 import함. CLI 진입점. |
| `main_app.py` | Streamlit 웹 대시보드 — `news_engine.py`의 함수들을 import해서 GUI로 노출 |
| `rag_search.py` | **Phase 2** — RAG 의미 검색 모듈. OpenAI text-embedding-3-small으로 기사 임베딩 → SQLite 저장 → 코사인 유사도 검색 → GPT-4o 답변 생성. `embed_unprocessed_articles()`, `answer_with_rag()` |
| `knowledge_graph.py` | **Phase 3** — 지식 그래프 모듈. NetworkX로 엔티티(기업·기술·국가) 공출현 그래프 빌드, Pyvis로 인터랙티브 HTML 생성. `build_entity_graph()`, `render_graph_html()`, `get_co_occurrence_matrix()`, `detect_surge_entities()` |
| `auto_intel_report.py` | **Phase 4** — 자율 인텔리전스 리포트 오케스트레이터. LangGraph-inspired 순수 Python 상태 기계(7-node pipeline): 데이터 로드 → 급등 감지 → RAG 검색 → AI 내러티브 → 리포트 생성 → 문서 추가 → 이메일 발송. `run_auto_intel_report()` |
| `trend_analyzer.py` | 트렌드 분석 + Google Docs 리포트 생성 + Gmail 발송 |
| `main6.93t.py` | **레거시 독립 스크립트** (v3 시대). 현재는 사용하지 않음. `news_engine.py`로 대체됨. |
| `data/config.json` | 런타임 설정 (API 키, 이메일 주소, RSS URL 등). 없으면 `news_engine.py` 내 하드코딩 값 사용. |
| `credentials.json` | Google OAuth2 클라이언트 인증 정보 (초기 인증 시 필요) |
| `token.json` | Google OAuth2 액세스 토큰 (첫 인증 후 자동 생성됨) |
| `data/news.db` | SQLite 데이터베이스 |

### 데이터 흐름
```
Google Alerts RSS + Naver API
        ↓ get_news_data()
  filter_news_by_ai()  ← OpenAI로 품질 필터링 (상위 20%)
        ↓
  save_news_to_db()    → SQLite (news_articles 테이블)
        ↓
  analyze_news_with_ai() ← GPT-4o / Claude / Gemini / Perplexity
        ↓
  run_weekly_report() / run_monthly_report()
        ↓
  Google Docs 리포트 + Gmail HTML 이메일
```

### DB 스키마 (`NewsArticle`)
- `title`, `link` (unique), `source`, `published`, `collected_at`
- `content`, `quality_score`
- `is_selected`, `is_analyzed`
- `analysis_result`, `ai_model`, `extracted_keywords`

자동 마이그레이션: `check_and_migrate_database()`가 시작 시 스키마를 확인하고 누락 컬럼을 추가함.

### AI 모델 상수 (`news_engine.py` 상단에서 중앙 관리)
```python
OPENAI_MODEL_DEFAULT   = "gpt-4o"
CLAUDE_MODEL_DEFAULT   = "claude-sonnet-4-6"
GEMINI_MODEL_DEFAULT   = "gemini-2.5-flash"
PERPLEXITY_MODEL_DEFAULT = "sonar-pro"
```
모델명 변경 시 이 상수만 수정.

### Google OAuth 인증 흐름
- `credentials.json`이 있어야 최초 인증 가능
- 최초 실행 시 브라우저 OAuth 팝업 → `token.json` 자동 생성
- `token.json` 삭제 후 재실행하면 재인증
- 필요 스코프: `documents`, `drive`

## 설정

`data/config.json` (없으면 `news_engine.py` 내 하드코딩 값으로 동작):
```json
{
  "openai_api_key": "sk-...",
  "naver_client_id": "...",
  "naver_client_secret": "...",
  "gmail_sender": "...",
  "gmail_password": "앱 비밀번호 16자리",
  "gmail_receivers": ["..."],
  "google_alerts_rss": ["https://www.google.co.kr/alerts/feeds/..."],
  "naver_queries": ["5G", "위성통신", ...]
}
```

## 주요 패턴

- **성능 모니터링**: `@performance_monitor` 데코레이터로 주요 함수 실행 시간 기록
- **안전 실행**: `safe_execute(func, error_msg, default_return)` 래퍼로 예외 처리
- **DB 세션**: `get_db_session()` 컨텍스트 매니저 사용 (thread-safe, `_DB_ENGINE_LOCK`)
- **병렬 AI 분석**: `ThreadPoolExecutor`로 기사 병렬 처리
- **로그**: `data/logs/ironage_YYYYMMDD.log` (콘솔 + 파일 동시 출력)

## 인텔리전스 매트릭스 고도화 (v4.5, 2026-04-27~28)

`doc/intelligence-matrix-upgrade-plan-20260427.md` 기반으로 4개 Phase 완료.

| Phase | 모듈 | 핵심 기능 | UI 위치 |
|-------|------|---------|---------|
| 1 | `main_app.py` 인라인 | 급등 알림 카드 + Plotly 히트맵 | 대시보드 > 인텔리전스 매트릭스 > 탭1/2 |
| 2 | `rag_search.py` | 벡터 임베딩 + 자연어 검색 | 뉴스 검색 페이지 |
| 3 | `knowledge_graph.py` | NetworkX 그래프 + Pyvis 인터랙티브 HTML | 대시보드 > 인텔리전스 매트릭스 > 탭3 |
| 4 | `auto_intel_report.py` | 7-node 상태 기계 파이프라인 | 리포트 > 🤖 자율 인텔리전스 탭 |

### Phase 4 파이프라인 노드 순서
```
node_load_data → node_detect_surges → node_rag_retrieve → node_gen_narrative
→ node_build_report → node_append_to_doc → node_send_report
```
- `skip_email=True`이면 `node_send_report` 건너뜀
- 급등 엔티티가 없으면 `node_rag_retrieve`, `node_gen_narrative`, `node_append_to_doc` 건너뜀
- 각 노드 오류는 `state['errors']`에 누적; 치명적 오류 시 후속 노드 중단

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
