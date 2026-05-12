# 변경사항 보고서

**IRONAGE AI Analytics System — 버그 수정 10건 + Phase 5~7 고도화**
**작성일:** 2026-05-07
**작업 기간:** 2026-05-06 ~ 2026-05-07
**작업 유형:** 버그 수정 + 기능 고도화
**참조 계획:** `C:\Users\user\.gstack\projects\2604_AI_newsanti_1.5\ceo-plans\2026-05-06-bug-fix-phase5-7.md`

---

## 작업 개요

운영 중 발견된 10개 버그를 수정하고 Phase 5~7 고도화를 진행.
버그 수정은 `news_engine.py`·`main_app.py`·`data/config.json`에 집중되었으며,
Phase 5~7은 AI 분석 품질 균일화, 뉴스 소스 확장, 주간 급등 리포트 Google Docs 연동을 완성.
추가로 모델별 품질 대시보드, 주간 키워드 비교 히트맵 2개 확장 항목을 구현.

---

## 수정·신규 파일 목록

| 파일 | 변경 유형 | 주요 내용 |
|------|---------|---------|
| `news_engine.py` | 수정 | Bug 1~5, Bug 10, Phase 5, Phase 6(config), Phase 7 |
| `main_app.py` | 수정 | Bug 6~9, 모델 품질 대시보드, 주간 키워드 비교 히트맵 |
| `data/config.json` | 수정 | Bug 5(`ict_min_articles` 10으로 조정), Phase 6(`standards_org_rss` 추가) |

---

## 버그 수정

### Bug 1 — 엑셀 AI 모델 잘못 표기

**증상:** OpenAI로 분석했는데 엑셀에 Gemini로 표기됨.

**원인:** `analyze_news_with_ai()` 내부에서 폴백 발생 시 `news_item['ai_model']`이 갱신되지 않고, Excel 저장 시 `CONFIG.get('ai_model')` 기본값(현재 선택된 모델)이 대신 사용됨.

**수정 위치:** `news_engine.py:2303`, `news_engine.py:2433`

```python
# analyze_news_with_ai() 성공 블록
news_item['ai_model'] = current_model  # Bug 1: 실제 사용 모델 명시 저장

# analyze_news_with_replacement() DB 저장 블록
article.ai_model = item.get('ai_model', ai_model)  # 실제 사용 모델 저장
```

---

### Bug 2 — Gemini "정보를 찾을 수 없습니다"

**증상:** Gemini 사용 시 이메일·대시보드에 "주요내용 정보를 찾을 수 없습니다", "시사점 정보를 찾을 수 없습니다" 반복 표시.

**원인:** Gemini `max_output_tokens=2500` 부족으로 응답 잘림 → `### **3. 핵심 키워드**` 섹션 생략 → 정규식 매칭 실패 → 기본값 표시.

**수정 3건:**

| 위치 | 수정 내용 |
|------|---------|
| `news_engine.py` Gemini API 호출부 | `max_output_tokens: 2500 → 4096` |
| `news_engine.py` Perplexity API 호출부 | `max_tokens: 2500 → 3500` |
| `send_gmail_report()` 파싱 폴백 | 정규식 실패 시 `"[파싱 실패 요약] " + raw_text[:500]` 저장 (빈 "찾을 수 없습니다" 대신 원문 표시) |

---

### Bug 3 — Google Docs 타임아웃 (Claude 모델)

**증상:** Claude 분석 결과로 `generate_google_doc_report()` 실행 시 61초 후 `"The read operation timed out"` 오류.

**원인:** Claude 분석 결과가 길어 `requests_list`가 수천 개 항목에 달하고, 단일 `batchUpdate` 호출에 집중되어 소켓 타임아웃 발생.

**수정 위치:** `news_engine.py` — `generate_google_doc_report()` 내 batchUpdate 호출부

