# 변경 보고서: 운영 버그 수정 및 안정화 (2026-05-19~20)

Branch: main  
Status: ✅ 완료 — Supabase 연동 정상, Google Docs OAuth2 전환 완료

---

## 배경

2026-05-14 이후 실제 운영 과정에서 아래 5가지 문제가 발견되어 수정하였다.

1. 매일 오전 9시 외에 오후 12~13시에도 중복 이메일 발송
2. TTA 조치사항이 매일 동일한 내용으로 반복 출력
3. Google Docs 생성 실패 (403 Permission Denied)
4. 이메일 생성 중 NoneType 크래시 (주간 리포트)
5. Streamlit 대시보드에 수집 데이터 미반영

---

## 1. 중복 이메일 발송 방지 (2026-05-19)

### 원인

- GitHub Actions `schedule: cron '0 0 * * *'` 과 cron-job.org가 **동시에** 작동 중
- 09:00 KST GitHub Actions 실행 + 12~13시 cron-job.org 실행 → 하루 2회 이메일 발송

### 해결 — DB 기반 중복 실행 방지 (`news_engine.py`)

`run_daily_collection()` 진입 시 오늘 이미 분석된 기사가 5건 이상이면 즉시 종료.

```python
_today_start = datetime.datetime.now(datetime.timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0
)
with get_db_session() as _s:
    _today_analyzed = _s.query(NewsArticle).filter(
        NewsArticle.collected_at >= _today_start,
        NewsArticle.is_analyzed == True
    ).count()
if _today_analyzed >= 5:
    log_info(f"ℹ️ 오늘 이미 {_today_analyzed}개 기사 분석 완료 — 중복 실행 건너뜀.")
    return []
```

> **권고**: cron-job.org 설정 비활성화 권장 (현재 GitHub Actions `0 0 * * *` 스케줄이 9시 KST를 담당)

---

## 2. TTA 조치사항 반복 문제 수정 (`news_engine.py`)

### 원인

AI 분석 프롬프트의 예시 문장(`3GPP SA2 회의 참여하여 위성 통신 관련 세션에 기여문서 제출...`)을
모델이 매번 그대로 복사하여 출력.

### 해결

- 예시를 **다른 도메인**(ITU-T FG-AI4EE / 에너지 효율)으로 교체
- 프롬프트에 명시적 복사 금지 지시 추가

```python
(예: "ITU-T FG-AI4EE 회의에 참가하여 AI 기반 네트워크 에너지 효율화 관련 기여문서 제출")
**주의: 위 예시를 절대 그대로 복사하지 말 것. 반드시 해당 기사 내용 기반으로 작성.**
```

---

## 3. Google Docs 생성 실패 수정 (2026-05-19~20)

### 원인 분석

`get_google_docs_service()`가 **서비스 계정(Service Account)**만 사용하고 있었는데,
서비스 계정은 구조적으로 Google Docs 문서를 생성할 수 없음 (403 Permission Denied).

| 인증 방식 | Docs 생성 | Drive 파일 업로드 | 비고 |
|-----------|-----------|-------------------|------|
| 서비스 계정 | ❌ 불가 | ❌ 불가 (quota 없음) | `storageQuotaExceeded` |
| OAuth2 사용자 토큰 | ✅ 가능 | ✅ 가능 | `token.json` + `refresh_token` |

> Google Docs API는 활성화 상태였으나 서비스 계정 자체의 한계로 실패.

### 해결 — OAuth2 사용자 토큰 우선 사용 (`news_engine.py`)

`get_google_docs_service()`의 인증 우선순위를 재정의:

```
Priority 1: GOOGLE_TOKEN_JSON 환경변수 (OAuth2 user token)
Priority 2: Streamlit secrets의 GOOGLE_TOKEN_JSON
Priority 3: 로컬 token.json 파일
Priority 4: 서비스 계정 (Drive 읽기 전용 폴백)
Priority 5: 브라우저 재인증 (로컬 개발 환경 전용)
```

```python
token_json_str = os.environ.get('GOOGLE_TOKEN_JSON')
...
creds = Credentials.from_authorized_user_info(token_info, SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())   # refresh_token으로 자동 갱신
```

### 워크플로우 변경

`daily-collection.yml` 및 `weekly-report.yml`에 `GOOGLE_TOKEN_JSON` 추가:

```yaml
env:
  GOOGLE_TOKEN_JSON: ${{ secrets.GOOGLE_TOKEN_JSON }}
```

### 필수 수동 작업

GitHub 저장소 → Settings → Secrets → **`GOOGLE_TOKEN_JSON`** 신규 등록  
(값: 로컬 `token.json` 파일 전체 내용)

---

## 4. Google Docs batchUpdate UTF-16 인덱스 오류 수정 (`news_engine.py`)

### 원인

Google Docs API는 텍스트 위치를 **UTF-16 코드 유닛** 기준으로 계산하는데,
이모지(📈, ✅ 등, U+10000 이상)는 Python `len()` = 1이지만 UTF-16 = **2유닛**.
→ 이모지가 포함된 단락 이후 모든 삽입 위치가 틀어져 batchUpdate 실패.

### 해결

```python
def _utf16_len(s: str) -> int:
    """Google Docs API는 UTF-16 코드 유닛 기준으로 위치를 계산함. 이모지(U+10000+)는 2유닛."""
    return len(s.encode('utf-16-le')) // 2
```

`generate_google_doc_report()` 내 `index += len(X)` 27곳을 `index += _utf16_len(X)`로 전체 교체.

---

## 5. 주간 리포트 이메일 NoneType 크래시 수정 (`news_engine.py`)

### 원인

DB에서 `analysis_result` 컬럼 값이 `None`인 기사가 있을 때,
`data.get('analysis_result', '')` 는 키가 존재하면 `None`을 그대로 반환 → `.replace()` 호출 시 AttributeError.

