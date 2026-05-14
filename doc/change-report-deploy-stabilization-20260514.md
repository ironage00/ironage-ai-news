# 변경 보고서: 배포 안정화 및 운영 자동화 (2026-05-13~14)

Branch: main  
Status: ✅ 완료 — Streamlit Cloud 정상 운영 중

---

## 배경

2026-05-12 세션에서 Streamlit Cloud 배포를 완료한 후, 13~14일에 걸쳐
실제 운영 중 발견된 오류를 수정하고 자동화 신뢰성을 높였다.

---

## 1. Streamlit Cloud 배포 버그 수정 (2026-05-13)

### 1-1. Python 버전 고정 (`runtime.txt`)

**문제:** Streamlit Cloud가 Python 3.14를 선택 → `lxml`, `psycopg2-binary` wheel 없음  
**해결:** `runtime.txt` 신규 생성

```
python-3.11
```

### 1-2. 패키지 버전 핀 완화 (`requirements.txt`)

| 패키지 | 이전 | 이후 | 이유 |
|--------|------|------|------|
| `lxml` | `==4.9.3` | `>=5.3.0` | Python 3.14 wheel 없음 |
| `feedparser` | `==6.0.10` | `>=6.0.11` | `cgi` 모듈 제거 (Python 3.13+) |
| `psycopg2-binary` | `==2.9.9` | `>=2.9.9` | 유연성 확보 |
| 기타 모든 패키지 | `==` 핀 | `>=` 핀 | 호환성 확보 |

### 1-3. `st.experimental_user` AttributeError 수정 (`main_app.py`)

**문제:** `hasattr()` 호출 자체가 예외를 던지는 경우 미처리  
**해결:** 전체 블록 `try/except` 감싸기

```python
_auth_enabled = False
try:
    if hasattr(st, 'experimental_user'):
        _auth_enabled = hasattr(st.experimental_user, 'is_logged_in')
except Exception:
    _auth_enabled = False
```

### 1-4. `week_str` NameError 수정 (`main_app.py`)

**문제:** `week_str`이 `if excel_path:` 블록 안에서만 정의 → 블록 밖 참조 시 NameError  
**해결:** `week_str` 정의를 조건문 앞으로 이동

### 1-5. Google Docs 실패 시 이메일 제목 `None` 수정 (`main_app.py`)

**문제:** `generate_google_doc_report()` 실패 → `report_title = None` → 이메일 제목 "None"  
**해결:** 폴백 제목 생성

```python
if not report_title:
    report_title = f"전파·이동통신 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
```

### 1-6. 0개 수집 문제 수정 (`news_engine.py`)

**문제:** `data/config.json`이 없는 Streamlit Cloud 환경에서 API 키 미로드 → 뉴스 0개 수집  
**해결:** `load_config()` 에 환경변수 폴백 추가

```python
default_config = {
    'openai_api_key': os.environ.get('OPENAI_API_KEY', ''),
    'naver_client_id': os.environ.get('NAVER_CLIENT_ID', ''),
    # ... 전체 API 키
    'google_alerts_rss': _default_rss,   # 17개 하드코딩 RSS
    'naver_queries': ["위성통신","6G","클라우드","3GPP","FCC","양자","UAM","SDV"],
}
```

### 1-7. PostgreSQL ID 시퀀스 리셋

**문제:** SQLite→PostgreSQL 마이그레이션 후 시퀀스가 1로 초기화 → UniqueViolation  
**해결:** Supabase SQL Editor에서 직접 실행

```sql
SELECT setval('news_articles_id_seq', (SELECT MAX(id) FROM news_articles));
```

결과: 다음 삽입 ID = 33,138

---

## 2. 보고서 제목 통일 (2026-05-14)

**문제:** Google Docs 생성 실패 시 폴백 제목이 일관되지 않음

| 경우 | 이전 | 이후 |
|------|------|------|
| 일간 Docs 실패 | `ICT 뉴스 트렌드 분석 (2026-05-14)` | `전파·이동통신 동향 보고서 (2026년 05월 14일)` |
| 주간 Docs 실패 | `주간 ICT 뉴스 트렌드 분석 (2026-05-14)` | `전파·이동통신 주간 동향 보고서 (2026년 05월 14일)` |
| 월간 Docs 실패 | `월간 ICT 뉴스 종합 분석 (2026-05-14)` | `전파·이동통신 월간 동향 보고서 (2026년 05월 14일)` |

날짜 포맷도 ISO(`2026-05-14`) → 한국어(`2026년 05월 14일`)로 통일.

---

## 3. AI 분석 시제 오류 수정 (`news_engine.py`)

**문제:** TTA 조치사항이 "2024년 3GPP SA2 #163 회의..." 처럼 2024년 기준으로 생성됨  
**원인:** 프롬프트에 현재 날짜 정보 없음 + 예시에 `"2024년"` 하드코딩

**해결:**