```python
_CHUNK_SIZE = 100
_chunks = [requests_list[i:i+_CHUNK_SIZE] for i in range(0, len(requests_list), _CHUNK_SIZE)]
_orig_timeout = socket.getdefaulttimeout()
socket.setdefaulttimeout(120)
try:
    for _ci, _chunk in enumerate(_chunks):
        try:
            docs_service.documents().batchUpdate(
                documentId=document_id, body={'requests': _chunk}
            ).execute()
        except Exception as _chunk_err:
            time.sleep(5)
            try:
                docs_service.documents().batchUpdate(
                    documentId=document_id, body={'requests': _chunk}
                ).execute()
            except Exception:
                log_error(f"청크 {_ci+1} 재시도 실패, 건너뜀")
finally:
    socket.setdefaulttimeout(_orig_timeout)
```

**주요 설계 결정:**
- `socket.setdefaulttimeout(120)`은 Docs API 블록에만 국소 적용 (AI API 호출 영향 방지, `finally`에서 복원)
- 청크 실패 시 1회 재시도(backoff 5s), 재시도 실패 시 건너뛰고 계속 진행 (부분 문서라도 생성)

---

### Bug 4 — 이메일 제목 "None"

**증상:** Claude 사용 시 발송된 이메일 제목이 "None".

**원인:** `generate_google_doc_report()` 타임아웃 → `(None, None)` 반환 → `if doc_url and report_title:` 조건 불충족 → `send_gmail_report(title=None)` → "None" 표시.

**수정 위치:** `news_engine.py` — `run_daily_collection()`, `run_weekly_report()` 두 곳

```python
# 1) doc_url 성공 여부와 무관하게 이메일 항상 발송
# 2) report_title 없을 시 날짜 기반 기본값 사용
report_title = report_title or f"ICT 뉴스 트렌드 분석 ({datetime.date.today()})"

# run_weekly_report() doc 생성 실패 경로
if not doc_url:
    _fallback_title = report_title or f"주간 ICT 뉴스 트렌드 분석 ({datetime.date.today()})"
    send_gmail_report(_fallback_title, articles, None, [])
    return None
```

---

### Bug 5 — ICT 무관 뉴스 선별

**증상:** 지방선거, 정치인 발언(오세훈·정원오 토론, 울산시장), 여행 뉴스(속초)가 분석 대상에 포함.

**원인:** ICT 키워드 기사가 `ict_min_articles(=25)` 미만이면 전체 뉴스로 대체하는 폴백 로직이 발동. 지방선거 기간에 비ICT 뉴스가 다수 유입될 때 특히 취약.

**수정 2건:**

1. `data/config.json`: `ict_min_articles: 25 → 10` (폴백 발동 임계값 하향)
2. `filter_news_by_ai()` AI 선별 프롬프트에 명시적 제외 기준 추가:

```
[필수 제외 기준]
아래 유형의 뉴스는 ICT/통신/표준화와 직접 관련이 없으므로 반드시 제외합니다.
- 지방선거, 선거 운동, 정치인 발언, 정당 관련 뉴스
- 스포츠, 연예, 방송 프로그램 관련 뉴스
- 여행, 관광, 맛집, 생활 정보 뉴스
- 날씨, 재난, 사건·사고(ICT 인프라와 무관한 것)
- ICT/통신/표준화 기술 및 정책에 직접 관련 없는 일반 경제·사회 뉴스
→ ICT/통신/표준화 기술 및 정책에 직접 관련된 기사만 선택합니다.
```

---

### Bug 6+7 — 대시보드 키워드 분석 0개 / 자율 인텔리전스 리포트 "분석 기사 부족"

**증상:**
- "AI 추출 핵심 키워드 분석" 메뉴에서 "최근 7일간 분석된 뉴스 0개" 표시
- 🤖 자율 인텔리전스 탭에서 "분석 기사 0개 (최소 5개 필요)" 표시

**원인:** Streamlit 대시보드에서 분석 실행 시 `is_analyzed=True` 플래그가 DB에 저장되지 않아 대시보드 쿼리 결과 0건.

**수정 3건 (`news_engine.py` + `main_app.py`):**

