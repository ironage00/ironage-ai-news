# 04. GitHub + Supabase 배포 가이드

**대상**: 로컬 테스트를 완료한 담당자  
**목적**: 클라우드 자동화 배포 — "서버 없이 매일 자동으로 실행"되는 환경 구축

---

## 배포 구조 이해

로컬 PC에서는 수동으로 `python news_engine.py daily`를 실행했습니다.  
배포 후에는 **아무도 아무것도 누르지 않아도** 매일 오전 9시에 자동으로 실행됩니다.

```
[cron-job.org]
매일 09:00 KST
  └──신호 전송──▶ [GitHub Actions]
                   클라우드 서버 임시 생성
                   코드 실행: news_engine.py daily
                         ↓
                   [Supabase DB] 기사 저장
                         ↓
                   Gmail 발송 + Google Docs 생성
                   서버 자동 소멸
```

---

## STEP 1: GitHub Secrets 등록

GitHub Actions가 실행될 때 API 키가 필요합니다.  
API 키는 코드에 직접 쓰지 않고 **Secrets**(암호화된 변수)에 저장합니다.

### 등록 방법

1. https://github.com/YOUR-GITHUB-ID/ironage-ai-news 접속
2. 상단 메뉴 **Settings** 클릭
3. 좌측 **Secrets and variables** → **Actions** 클릭
4. **New repository secret** 클릭

아래 항목을 하나씩 추가합니다.

| Secret 이름 | 값 |
|-------------|---|
| `DATABASE_URL` | Supabase 연결 문자열 전체 |
| `OPENAI_API_KEY` | `sk-proj-...` |
| `NAVER_CLIENT_ID` | 네이버 Client ID |
| `NAVER_CLIENT_SECRET` | 네이버 Client Secret |
| `GMAIL_SENDER` | 발송용 Gmail 주소 |
| `GMAIL_PASSWORD` | Gmail 앱 비밀번호 (16자리) |
| `GOOGLE_TOKEN_JSON` | token.json 파일의 전체 내용 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | (선택, 서비스 계정 방식) |
| `CLAUDE_API_KEY` | (선택) Claude API 키 |
| `GEMINI_API_KEY` | (선택) Gemini API 키 |
| `PERPLEXITY_API_KEY` | (선택) Perplexity API 키 |

### GOOGLE_TOKEN_JSON 등록 방법

`token.json` 파일의 내용 전체를 복사해서 붙여 넣습니다.

```bash
# 파일 내용 확인
type token.json
```

출력된 JSON 전체를 복사 → `GOOGLE_TOKEN_JSON` Secret 값에 붙여넣기

---

## STEP 2: Supabase DB 테이블 초기화

Supabase에 테이블이 없으면 코드가 자동으로 만들지만,  
처음 한 번은 로컬에서 연결 테스트를 해두는 것이 안전합니다.

로컬에서 .env 파일에 DATABASE_URL이 있는 상태로:

```bash
python news_engine.py test
```

출력에 `[DB] Supabase(PostgreSQL) 연결됨` 이 보이면 클라우드 DB 연결 성공.

---

## STEP 3: GitHub Actions 워크플로우 확인

프로젝트에는 이미 워크플로우 파일이 포함되어 있습니다.

```
.github/
└── workflows/
    ├── daily-collection.yml   ← 매일 수집 + 분석 + 이메일
    └── weekly-report.yml      ← 매주 주간 리포트
```

### 워크플로우 파일 내용 확인

`.github/workflows/daily-collection.yml`:

```yaml
name: Daily News Collection

on:
  workflow_dispatch:   # cron-job.org 또는 수동 실행

env:
  TZ: Asia/Seoul       # 한국 시간대 설정

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 150
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run daily collection
        run: python news_engine.py daily
        env:
          DATABASE_URL:       ${{ secrets.DATABASE_URL }}
          OPENAI_API_KEY:     ${{ secrets.OPENAI_API_KEY }}
          NAVER_CLIENT_ID:    ${{ secrets.NAVER_CLIENT_ID }}
          NAVER_CLIENT_SECRET: ${{ secrets.NAVER_CLIENT_SECRET }}
          GMAIL_SENDER:       ${{ secrets.GMAIL_SENDER }}
          GMAIL_PASSWORD:     ${{ secrets.GMAIL_PASSWORD }}
          GOOGLE_TOKEN_JSON:  ${{ secrets.GOOGLE_TOKEN_JSON }}
          ...
```

### 수동 실행으로 테스트

1. GitHub 저장소 → **Actions** 탭 클릭
2. 좌측 목록에서 **Daily News Collection** 클릭
3. 우측 **Run workflow** 버튼 클릭 → **Run workflow** 확인
4. 실행 상태 모니터링 (초록색 체크 = 성공, 빨간색 X = 실패)

