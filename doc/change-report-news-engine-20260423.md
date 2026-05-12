# 변경사항 보고서

**IRONAGE AI Analytics System — news_engine.py 강화**
**작성일:** 2026-04-23
**작업 유형:** 기능 추가 (main6.93t.py 뉴스 선별 로직 이식)

---

## 수정 파일 목록

| 파일 | 변경 유형 | 백업 |
|------|---------|------|
| `news_engine.py` | 수정 (기능 추가 + 버그 수정) | `news_engine.py.bak.20260423` |
| `data/config.json` | 수정 (키 4개 추가) | `data/config.json.bak.20260423` |

---

## 1. data/config.json

**변경 내용:** 새 설정 키 4개 추가

| 키 | 기본값 | 설명 |
|---|------|------|
| `ict_keywords` | 50+ 키워드 배열 | Stage 1 필터에서 ICT 관련 기사를 판별하는 키워드 목록 |
| `ict_min_articles` | 25 | ICT 필터 통과 기사가 이 값 미만이면 필터 비활성화, 전체 기사 사용 |
| `jaccard_threshold_numeric` | 0.5 | 제목에 동일한 숫자가 있을 때의 Jaccard 유사도 임계값 |
| `jaccard_threshold_text` | 0.6 | 숫자 없는 제목 비교 시 Jaccard 임계값 (더 보수적) |

---

## 2. news_engine.py — 변경 요약

### 2-1. 모듈 레벨 상수 및 헬퍼 함수 (신규 추가)

`load_config()` 앞에 삽입. 테스트 및 재사용 가능하도록 모듈 레벨로 추출.

**regex 상수 5개 (모듈 레벨 pre-compile):**

```python
_RE_HTML_ENTITY   = re.compile(r'&[a-zA-Z]+;')
_RE_HTML_TAG      = re.compile(r'<[^>]+>')
_RE_SPECIAL_CHARS = re.compile(r'["\'\[\]()…·\-_|<>]')
_RE_WHITESPACE    = re.compile(r'\s+')
_RE_NUMBERS       = re.compile(r'\d+(?:만|억|조|기|개|대|%)?|\d+[gG]')
```

**헬퍼 함수 5개:**

| 함수 | 역할 |
|------|------|
| `normalize_title(title)` | Jaccard 비교용 제목 정규화 (HTML 제거, 소문자) |
| `get_title_keywords(title)` | 불용어 제거 후 핵심 키워드 set 반환 |
| `is_similar_news(t1, t2, ...)` | Jaccard 유사도로 두 기사가 같은 사건인지 판단 |
| `normalize_for_clustering(title)` | 클러스터링용 제목 정규화 (더 공격적) |
| `extract_signature(title)` | 클러스터링 키 생성 (숫자 + 주요 개체명 tuple) |

`is_similar_news()` 임계값 설계:
- 두 제목에 동일 숫자 존재 → `threshold_numeric` (0.5) 사용. 숫자 일치가 강한 동일 사건 증거이므로 낮은 임계값
- 숫자 없거나 다를 때 → `threshold_text` (0.6) 사용. 키워드만으로 판단하므로 더 엄격

### 2-2. load_config() — default_config에 새 키 4개 추가

config.json에 해당 키가 없을 때 조용히 실패하지 않도록 기본값 보장.

```python
'ict_keywords': DEFAULT_ICT_KEYWORDS,
'ict_min_articles': 25,
'jaccard_threshold_numeric': 0.5,
'jaccard_threshold_text': 0.6,
```

### 2-3. deduplicate_news() — Jaccard 타이틀 중복 제거 추가

```
[기존]   1단계: URL 정규화 중복 제거
[변경 후] 1단계: URL 정규화 중복 제거 (기존 유지)
          2단계: Jaccard 타이틀 유사도 중복 제거 (신규)
                - 같은 사건을 다루는 기사 중 제목이 가장 긴 기사를 대표로 선택
                - 제거된 기사 수 log_info() 출력
```

### 2-4. filter_news_by_ai() — Stage 1, Stage 2 삽입

```
[기존 흐름]
  API 키 확인 → 전체 뉴스 포맷팅 → AI 호출 → news_items[i] 반환

[변경 후 흐름]
  API 키 확인
  ├ [Stage 1 신규] ICT 키워드 사전 필터
  │   ├ config['ict_keywords']로 비ICT 기사 제거
  │   └ 통과 기사 < ict_min_articles → log_warning + 전체 사용 (폴백)
  ├ [Stage 2 신규] 엔티티 클러스터링
  │   ├ extract_signature()로 기사별 시그니처 생성
  │   └ 동일 시그니처 = 동일 사건 → 대표 기사 1개만 유지
  │   news_for_ai = 클러스터링 결과[:100]
  └ AI 호출 → news_for_ai[i] 반환
```

### 2-5. 버그 수정

| 위치 | 버그 | 수정 |
|------|------|------|
| filter_news_by_ai() 내부 | `import re` 함수 내부 중복 import | 제거 (re는 파일 최상단 line 12에서 이미 import) |
| AI 결과 파싱 | `int(n) < len(news_items)` | `int(n) < len(news_for_ai)` |
| 선별 결과 생성 | `news_items[i]` | `news_for_ai[i]` |
| 예외 처리 폴백 | `return news_items[:max_results]` | `return news_for_ai[:max_results]` |

---

## 3. 전체 파이프라인 흐름 (변경 후)

```
수집 (get_news_data)
  ↓
deduplicate_news()
  ├ [Layer 1] URL 정규화 중복 제거
  └ [Layer 2] Jaccard 타이틀 유사도 중복 제거  ← 신규
  ↓
filter_news_by_ai()
  ├ [Stage 1] ICT 키워드 사전 필터              ← 신규
  ├ [Stage 2] 엔티티 클러스터링                 ← 신규
  └ [Stage 3] AI 최종 선별 (기존 프롬프트 유지)
  ↓
analyze_news_with_replacement()
  ↓
이메일 / Google Docs 발송
```

---

## 4. main_app.py 영향

없음. `filter_news_by_ai()`와 `deduplicate_news()`의 함수 시그니처가 변경되지 않아 main_app.py 수정 불필요.

---

## 5. 복구 방법

```bash
cp news_engine.py.bak.20260423 news_engine.py
cp data/config.json.bak.20260423 data/config.json
```

---

## 6. 미완료 항목 (이번 세션 범위 외)

| 항목 | 상태 | 비고 |
|------|------|------|
| 단위 테스트 (`tests/test_news_engine.py`) | 미작성 | 사용자 요청으로 연기 ("나중에") |
| config.json API 키 평문 저장 | 미수정 | .gitignore 확인 필요 |