### 해결

```python
# 이전
analysis_text = data.get('analysis_result', '')

# 이후
analysis_text = data.get('analysis_result') or ''
```

except 블록 내 문자열 처리에도 방어 추가:

```python
main_content = (main_content or "주요내용 정보를 찾을 수 없습니다.").replace('ㅇ', '•')
implications = (implications or "시사점 정보를 찾을 수 없습니다.").replace('ㅇ', '•')
```

---

## 6. Streamlit 대시보드 데이터 미반영 수정 (2026-05-20)

### 원인 분석

```
GitHub Actions daily-collection    Streamlit Cloud 대시보드
───────────────────────────────    ──────────────────────────
DATABASE_URL 없음                  DATABASE_URL 있음
        ↓                                  ↓
SQLite (data/news.db, 임시)   ≠   Supabase PostgreSQL
        ↓                                  ↓
GitHub Cache에만 저장          대시보드는 여기서 읽음 → 데이터 없음!
```

`daily-collection.yml`에 `DATABASE_URL`이 없어서 수집 데이터가 SQLite에만 저장되고,
Supabase를 읽는 Streamlit 대시보드에는 반영되지 않았음.

### 해결 — `DATABASE_URL` 추가 (`daily-collection.yml`)

```yaml
- name: Run daily collection
  run: python news_engine.py daily
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}   # ← 신규 추가
    OPENAI_API_KEY: ...
```

**결과:** 수집 즉시 Supabase에 저장 → 대시보드 실시간 반영.

---

## 7. DB 영속성 — Google Drive → GitHub Actions Cache 전환 (2026-05-19)

### 배경

서비스 계정은 Drive에 바이너리 파일(SQLite DB)을 업로드할 수 없음 (`storageQuotaExceeded`).
→ `Upload DB to Google Drive` 스텝이 매번 실패하여 5/19 데이터 전체 누락.

### 해결 — GitHub Actions Cache 방식으로 교체 (`daily-collection.yml`)

```yaml
- name: Restore DB from cache
  uses: actions/cache/restore@v4
  with:
    path: data/news.db
    key: news-db-${{ github.run_id }}
    restore-keys: |
      news-db-

- name: Save DB to cache
  if: always()
  uses: actions/cache/save@v4
  with:
    path: data/news.db
    key: news-db-${{ github.run_id }}
```

> Supabase(`DATABASE_URL`)가 주 저장소이므로 Cache의 SQLite는 로컬 임시 용도로만 활용됨.

---

## 8. GitHub Actions Node.js 24 사전 마이그레이션 (2026-05-20)

### 배경

GitHub Actions 경고: `actions/checkout@v4`, `setup-python@v5`, `cache/restore@v4`, `cache/save@v4` 가
Node.js 20 기반이며, **2026-06-02부터 Node.js 24가 기본값으로 강제 적용**됨.

### 해결 — 두 워크플로우 모두에 env 추가

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
```

> 2026-09-16에 Node.js 20 완전 제거 예정. 현재 설정으로 영향 없음.

---

## Supabase DB 현황 (2026-05-20 기준)

| 항목 | 값 |
|------|-----|
| 전체 기사 | 34,244건 |
| 분석 완료 | 868건 |
| 최근 수집 | 2026-05-20 (232건 / 20건 분석) |

### 일별 수집 현황

| 날짜 | 수집 | 분석 | 비고 |
|------|------|------|------|
| 2026-05-20 | 232건 | 20건 | ✅ 정상 |
| 2026-05-19 | 0건 | 0건 | ❌ Drive 업로드 실패로 누락 |
| 2026-05-18 | 330건 | 30건 | ✅ 정상 |
| 2026-05-17 | 238건 | 31건 | ✅ 정상 |
| 2026-05-16 | 317건 | 30건 | ✅ 정상 |

---

## 현재 운영 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| Streamlit Cloud 앱 | ✅ 운영 중 | ironage-ai-news-noaarvssdkmyjmamgha5cz.streamlit.app |
| 일간 자동 실행 | ✅ 운영 중 | GitHub Actions `0 0 * * *` → 09:00 KST |
| 중복 실행 방지 | ✅ 적용 | DB 기반 (오늘 분석 기사 ≥5건 시 건너뜀) |
| Supabase 저장 | ✅ 정상 | daily-collection에 DATABASE_URL 추가 완료 |
| Google Docs 생성 | ⚠️ 확인 필요 | GOOGLE_TOKEN_JSON Secret 등록 후 다음 실행으로 검증 |
| 이메일 NoneType 오류 | ✅ 수정 | `or ''` 방어 처리 |
| Node.js 24 준비 | ✅ 완료 | FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true |

---

## 남은 수동 작업

### A. GitHub Secret 등록 (필수 — Google Docs 생성용)
- 항목: `GOOGLE_TOKEN_JSON`
- 값: 로컬 `token.json` 파일 전체 내용
- 경로: GitHub → Settings → Secrets and variables → Actions

### B. cron-job.org 비활성화 (권장)
- GitHub Actions 스케줄이 9시 KST를 이미 담당
- cron-job.org가 살아있으면 중복 Actions 비용 발생

---

## 커밋 이력

| 커밋 해시 | 내용 |
|-----------|------|
| `c5ae40f` | Google Docs OAuth2 전환, NoneType 수정, UTF-16 인덱스 수정, 중복 방지, TTA 프롬프트 수정, DB Cache 전환 |
| `fb7b3df` | Node.js 24 마이그레이션 (FORCE_JAVASCRIPT_ACTIONS_TO_NODE24) |
| `4fc963e` | daily-collection에 DATABASE_URL 추가 — Supabase 연동 복구 |