실행 중 로그 확인:
- Actions 탭 → 실행 중인 작업 클릭 → `collect` 클릭 → 로그 실시간 확인

---

## STEP 4: cron-job.org 자동 스케줄 등록

매일 오전 9시(KST)에 GitHub Actions를 자동으로 시작하는 설정입니다.

### GitHub Personal Access Token 발급

cron-job.org가 GitHub에 신호를 보내려면 토큰이 필요합니다.

1. https://github.com/settings/tokens 접속
2. **Generate new token (classic)** 클릭
3. Note: `cron-job-trigger`
4. Expiration: `No expiration` 또는 1년
5. Scopes에서 `workflow` 체크
6. **Generate token** 클릭
7. `ghp_...` 형태의 토큰 즉시 복사 (한 번만 표시됨)

### cron-job.org 작업 등록

**일일 수집 (매일 09:00 KST)**

1. https://cron-job.org 로그인
2. **Cronjobs** → **Create cronjob** 클릭
3. 설정:
   - **Title**: `TTA AI News - Daily`
   - **URL**: `https://api.github.com/repos/YOUR-GITHUB-ID/ironage-ai-news/actions/workflows/daily-collection.yml/dispatches`
     - `YOUR-GITHUB-ID`를 본인 GitHub 아이디로 교체
   - **Schedule**: Custom → `0 0 * * *` (UTC 00:00 = KST 09:00)
   - **Request method**: `POST`
   - **Request headers** 추가:
     - `Authorization`: `Bearer ghp_발급받은_토큰`
     - `Accept`: `application/vnd.github.v3+json`
     - `Content-Type`: `application/json`
   - **Request body**:
     ```json
     {"ref":"main"}
     ```
4. **Create** 클릭

**주간 리포트 (매주 월요일 09:00 KST)**

같은 방법으로 두 번째 작업 등록:
- **Title**: `TTA AI News - Weekly`
- **URL**: `.../workflows/weekly-report.yml/dispatches`
- **Schedule**: `0 0 * * 1` (UTC 00:00 월요일 = KST 09:00 월요일)
- 나머지 동일

### 등록 확인

1. cron-job.org 대시보드에서 두 작업이 **Active** 상태인지 확인
2. **Test run** 버튼으로 즉시 실행 테스트 가능

---

## STEP 5: Streamlit Community Cloud 배포 (선택)

웹 대시보드를 외부에서 접속 가능한 URL로 공개 배포합니다.  
PC를 켜두지 않아도 언제 어디서나 대시보드를 볼 수 있습니다.

### 배포 방법

1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인
2. **New app** 클릭
3. 설정:
   - **Repository**: `YOUR-GITHUB-ID/ironage-ai-news`
   - **Branch**: `main`
   - **Main file path**: `main_app.py`
4. **Advanced settings** 클릭 → **Secrets** 탭
5. 아래 내용을 TOML 형식으로 입력:

```toml
DATABASE_URL = "postgresql://postgres:비밀번호@db.xxxx.supabase.co:5432/postgres"
OPENAI_API_KEY = "sk-proj-..."
NAVER_CLIENT_ID = "..."
NAVER_CLIENT_SECRET = "..."
GMAIL_SENDER = "...@gmail.com"
GMAIL_PASSWORD = "..."
GOOGLE_TOKEN_JSON = '''
{
  "token": "ya29.xxxx",
  "refresh_token": "1//xxxx",
  ...
}
'''
```

6. **Deploy** 클릭
7. 약 2~3분 후 `https://your-app-name.streamlit.app` URL로 접속 가능

> 무료 플랜 제한: 앱이 7일간 접속 없으면 자동 슬립 상태로 전환됨.  
> 접속하면 즉시 재시작됩니다.

---

## 배포 완료 확인

```
[ ] GitHub Secrets 10개 항목 등록 완료
[ ] Actions 수동 실행 → 성공 (초록 체크)
[ ] cron-job.org 일일/주간 작업 등록 → Active
[ ] 첫 번째 자동 실행 후 이메일 수신 확인
[ ] (선택) Streamlit Cloud 배포 → URL 접속 확인
```

---

## 이후 일상 운영

배포가 완료되면 시스템은 **완전 자동**으로 운영됩니다.

담당자가 할 일:
- 매일 오전 이메일 확인
- 주 1회 GitHub Actions 탭에서 실행 성공 여부 확인
- 필요 시 웹 대시보드에서 상세 검색/분석

자세한 운영 방법과 문제 해결은 → **06_운영_및_장애처리.md** 참조

---

*소요 시간: 약 1~2시간*
