# 변경 보고서: Streamlit Cloud 배포 준비 (2026-05-12)

Branch: main  
Status: 진행 중 (코드 완료 / GitHub push + Streamlit Cloud 배포 대기)

---

## 배경 및 목표

IRONAGE AI Analytics System을 TTA 내부 여러 팀이 웹 브라우저에서 접속할 수 있도록
Streamlit Community Cloud에 배포한다.

- 기존: 담당자 PC에서만 로컬 실행 (`streamlit run main_app.py`)
- 목표: `https://YOUR-APP.streamlit.app` URL로 TTA 전 직원 접속

설계 근거: `doc/design-streamlit-cloud-deploy-20260510.md` 참조

---

## 이번 세션에서 완료한 작업

### 1. Supabase PostgreSQL 연동 (주 1 완료)

**배경:** Streamlit Cloud는 재시작 시 파일시스템 초기화 → SQLite 사용 불가.

**`news_engine.py` — `init_database()` 수정:**
- `DATABASE_URL` 환경변수(또는 Streamlit Secrets)가 있으면 PostgreSQL 연결
- 없으면 로컬 SQLite 폴백 유지
- `postgresql://` → `postgresql+psycopg2://` 자동 변환

**`check_and_migrate_database()` 수정:**
- SQLite 전용 `PRAGMA` / `sqlite3` 직접 호출 제거
- SQLAlchemy Inspector 기반으로 DB-agnostic하게 교체
- `user_settings` 테이블 자동 생성 추가 (PostgreSQL: SERIAL, SQLite: AUTOINCREMENT)

**`requirements.txt` 추가:**
```
psycopg2-binary==2.9.9
python-dotenv==1.0.0
```

**`.env` 파일 생성 (gitignore 처리):**
```
DATABASE_URL=postgresql://postgres.xxx:IronAge2026!TTA@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres
```

**`.gitignore` 생성:** `.env`, `data/news.db`, `data/logs/`, `credentials.json`, `token.json` 등 제외

**데이터 마이그레이션:**
- `migrate_sqlite_to_postgres.py` 작성 (1회용)
- SQLite 컬럼 → PostgreSQL 컬럼 자동 필터링 (`keywords` 컬럼 제외)
- boolean 타입 자동 변환 (SQLite int 0/1 → Python bool)
- 결과: `news_articles` 32,137건, `article_embeddings` 695건 이전 완료
- `python news_engine.py test` 확인: `total: 32,137 / PostgreSQL 연결 모드`

---

### 2. Google Docs — Service Account 전환 (주 2)

**배경:** 기존 `token.json` OAuth2 방식은 90일 후 만료 → GitHub Actions headless 환경에서 재인증 불가.

**`news_engine.py` — `get_google_docs_service()` 교체:**

인증 우선순위:
1. 환경변수 `GOOGLE_SERVICE_ACCOUNT_JSON` (GitHub Secrets / Streamlit Secrets)
2. 로컬 파일 `ironage-sa.json`
3. 레거시 `token.json` (로컬 개발 전용 폴백)

```python
from google.oauth2 import service_account
# ...
sa_json_str = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
if sa_json_str:
    creds = service_account.Credentials.from_service_account_info(json.loads(sa_json_str), scopes=SCOPES)
```

**미완료 (수동 작업):**
- Google Cloud Console에서 서비스 계정 `ironage-docs-writer` 발급
- Drive 보고서 폴더에 서비스 계정 이메일 편집자 권한 부여
- `ironage-sa.json` 다운로드 → GitHub Secrets `GOOGLE_SERVICE_ACCOUNT_JSON`에 등록

---

### 3. Google OAuth 인증 추가 (주 2)

**`main_app.py` — `st.set_page_config()` 직후 삽입:**

```python
_auth_enabled = hasattr(st.experimental_user, 'is_logged_in')

if _auth_enabled:
    if not st.experimental_user.is_logged_in:
        # 로그인 버튼 표시 → st.login()
        st.stop()
    _user_email = st.experimental_user.email or ""
    if not _user_email.endswith("@tta.or.kr"):
        # 도메인 차단 → st.logout()
        st.stop()
else:
    _user_email = "local@tta.or.kr"  # 로컬 개발 모드
```

로컬 환경(`_auth_enabled = False`)에서는 인증 블록 전체 우회 → 개발 편의성 유지.

**사이드바 업데이트:**
- 사용자 이름(`_user_name`) + 이메일(`_user_email`) 표시
- 로그아웃 버튼 추가

**Streamlit Cloud Secrets에 추가 필요 (미완료):**
```toml
[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "32자 이상 랜덤 문자열"
```

---

### 4. user_settings — 개인 설정 기능 (주 2)

**`news_engine.py` — 헬퍼 함수 2개 추가:**

| 함수 | 역할 |
|------|------|
| `load_user_settings(user_email)` | DB에서 사용자 설정 조회 (없으면 `{}`) |
| `save_user_settings(user_email, settings)` | upsert 저장 (PostgreSQL ON CONFLICT) |

저장 필드: `keywords`, `ai_model`, `email_recipients`, `schedule_daily`, `schedule_weekly`