```python
_today = datetime.date.today()
_current_year = _today.year
prompt = f"""
...
**현재 날짜: {_today.strftime('%Y년 %m월 %d일')}** — TTA 조치 사항 작성 시 이 날짜 이후의 미래 시점 또는 현재 기준으로 서술할 것.
...
(예: "{_current_year}년 3GPP SA2 회의 참여하여 6G NTN 관련 세션 기여문서 제출")
...
이미 지난 과거 시점({_current_year - 1}년 이전) 기준의 조치사항 작성 금지
"""
```

---

## 4. 다수 이메일 수신자 지원 (`news_engine.py`)

**문제:** 코드가 `GMAIL_SENDER` 하나만 수신자로 사용 → `ssg@tta.or.kr` 추가 불가

**해결:** `GMAIL_RECEIVERS` 환경변수 신규 지원 (쉼표 구분 복수 주소)

```python
'gmail_receivers': (
    [r.strip() for r in os.environ.get('GMAIL_RECEIVERS', '').split(',') if r.strip()]
    or ([os.environ.get('GMAIL_SENDER')] if os.environ.get('GMAIL_SENDER') else [])
),
```

**Streamlit Cloud Secrets 추가 필요:**
```toml
GMAIL_RECEIVERS = "ironage@tta.or.kr,ssg@tta.or.kr"
```

---

## 5. GitHub Actions → cron-job.org 스케줄 전환

### 배경

GitHub Actions `schedule` 트리거는 서버 부하에 따라 수 시간 지연 발생 (오늘 실측: 3시간 지연).

### 변경 내용

**`.github/workflows/daily-collection.yml` 및 `weekly-report.yml`:**

```yaml
# 이전
on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

# 이후
on:
  workflow_dispatch:   # cron-job.org 또는 수동 실행
```

### cron-job.org 설정

| 항목 | 일간 | 주간 |
|------|------|------|
| URL | `.../daily-collection.yml/dispatches` | `.../weekly-report.yml/dispatches` |
| 실행 시각 | 매일 00:00 UTC (09:00 KST) | 매주 월요일 00:00 UTC |
| Method | POST | POST |
| Body | `{"ref":"main"}` | `{"ref":"main"}` |
| Authorization | `Bearer <PAT>` | `Bearer <PAT>` |

**결과:** `workflow_dispatch`는 즉시 실행 → 지연 없이 09:00 KST 정각에 발동

---

## 6. daily-collection workflow에 Google Docs SA 키 추가

**문제:** `daily-collection.yml`에 `GOOGLE_SERVICE_ACCOUNT_JSON` 미포함 → Docs 생성 실패  
(weekly-report.yml에는 있었으나 daily에 누락)

**해결:**
```yaml
env:
  # 기존 키들 ...
  GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
```

---

## 현재 운영 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| Streamlit Cloud 앱 | ✅ 운영 중 | `ironage-ai-news-noaarvssdkmyjmamgha5cz.streamlit.app` |
| 일간 자동 실행 | ✅ 운영 중 | cron-job.org → 09:00 KST |
| 주간 자동 실행 | ✅ 설정 완료 | 매주 월요일 09:00 KST (cron-job.org) |
| Google Docs 생성 | ⚠️ 확인 필요 | daily workflow에 SA키 추가 → 내일 실행 결과로 확인 |
| 다수 수신자 이메일 | ⚠️ 설정 필요 | Streamlit Cloud Secrets에 `GMAIL_RECEIVERS` 추가 필요 |
| OAuth 로그인 (`@tta.or.kr`) | ✅ 작동 | `ssg@tta.or.kr` 포함 모든 TTA 계정 가능 |

---

## 남은 수동 작업

### A. Streamlit Cloud Secrets 업데이트
```toml
GMAIL_RECEIVERS = "ironage@tta.or.kr,ssg@tta.or.kr"

[auth]
redirect_uri = "https://ironage-ai-news-noaarvssdkmyjmamgha5cz.streamlit.app/oauth2callback"
cookie_secret = "IronAge2026TTA-SuperSecret-32chars!!"
```

> `redirect_uri`의 URL이 실제 앱 주소(`...-noaarvssdkmyjmamgha5cz...`)와 일치하는지 반드시 확인.

### B. Google Docs 생성 확인
내일(2026-05-15) 09:00 KST 자동 실행 후 이메일에 Google Docs 링크가 포함되는지 확인.

---

## 커밋 이력

| 커밋 해시 | 내용 |
|-----------|------|
| `a4c8130` | load_config() 환경변수 폴백 추가 |
| `bd76c8e` | 이메일 제목 None 수정 + Google Docs 오류 화면 표시 |
| `4a2376a` | AI 분석 프롬프트 현재 날짜 컨텍스트 추가 |
| `2ea5f0b` | 보고서 폴백 제목 '전파·이동통신 동향 보고서'로 통일 |
| `227b2d9` | GMAIL_RECEIVERS 환경변수 지원 추가 |
| `d449118` | GitHub Actions schedule 제거 → cron-job.org 전환 |
| `943d85b` | daily workflow에 GOOGLE_SERVICE_ACCOUNT_JSON 추가 |