| 위치 | 수정 내용 |
|------|---------|
| `analyze_news_with_replacement()` DB 저장 블록 | `article.is_analyzed = True` 명시 저장 추가 |
| `main_app.py` 키워드 분석 쿼리 | `is_analyzed=True` 조건 제거 → `extracted_keywords` 존재 여부로 클라이언트 필터링 |
| `main_app.py` 기본 날짜 범위 | 7일 → 30일 기본값 (index=0 → index=2) |

---

### Bug 8 — 분석완료·임베딩 완료 숫자 업데이트 안됨

**증상:** 뉴스 자연어 검색 화면에서 임베딩 실행 후에도 숫자가 갱신되지 않음.

**원인:** Streamlit `@st.cache_data` 캐시가 이전 값을 유지.

**수정:** `main_app.py` 임베딩 완료 후 `st.cache_data.clear()` 호출 추가.

---

### Bug 9 — 이슈 추적 & 표준화 갭 글자 겹침

**증상:** "이슈 추적 & 표준화 갭" 탭 및 대시보드 키워드 태그에서 텍스트가 겹쳐서 표시됨.

**원인:** Streamlit HTML 컴포넌트에서 `overflow: hidden` + 고정 높이 조합으로 텍스트 잘림·겹침 발생.

**수정:** `main_app.py` 키워드 태그 스타일에 `word-wrap:break-word; overflow:visible; max-width:180px` 적용 + 15자 초과 시 말줄임표 처리.

---

### Bug 10 — TTA 조치사항 형식

**증상:** 이메일에서 TTA 조치사항이 두 줄 카드로 별도 표시되고, 내용이 짧고 팩트 부족.

**수정 2건:**

**(a) HTML 구조 변경 (`send_gmail_report()`):**
- 기존: TTA 조치사항 별도 카드 (`{tta_html}`)
- 변경: 시사점 섹션 내부 인라인 표시 (`{tta_inline}`)
- `doc_url=None` 시 Google Docs 링크 버튼 대신 `"(Google Docs 생성 실패 — 아래 본문 참조)"` 텍스트

**(b) 프롬프트 기준 강화 (`analyze_news_with_ai()`):**
```
- **최소 50자 이상** 작성, 구체적 수치·일정·기구명 포함 필수
  (예: "2026년 3GPP Rel-19 동결 전 SA2 #163 회의 참여하여 NTN 세션 기여문서 제출")
```

---

## Phase 5 — AI 응답 품질 균일화

**목표:** OpenAI 분석 품질을 기준으로 Gemini·Claude·Perplexity의 불완전 응답(섹션 누락)을 자동 감지하고 1회 재호출.

### 신규 함수 2개

**`validate_analysis_output(analysis_text, model_name) → list`**

`is_valid_analysis()` 래핑 + 섹션별 존재 여부 세부 검증. 누락 섹션 목록 반환.

```python
def validate_analysis_output(analysis_text: str, model_name: str = '') -> list:
    if not is_valid_analysis(analysis_text):
        return ['주요 내용 요약', '시사점 및 전망']
    missing = []
    if not any(p in analysis_text for p in ['주요 내용 요약', '주요 내용', 'Main Content']):
        missing.append('주요 내용 요약')
    if not any(p in analysis_text for p in ['시사점 및 전망', '시사점', 'Implications']):
        missing.append('시사점 및 전망')
    return missing
```

**`_phase5_retry_call(model_name, prompt) → str`**

누락 섹션 목록을 포함한 재호출 프롬프트로 동일 모델 1회 재호출. 실패 시 빈 문자열 반환.

### 재호출 흐름

`analyze_news_with_ai()` 성공 블록 내, `update_analysis_in_db()` 직전에 삽입:

```
분석 성공 → validate_analysis_output() → 누락 없음: 그대로 저장
                                        → 누락 있음: _phase5_retry_call() → 재호출 성공: analysis 교체, ai_model_fallback = "{model}_retry"
                                                                           → 재호출 실패: 원본 분석 그대로 저장
```