**`main_app.py` — "내 설정" 탭 신규 추가:**
- 키워드 설정 (줄바꿈 구분)
- AI 모델 선택 (Gemini / GPT-4o / Claude / Perplexity)
- 수신 이메일 설정
- 일일/주간 자동 실행 체크박스
- 💾 설정 저장 버튼 → Supabase `user_settings` 테이블에 영구 저장

사이드바 메뉴에 "내 설정" 항목 추가 (6번째).

**동작 확인:**
```
load_user_settings: {}
save 완료
reload: {'keywords': ['5G', '위성통신'], 'ai_model': 'gemini', ...}  ✅
```

---

### 5. GitHub Actions 워크플로우 생성 (주 3)

**`.github/workflows/daily-collection.yml`:**
- cron: `0 0 * * *` (매일 09:00 KST)
- `python news_engine.py daily`
- 환경변수: DATABASE_URL, OPENAI_API_KEY, GEMINI_API_KEY, CLAUDE_API_KEY, PERPLEXITY_API_KEY, NAVER_*, GMAIL_*

**`.github/workflows/weekly-report.yml`:**
- cron: `0 0 * * 1` (매주 월요일 09:00 KST)
- `python news_engine.py weekly`
- 환경변수: 위와 동일 + `GOOGLE_SERVICE_ACCOUNT_JSON`

---

### 6. Git 초기화 + 첫 커밋

```
git init
git add [주요 파일 27개]
git commit -m "IRONAGE AI Analytics System v5.0 초기 배포"
```

커밋 해시: `f989931`  
스테이징된 파일 수: 27개

---

## 현재 진행 상태

| 단계 | 항목 | 상태 |
|------|------|------|
| 주 1 | Supabase 연동 + 데이터 이전 | ✅ 완료 |
| 주 2 | Service Account 코드 | ✅ 완료 |
| 주 2 | Google OAuth 코드 | ✅ 완료 |
| 주 2 | user_settings 탭 | ✅ 완료 |
| 주 2 | Service Account 발급 (수동) | ✅ 완료 (2026-05-13) |
| 주 2 | GitHub push | ✅ 완료 (2026-05-13) |
| 주 2 | Streamlit Cloud 배포 | ✅ 완료 (2026-05-13) |
| 주 3 | GitHub Actions 워크플로우 파일 | ✅ 완료 |
| 주 3 | GitHub Secrets 등록 (수동) | ✅ 완료 (2026-05-13) |

→ 이후 안정화 작업: `doc/change-report-deploy-stabilization-20260514.md` 참조

---

## 남은 수동 작업

### A. GitHub push

```bash
# github.com에서 ironage-ai-news (private) 리포 생성 후:
git remote add origin https://github.com/YOUR_USERNAME/ironage-ai-news.git
git branch -M main
git push -u origin main
```

### B. Google Cloud Service Account 발급

```
1. console.cloud.google.com (@tta.or.kr 계정)
2. IAM & Admin → Service Accounts → "서비스 계정 만들기"
   이름: ironage-docs-writer
3. "키 만들기" → JSON → ironage-sa.json 다운로드
4. Google Docs API + Drive API 활성화
5. Drive 보고서 폴더 → 서비스 계정 이메일에 편집자 권한 부여
```

### C. GitHub Secrets 등록

Repository Settings → Secrets and variables → Actions:

| Secret 이름 | 값 출처 |
|-------------|---------|
| `DATABASE_URL` | Supabase → Settings → Database → URI |
| `OPENAI_API_KEY` | data/config.json |
| `GEMINI_API_KEY` | data/config.json |
| `CLAUDE_API_KEY` | data/config.json |
| `PERPLEXITY_API_KEY` | data/config.json |
| `NAVER_CLIENT_ID` | data/config.json |
| `NAVER_CLIENT_SECRET` | data/config.json |
| `GMAIL_SENDER` | data/config.json |
| `GMAIL_PASSWORD` | data/config.json |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ironage-sa.json 전체 내용 |

### D. Streamlit Cloud 배포

```
1. share.streamlit.io → "New app"
2. GitHub 리포: ironage-ai-news / main / main_app.py
3. Secrets 탭에 동일 키 입력 + [auth] 섹션 추가:

[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "32자 이상 랜덤 문자열"
```

---

## 파일 변경 목록

| 파일 | 변경 유형 | 주요 내용 |
|------|----------|----------|
| `news_engine.py` | 수정 | PostgreSQL 연동, Service Account, user_settings 함수 |
| `main_app.py` | 수정 | Google OAuth, 내 설정 탭, 사이드바 업데이트 |
| `requirements.txt` | 수정 | psycopg2-binary, python-dotenv 추가 |
| `.env` | 신규 (gitignore) | DATABASE_URL |
| `.gitignore` | 신규 | 시크릿/데이터 파일 제외 |
| `migrate_sqlite_to_postgres.py` | 신규 | 1회용 이전 스크립트 |
| `.github/workflows/daily-collection.yml` | 신규 | 일일 수집 자동화 |
| `.github/workflows/weekly-report.yml` | 신규 | 주간 리포트 자동화 |

---

## 다음 세션 시작 시 확인 사항

1. GitHub push 완료 여부
2. Service Account JSON 발급 완료 여부
3. Streamlit Cloud 배포 URL 확인
4. Google OAuth 로그인 동작 테스트 (@tta.or.kr 계정)
5. "내 설정" 탭 저장 동작 확인
