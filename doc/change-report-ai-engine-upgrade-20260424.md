# 변경사항 보고서

**IRONAGE AI Analytics System — AI 분석 엔진 고도화 및 리포트 연동**
**작성일:** 2026-04-24
**작업 유형:** 기능 추가 (영향도·TTA 조치 사항·표준화 격차 분석 항목 신설)
**참조 계획:** `doc/implementation_plan.md` § 2. AI 분석 엔진 고도화 / § 3. 리포트 연동

---

## 수정 파일 목록

| 파일 | 변경 유형 |
|------|---------|
| `news_engine.py` | 수정 (프롬프트·파싱·Google Docs·Gmail·Excel) |
| `doc/implementation_plan.md` | 수정 (완료 항목 체크) |

---

## 1. AI 분석 프롬프트 고도화

**위치:** `analyze_news_with_ai()` 내 `OUTPUT FORMAT` 섹션 (§3. 핵심 키워드)

### 변경 전
```
### **3. 핵심 키워드**
{
  "keywords": [
    {"term": "...", "category": "...", "importance": "..."}
  ]
}
```

### 변경 후
```
### **3. 핵심 키워드 및 영향도 분석**
{
  "keywords": [
    {"term": "...", "category": "...", "importance": "..."}
  ],
  "impact_level":        "Critical | High | Medium | Low",
  "impact_reason":       "영향도 판단 근거 1~2문장",
  "tta_action_item":     "TTA 표준화본부 즉시 조치 사항",
  "standardization_gap": "현재 표준화 현황과 기사 내용 간의 격차"
}
```

### 추가된 작성 기준 (프롬프트 내)

| 필드 | 기준 |
|------|------|
| `impact_level` | Critical / High / Medium / Low 4단계. 반드시 이 4개 값 중 하나만 사용 |
| `impact_reason` | 기사 내용에 직접 근거한 영향도 판단 근거 |
| `tta_action_item` | TTA 관점의 구체적 행동 지침, 빈 문자열 불허 |
| `standardization_gap` | 표준화 수준과 현실 사이의 격차. 정보 없으면 `"기사에서 표준화 현황 정보 미확인"` |

**영향도 단계 정의**

| 단계 | 정의 |
|------|------|
| Critical | TTA가 즉각적인 공식 대응이 필요한 긴급 사안 (규제 발효, 표준화 완료 임박, 핵심 기술 돌파) |
| High | 6개월 내 전략적 대응이 필요한 중요 동향 |
| Medium | 지속 모니터링이 필요한 일반 업계 동향 |
| Low | 참고 수준의 배경 정보성 뉴스 |

---

## 2. JSON 파싱 및 news_item 데이터 처리

**위치:** `analyze_news_with_ai()` 내 키워드 추출 블록

### 추가된 로직
AI 응답 JSON 파싱 성공 시 `news_item` 딕셔너리에 4개 필드를 직접 저장:

```python
news_item['impact_level']        = parsed.get('impact_level', 'Medium')
news_item['impact_reason']       = parsed.get('impact_reason', '')
news_item['tta_action_item']     = parsed.get('tta_action_item', '')
news_item['standardization_gap'] = parsed.get('standardization_gap', '')
```

파싱 실패(키워드 섹션 없음 / JSONDecodeError) 시에도 기본값으로 초기화하여 이후 리포트 생성 단계에서 KeyError가 발생하지 않도록 방어 처리.

---

## 3. 신규 헬퍼 코드

**위치:** `generate_google_doc_report()` 정의 직전 (모듈 레벨)

### 상수

```python
IMPACT_LEVEL_ORDER    = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
IMPACT_LEVEL_ICON     = {'Critical': '🚨', 'High': '⚠️', 'Medium': '📋', 'Low': 'ℹ️'}
IMPACT_LEVEL_COLOR_RGB = {
    'Critical': {'red': 0.85, 'green': 0.13, 'blue': 0.13},
    'High':     {'red': 0.91, 'green': 0.36, 'blue': 0.02},
    'Medium':   {'red': 0.14, 'green': 0.39, 'blue': 0.82},
    'Low':      {'red': 0.42, 'green': 0.45, 'blue': 0.50},
}
```

### 헬퍼 함수 `_get_impact_info(data: dict) -> dict`

`news_item`에서 영향도 관련 4개 필드를 안전하게 추출.

- 우선순위 1: `news_item`에 `impact_level` 키가 직접 존재하면 사용
- 우선순위 2: `extracted_keywords` JSON을 파싱하여 추출
- 어느 경우도 실패하면 기본값(`'Medium'`, 빈 문자열 3개) 반환

---

## 4. Google Docs 리포트 변경

**위치:** `generate_google_doc_report()`

### 4-1. 문서 상단 — 영향도 요약 섹션 신설 (TOC 직후)

Critical 또는 High 등급의 뉴스가 존재할 경우 다음 섹션을 자동으로 삽입:

```
🔔 주요 조치 필요 항목 (Critical / High)
  🚨 [Critical] 기사 제목 최대 60자...
       → TTA 조치: TTA 조치 사항 텍스트
  ⚠️ [High]     기사 제목 최대 60자...
       → TTA 조치: TTA 조치 사항 텍스트
```

- 영향도 높은 순(Critical → High)으로 정렬
- 영향도별 지정 색상으로 텍스트 스타일 적용

### 4-2. 각 기사 항목 — 영향도 배지 및 TTA 섹션 추가

기존 `원문 링크` 바로 다음에 3개 블록 추가:

| 블록 | 조건 | 스타일 |
|------|------|--------|
| `{icon} 영향도: {level}` | 항상 표시 | 영향도별 컬러 볼드 |
| `▶ TTA 조치 사항` + 본문 | `tta_action_item` 존재 시 | 노란 배경 블록 |
| `▶ 표준화 격차` + 본문 | `standardization_gap` 존재하고 "미확인" 아닐 때 | 들여쓰기 블록 |

---

## 5. Gmail 이메일 리포트 변경

**위치:** `send_gmail_report()`

### 5-1. 영향도 우선 정렬

함수 시작 시 `analyzed_data`를 Critical→High→Medium→Low 순으로 정렬:

```python
sorted_data = sorted(
    analyzed_data,
    key=lambda d: IMPACT_LEVEL_ORDER.get(_get_impact_info(d)['impact_level'], 2)
)
```

### 5-2. 각 뉴스 카드 변경

| 위치 | 변경 내용 |
|------|---------|
| 카드 상단 테두리 | 영향도별 컬러 `border-top: 3px solid {color}` |
| 번호 배지 배경색 | 영향도별 컬러 |
| 제목 위 | 영향도 배지 (`🚨 Critical` 등 pill 스타일) |
| 시사점 섹션 아래 | **TTA 조치 사항** 섹션 (영향도 컬러 left border) |
| TTA 섹션 아래 | **표준화 격차** 섹션 (초록 left border, 정보 있을 때만) |

**영향도별 HTML 색상표**

| 단계 | 텍스트 색 | 배경 색 |
|------|---------|--------|
| Critical | `#dc2626` | `#fff1f2` |
| High | `#ea580c` | `#fff7ed` |
| Medium | `#2563eb` | `#eff6ff` |
| Low | `#6b7280` | `#f9fafb` |

---

## 6. Excel 리포트 변경

**위치:** `save_analysis_to_weekly_excel()` 내 `row_data` 딕셔너리

### 추가된 컬럼 (기존 컬럼 사이에 삽입)

| 순서 | 컬럼명 | 데이터 출처 |
|------|--------|-----------|
| 5번째 | `영향도` | `_get_impact_info(item)['impact_level']` |
| 6번째 | `TTA 조치 사항` | `_get_impact_info(item)['tta_action_item']` |
| 7번째 | `표준화 격차` | `_get_impact_info(item)['standardization_gap']` |

---

## 7. 데이터 흐름 (변경 후)

```
AI 분석 프롬프트
    ↓ (JSON 응답)
_extract_keyword_json()
    ↓
analyze_news_with_ai()
    → news_item['keywords']           (기존)
    → news_item['impact_level']       (신규)
    → news_item['impact_reason']      (신규)
    → news_item['tta_action_item']    (신규)
    → news_item['standardization_gap'](신규)
    ↓
_get_impact_info(news_item)           (헬퍼, 안전 추출)
    ↓                ↓                   ↓
Google Docs      Gmail HTML          Excel (.xlsx)
  - 요약 섹션     - 정렬              - 영향도 컬럼
  - 배지/TTA     - 배지/TTA          - TTA 컬럼
  - 표준화 격차  - 표준화 격차       - 표준화 격차 컬럼
```

---

## 8. 검증 방법

```bash
# 1. 구문 오류 검사 (통과 확인됨)
python -c "import ast; ast.parse(open('news_engine.py', encoding='utf-8').read()); print('OK')"

# 2. 테스트 모드 — DB 통계 및 기존 기능 정상 동작 확인
python news_engine.py test

# 3. 단일 기사 AI 분석 — JSON에 새 필드 포함 여부 확인
#    (news_engine.py 내 테스트 모드 또는 기존 DB 데이터 활용)

# 4. Streamlit 대시보드 실행 후 이상 없음 확인
streamlit run main_app.py
```

---

## 9. 미완료 항목 (implementation_plan.md 기준)

| 항목 | 상태 | 비고 |
|------|------|------|
| 사이드바 및 레이아웃 배치 최적화 | 미완료 | `main_app.py` 별도 작업 필요 |
| 영향도 차트 (도넛 차트) | 미완료 | `main_app.py` 대시보드 작업 필요 |
| 주요 조치 사항 시보드 요약 | 미완료 | `main_app.py` 대시보드 작업 필요 |