**설계 결정:**
- `news_item['ai_model']`은 원본 모델명 유지 (모델 대시보드 그룹핑 보호)
- `ai_model_fallback = "{model}_retry"` suffix로 재호출 여부 구분 가능
- 재호출은 기존 `max_retries` 루프와 별개 — 루프 바깥에서 1회만 발생, double-retry 없음

### DB 마이그레이션

`check_and_migrate_database()`에 `ai_model_fallback VARCHAR(100)` 컬럼 자동 추가 (nullable). 기동 시 자동 실행.

---

## Phase 6 — 뉴스 수집 소스 확장

**목표:** ICT 전문 표준화 기관(3GPP·ETSI·ITU) RSS 피드를 별도 관리하여 비ICT 뉴스 유입 근본 감소.

**수정:** `data/config.json`에 `standards_org_rss` 키 추가

```json
"standards_org_rss": [
  "https://www.3gpp.org/news-events/3gpp-news/feed",
  "https://www.etsi.org/news-events/news/rss",
  "https://www.itu.int/net/pressoffice/RSS/feed.aspx",
  "__REPLACE_WITH_GOOGLE_ALERTS_3GPP_2026_MEETING__",
  "__REPLACE_WITH_GOOGLE_ALERTS_ETSI_STANDARD_2026__",
  "__REPLACE_WITH_GOOGLE_ALERTS_IEEE_5G_STANDARDS_2026__"
]
```

**사용 방법:** `__REPLACE_WITH_...` 항목에 실제 Google Alerts RSS URL 입력. feedparser가 오류를 자동으로 무시하므로 placeholder가 남아 있어도 기존 피드에 영향 없음.

---

## Phase 7 — 주간 급등 리포트 Google Docs 연동

**목표:** Google Docs 주간 보고서 상단에 "전주 대비 급등 엔티티 TOP 5" 섹션 자동 포함.

**수정 위치:** `news_engine.py` — `generate_google_doc_report()` 내 구분선(`━━━`) 직후, 안내사항 직전

### 구현 로직

```python
# 1. knowledge_graph에서 detect_surge_entities 로컬 임포트
from knowledge_graph import detect_surge_entities

# 2. 전주 데이터: SQLAlchemy 직접 쿼리 (7~14일 전)
_prev_start = now - timedelta(days=14)
_prev_end   = now - timedelta(days=7)
_prev_data  = db.query(NewsArticle).filter(
    collected_at >= _prev_start,
    collected_at <  _prev_end
).all()

# 3. 급등 감지
_surge_entities = detect_surge_entities(analyzed_data, _prev_data)[:5]

# 4. 결과가 있으면 표 형식으로 삽입, 없으면 섹션 전체 생략
```

**설계 결정:**
- `load_news_from_db(days=N)`은 "N일 전~현재" 범위만 지원 → 이전 주 데이터는 SQLAlchemy 직접 쿼리 (날짜 범위 지정)
- 급등 엔티티 0개인 경우 섹션 전체 생략 (빈 표 미노출) — `auto_intel_report.py` 파이프라인과 일관성 유지
- `knowledge_graph.py`가 `news_engine.py`를 임포트하지 않음이 확인되어 순환 임포트 없음
- `pct_change`는 ratio(0~1) 값 — 표시 시 `*100` 변환 및 `inf` → "신규 등장" 처리

**표시 예시 (Google Docs 보고서):**
```
📈 전주 대비 급등 키워드 TOP 5
  1. LG디스플레이 (company) | 전주 0회 → 이번주 2회 (신규 등장)
  2. GPS (tech)            | 전주 1회 → 이번주 2회 (+100%)
  3. 영국 (country)        | 전주 2회 → 이번주 3회 (+50%)
```

---

## 확장 항목

### 이메일 HTML 폴백

