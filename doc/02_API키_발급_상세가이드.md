# 02. API 키 발급 상세 가이드

**대상**: 각 외부 서비스의 API 키·인증 정보를 처음 발급하는 담당자  
**목적**: 시스템 운영에 필요한 모든 인증 정보를 빠짐없이 수집

> API 키는 시스템이 외부 서비스에 접근하는 "열쇠"입니다.  
> 이 단계에서 발급된 값들은 이후 설정 파일과 GitHub Secrets에 등록됩니다.

---

## 발급해야 할 키 목록

| 서비스 | 키 종류 | 용도 |
|--------|--------|------|
| OpenAI | API Key | 기사 AI 분석 (필수) |
| 네이버 | Client ID + Secret | 국내 뉴스 수집 (필수) |
| Google | OAuth2 토큰 | Docs 보고서 생성 + Drive 저장 (필수) |
| Gmail | 앱 비밀번호 | 이메일 자동 발송 (필수) |
| Supabase | DATABASE_URL | 클라우드 DB 연결 (필수) |
| Anthropic Claude | API Key | AI 분석 보조 (선택) |
| Google Gemini | API Key | AI 분석 보조 (선택) |
| Perplexity | API Key | AI 분석 보조 (선택) |

> 선택 항목은 없어도 시스템이 동작합니다. OpenAI만 있으면 충분합니다.

---

## 1. OpenAI API 키

01 가이드에서 이미 발급했다면 이 섹션을 건너뜁니다.

**위치**: https://platform.openai.com/api-keys

발급 방법:
1. 로그인 → 좌측 **API keys** 메뉴
2. **+ Create new secret key** 클릭
3. Name: `TTA-News-v5`
4. 생성된 `sk-proj-...` 값 즉시 복사 → 안전 저장

수집 정보:
```
OPENAI_API_KEY = sk-proj-xxxxxxxxxxxx
```

---

## 2. 네이버 뉴스 API

**위치**: https://developers.naver.com/apps

1. 로그인 후 **내 애플리케이션** → 등록한 앱 클릭
2. **인증 정보** 탭에서 확인

수집 정보:
```
NAVER_CLIENT_ID     = xxxxxxxxxxxx
NAVER_CLIENT_SECRET = xxxxxxxxxxxx
```

> 없다면 01 가이드 7번 항목 참조.

---

## 3. Google OAuth2 인증 설정

이 단계가 가장 복잡합니다. Google Docs 자동 생성과 Google Drive 저장에 필요합니다.  
순서를 정확히 따라 주세요.

### 3-1. Google Cloud Console 프로젝트 생성

1. https://console.cloud.google.com 접속
2. 상단 프로젝트 선택 드롭다운 → **새 프로젝트**
3. 프로젝트 이름: `TTA-AI-News` → 만들기

### 3-2. Google Docs API + Drive API 활성화

1. 좌측 메뉴 → **API 및 서비스** → **라이브러리**
2. 검색창에 `Google Docs API` 입력 → 결과 클릭 → **사용 설정**
3. 다시 라이브러리로 돌아가서 `Google Drive API` 검색 → **사용 설정**

### 3-3. OAuth2 동의 화면 구성

1. 좌측 메뉴 → **API 및 서비스** → **OAuth 동의 화면**
2. User Type: **외부** 선택 → 만들기
3. 입력:
   - 앱 이름: `TTA AI News`
   - 사용자 지원 이메일: (내 Gmail)
   - 개발자 연락처 이메일: (내 Gmail)
4. 나머지는 모두 기본값으로 **저장 후 계속** 클릭 (3단계 반복)
5. **테스트 사용자** 섹션에서 **+ ADD USERS** → 본인 Gmail 추가

### 3-4. OAuth2 클라이언트 ID 생성

1. 좌측 메뉴 → **사용자 인증 정보** → **+ 사용자 인증 정보 만들기** → **OAuth 클라이언트 ID**
2. 애플리케이션 유형: **데스크톱 앱**
3. 이름: `TTA-News-Desktop`
4. **만들기** 클릭
5. 팝업에서 **JSON 다운로드** 클릭
6. 다운로드된 파일의 이름을 `credentials.json`으로 변경
7. 프로젝트 폴더에 복사: `2604_AI_news(anti)_1.5/credentials.json`

### 3-5. 초기 인증 실행 (token.json 생성)

프로젝트 폴더에서 아래 명령어 실행:

```bash
python news_engine.py test
```

처음 실행 시 브라우저가 열리고 Google 계정 선택 화면이 나타납니다.

1. Gmail 계정 선택
2. "앱이 Google 계정 접근을 요청합니다" 화면에서 **계속** 클릭
3. Docs + Drive 접근 권한 **허용** 클릭

