# CEO Plan: news_engine.py 강화 (main6.93t.py 핵심 기능 통합)

Generated: 2026-04-22  
Repo: D:\AI_project\2604_AI_news(anti)_1.5  
Status: APPROVED (cherry-picks complete)

## 목표

main6.93t.py의 뉴스 선별 정확도를 news_engine.py에 통합한다.  
결과물: 기존 main_app.py Streamlit 대시보드가 4개 모델 + 향상된 선별 정확도로 동작.

## 실제 범위 (CEO 리뷰에서 재정의)

**초기 설계 문서의 오류**: 30% 하이라이트 프롬프트, analyze_news_with_replacement(), 이메일 CSS 하이라이트는 이미 news_engine.py에 존재함. 실제 누락 기능은 2개뿐.

### 실제 구현 대상 (news_engine.py 수정)

**Gap 1 — ICT 키워드 사전 필터 + 클러스터링**  
위치: `filter_news_by_ai()` (lines 1367–1560)  
현재: 4개 모델 지원하나 ICT 도메인 사전 필터 없음  
추가할 것:
- Stage 1: 70+ ICT 키워드 사전 필터 (통신, 5G, 6G, 위성, 3GPP, ITU 등)
- Stage 2: `extract_signature()` + 엔티티 클러스터링으로 AI 전달 전 중복 제거
- 키워드 목록 출처: config.json `ict_keywords` 배열

**Gap 2 — Jaccard 타이틀 유사도 중복 제거**  
위치: `deduplicate_news()` (lines 395–421)  
현재: URL 정규화만 존재, 타이틀 유사도 없음  
추가할 것:
- `normalize_title()`, `get_title_keywords()`, `is_similar_news()` 모듈 레벨 헬퍼 함수
- Jaccard 유사도 임계값: config.json `jaccard_threshold` (기본값 0.6)

### config.json 추가 키 (엔지니어링 리뷰 반영)

```json
{
  "ict_keywords": ["통신", "5G", "6G", "위성", "satellite", "3GPP", "ITU", "FCC", ...],
  "ict_min_articles": 25,
  "jaccard_threshold_numeric": 0.5,
  "jaccard_threshold_text": 0.6
}
```

**임계값 설명:**
- `jaccard_threshold_numeric`: 두 기사 제목에 같은 숫자가 있을 때 사용 (낮은 값 = 더 공격적)
- `jaccard_threshold_text`: 숫자 없는 제목 비교 시 사용 (높은 값 = 더 보수적)

### 코드 품질 작업 (엔지니어링 리뷰 반영)

- `filter_news_by_ai()` 이식 시 모든 `print()` → `log_info()` / `log_warning()` 교체
- **헬퍼 함수 5개** 모듈 레벨로 추출:
  - dedup용: `normalize_title()`, `get_title_keywords()`, `is_similar_news()`
  - clustering용: `normalize_for_clustering()`, `extract_signature()`
- `re` import (현재 news_engine.py:1542 함수 내부) → 파일 최상단으로 이동
- ICT 필터 폴백 발동 시 `log_warning()` 명시적 출력
- `ict_keywords` null/타입 오류 방어 코드: `CONFIG.get('ict_keywords') or DEFAULT_ICT_KEYWORDS`
- regex 패턴 모듈 레벨 `re.compile()` 상수화 (반복 컴파일 제거)

## Cherry-pick 결정

| # | 항목 | 결정 |
|---|------|------|
| A | ICT 키워드 목록 위치 | config.json (`ict_keywords`) |
| B | Jaccard 임계값 위치 | config.json (두 키 분리: `jaccard_threshold_numeric: 0.5`, `jaccard_threshold_text: 0.6`) |
| C | Dry-run 모드 | 추가 안 함 |
| D | ICT 최소 기사 수 | config.json (`ict_min_articles: 25`) |

## 보안 주의사항 (CRITICAL)

**이식 금지 (main6.93t.py lines 65–75):**  
- `NAVER_CLIENT_SECRET`, `OPENAI_API_KEY`, `GMAIL_PASSWORD` 하드코딩 값  
- news_engine.py는 이미 config.json에서 API 키를 로드하는 구조 사용

**기존 위험 (Outside Voice 지적):**  
- `data/config.json`에 OpenAI/Claude/Gemini/Perplexity/Gmail 키가 현재도 평문 저장됨  
- 이번 작업 범위 밖이지만 git 추적에서 반드시 제외 확인 필요 (`.gitignore`)

## 구현 시 주의사항 (Outside Voice 리뷰 반영)

**1. config 기본값 fallback 필수**  
`load_config()`의 `default_config`에 두 키를 반드시 추가해야 함:
```python
"ict_keywords": [...],   # 빠지면 Stage 1 필터 조용히 무력화
"jaccard_threshold": 0.6
```
config.json에 키가 없는 경우 `CONFIG.get('ict_keywords', [])` → 빈 리스트 → 필터 통과 불가.

**2. 중복 제거 레이어 실행 순서 명시**  
현재 + 추가 후 중복 제거 레이어 3개 중첩:
1. `deduplicate_news()`: URL 정규화 (기존)
2. `deduplicate_news()`: Jaccard 타이틀 유사도 (추가)
3. `filter_news_by_ai()` AI 프롬프트 내 중복 제거 지시 (기존)

구현 시 레이어 순서 (1→2→3) 문서화 필수. AI 프롬프트 내 중복 제거 지시를 삭제하지 말 것 (AI가 맥락 기반으로 추가 판단하므로 보완적).

**3. Jaccard 임계값 검증 계획**  
0.6은 ICT 뉴스 특성상 과도하게 공격적일 수 있음. 초기 실행 후 제거된 기사 목록을 로그로 출력해 검증. 필요 시 config에서 조정.

**4. 상대경로 취약점 (이번 범위 밖, 주의)**  
`load_config()`가 `Path("data/config.json")` 상대경로 사용. 다른 디렉토리에서 실행 시 config 로드 실패 가능성 있음. 이번 작업에서 수정하지 않으나 인지 필요.

## 범위 외 (이번 작업에서 하지 않는 것)

- main_app.py UI 변경 없음
- Google Docs / Gmail 발송 로직 변경 없음
- DB 스키마 변경 없음
- Dry-run 모드 추가 없음
- 새로운 AI 모델 추가 없음

## 구현 파일

| 파일 | 변경 유형 |
|------|---------|
| `news_engine.py` | 수정 (Gap 1, Gap 2, 헬퍼 함수) |
| `data/config.json` | 수정 (ict_keywords, jaccard_threshold 추가) |
| `main6.93t.py` | 읽기 전용 참조 (수정 안 함) |
| `main_app.py` | 변경 없음 |

## 성공 기준

1. `filter_news_by_ai()` 실행 시 ICT 비관련 기사가 AI에 전달되지 않음
2. `deduplicate_news()` 실행 후 타이틀 유사 기사가 제거됨
3. 기존 main_app.py Streamlit 앱이 수정 없이 정상 동작
4. news_engine.py에 `print()` 잔존 없음 (이식된 코드 기준)

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | clean | cherry-picks A/B/C/D confirmed, 2 outside voice items fixed |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 5 issues found, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CROSS-MODEL:** Outside voice (Claude subagent) found 5 issues. 2 accepted (fallback logging, ict_keywords null validation). 3 rejected (threshold direction correct, extract_signature defined, .update() merge direction sound).
- **UNRESOLVED:** 0
- **VERDICT:** CEO + ENG CLEARED — ready to implement