Bug 4 + Bug 10(a) 조합으로 완성.
- Google Docs 생성 실패 시에도 `send_gmail_report()`가 항상 호출됨 (Bug 4)
- `doc_url=None` 시 Google Docs 링크 버튼 대신 `"(Google Docs 생성 실패 — 아래 본문 참조)"` 텍스트로 대체 (Bug 10a)
- 이메일 본문에는 각 기사의 분석 결과 전체가 포함되므로 Google Docs 없이도 완전한 내용 전달

### AI 모델별 분석 품질 대시보드

**위치:** `main_app.py` — 대시보드 페이지 하단 (`"#### 🤖 AI 모델별 분석 품질"`)

DB 집계 쿼리로 모델별 `extracted_keywords` 존재 비율 계산 후 `st.metric()` 카드로 표시.

**품질 지표:** `extracted_keywords IS NOT NULL AND extracted_keywords != ''` 비율

**테스트 결과 (2026-05-07 기준):**

| 모델 | 키워드 추출률 | 기사 수 |
|------|------------|--------|
| OpenAI | 74% | 268건 |
| Claude | 95% | 74건 |
| Gemini | 94% | 241건 |
| Perplexity | 100% | 10건 |

### 주간 키워드 비교 히트맵

**위치:** `main_app.py` — 인텔리전스 매트릭스 4번째 탭 (`"📊 주간 키워드 비교"`)

이번 `keyword_days`일과 이전 `keyword_days`일의 `key_technologies` 등장 횟수를 Plotly `imshow`로 비교.

- 상위 15개 기술 키워드 추출 (현재·이전 기간 합산 빈도순)
- 색상: 초록(증가) ↔ 빨강(감소) (`RdYlGn` 색상맵)
- 이전 기간 데이터 없을 시 "비교할 이전 기간 데이터 부족" 메시지 표시

---

## 테스트 결과

2026-05-07 `python -c` + Streamlit 기동 테스트로 확인.

| 항목 | 결과 |
|------|------|
| Streamlit 기동 (HTTP 200) | ✅ |
| DB 통계 쿼리 (전체 32,228 / 분석완료 593) | ✅ |
| 모델 품질 집계 쿼리 (SQLAlchemy case()) | ✅ |
| Phase 7 detect_surge_entities 임포트 | ✅ |
| Phase 7 전주 날짜 범위 쿼리 | ✅ (이전주 1,212건 로드) |
| Phase 5 validate_analysis_output | ✅ (완전 응답 `[]`, 불완전 응답 재호출 트리거) |
| config 변경 (ict_min=10, standards_org_rss 6개) | ✅ |
| Bug 5 필터 프롬프트 (지방선거·스포츠 제외) | ✅ |
| Bug 10 TTA 50자 조건 | ✅ |
| 주간 히트맵 데이터 빌드 | ✅ (이전 데이터 부족 시 안내 메시지 표시) |

---

## 알려진 제약

| 항목 | 내용 |
|------|------|
| Phase 6 placeholder URL | `__REPLACE_WITH_...` 3개는 실제 Google Alerts URL로 직접 교체 필요. feedparser가 오류 무시하므로 현재 기능 영향 없음 |
| 주간 키워드 히트맵 | DB에 60일 이상 데이터 누적 시 자동 표시. 현재는 이전 기간 데이터 부족으로 안내 메시지 출력 |
| Bug 3 부분 실패 | Google Docs 청크 실패-건너뜀 정책 하에서 index 오염 가능성 있음. 실패 청크 건너뜀으로 부분 문서 생성. 완전한 문서가 필요하다면 재실행 |

---

## 다음 단계 후보 (TODOS.md 참조)

- **분석 결과 인라인 편집 UI**: Streamlit `st.text_area` + DB `analysis_result` 저장 버튼. 이메일 발송 전 TTA 담당자가 TTA 조치사항을 직접 수정 가능.
- **자동 모델 폴백 순서**: OpenAI → Gemini → Perplexity 자동 시도 (현재는 수동 선택).
- **Phase 6 Google Alerts URL 실제 등록**: 3GPP 2026 회의, ETSI 표준, IEEE 5G 관련 Google Alerts 생성 후 `standards_org_rss`에 등록.