완료되면 `token.json` 파일이 자동 생성됩니다.

### 3-6. token.json 내용 확인

```bash
type token.json
```

아래 형태의 JSON이 출력되면 성공:

```json
{
  "token": "ya29.xxxx",
  "refresh_token": "1//xxxx",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

이 내용 전체를 복사해 두세요 (GitHub Secrets 등록 시 필요).

---

## 4. Gmail 앱 비밀번호

일반 Gmail 비밀번호를 사용하면 보안 정책으로 차단됩니다.  
반드시 **앱 비밀번호**(16자리)를 사용해야 합니다.

### 전제 조건: 2단계 인증 활성화

1. https://myaccount.google.com 접속
2. 좌측 **보안** 클릭
3. **2단계 인증** → 아직 없으면 **시작하기** 클릭해서 활성화

### 앱 비밀번호 생성

1. https://myaccount.google.com/apppasswords 접속
2. (2단계 인증이 되어 있어야 이 페이지가 보입니다)
3. **앱 비밀번호** 항목에서:
   - 앱: `메일`
   - 기기: `Windows 컴퓨터`
4. **생성** 클릭
5. 화면에 나타나는 **16자리 비밀번호** 즉시 복사 (공백 포함, 예: `abcd efgh ijkl mnop`)

수집 정보:
```
GMAIL_SENDER   = your-email@gmail.com
GMAIL_PASSWORD = abcdefghijklmnop  (공백 제거한 16자리)
```

---

## 5. Supabase DATABASE_URL

01 가이드에서 프로젝트를 만들었다면:

1. https://supabase.com → 내 프로젝트 클릭
2. 좌측 **Settings** → **Database**
3. 스크롤 내려 **Connection string** 섹션
4. 탭에서 **URI** 선택
5. `postgresql://postgres:[YOUR-PASSWORD]@db.xxxx.supabase.co:5432/postgres` 복사
6. `[YOUR-PASSWORD]` 부분을 프로젝트 생성 시 설정한 비밀번호로 교체

수집 정보:
```
DATABASE_URL = postgresql://postgres:your-db-password@db.abcdefgh.supabase.co:5432/postgres
```

---

## 6. (선택) Anthropic Claude API 키

OpenAI 대신 또는 병행해서 Claude를 AI 분석에 사용할 수 있습니다.

1. https://console.anthropic.com 접속 → 가입 또는 로그인
2. 좌측 **API Keys** → **Create Key**
3. 키 이름 입력 → 생성
4. `sk-ant-...` 형태의 키 복사

```
CLAUDE_API_KEY = sk-ant-xxxxxxxxxxxx
```

---

## 7. (선택) Google Gemini API 키

1. https://aistudio.google.com/app/apikey 접속
2. **Create API key** 클릭
3. 프로젝트 선택 후 **Create API key in existing project**
4. 키 복사

```
GEMINI_API_KEY = AIzaxxxxxxxxxxxx
```

---

## 8. (선택) Perplexity API 키

웹 검색 기반 AI 분석에 활용됩니다.

1. https://www.perplexity.ai/settings/api 접속
2. **Generate** 클릭 → API 키 복사

```
PERPLEXITY_API_KEY = pplx-xxxxxxxxxxxx
```

---

## 수집 완료 체크리스트

아래 표에 발급한 값을 기록하고 **안전한 곳(암호화된 메모, 비밀번호 관리자)**에 저장하세요.

```
[ ] OPENAI_API_KEY      = sk-proj-...
[ ] NAVER_CLIENT_ID     = ...
[ ] NAVER_CLIENT_SECRET = ...
[ ] GMAIL_SENDER        = ...@gmail.com
[ ] GMAIL_PASSWORD      = .....................  (16자리 앱 비밀번호)
[ ] DATABASE_URL        = postgresql://postgres:...@db....supabase.co:5432/postgres
[ ] token.json          = 파일 생성 완료 (프로젝트 폴더에 위치)
[ ] CLAUDE_API_KEY      = sk-ant-... (선택)
[ ] GEMINI_API_KEY      = AIza...    (선택)
[ ] PERPLEXITY_API_KEY  = pplx-...   (선택)
```

> **보안 주의**: 이 키들은 절대 이메일, 카카오톡, 문서에 평문으로 공유하지 마세요.  
> GitHub에 커밋되지 않도록 `.gitignore`에 포함되어 있습니다.

모든 항목 완료 후 → **03_설치_및_초기설정.md**로 이동하세요.

---

*소요 시간: 약 1~2시간 (Google OAuth 설정이 가장 오래 걸립니다)*
