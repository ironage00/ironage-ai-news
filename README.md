# 🚀 IRONAGE AI Analytics System v4.2

**ICT/통신 업계 뉴스 수집 및 AI 분석 시스템**

한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀을 위한  
자동화된 뉴스 수집, AI 분석, 트렌드 리포트 생성 시스템

---

## 📋 목차

1. [시스템 개요](#-시스템-개요)
2. [주요 기능](#-주요-기능)
3. [기술 스택](#-기술-스택)
4. [설치 방법](#-설치-방법)
5. [사용 방법](#-사용-방법)
6. [설정 가이드](#-설정-가이드)
7. [프로젝트 구조](#-프로젝트-구조)
8. [API 문서](#-api-문서)
9. [문제 해결](#-문제-해결)

---

## 🎯 시스템 개요

### 목적
ICT/통신 분야의 최신 뉴스를 자동으로 수집하고, AI를 활용해 핵심 이슈와 트렌드를 분석하여 
주간/월간 리포트를 자동 생성하는 시스템입니다.

### 주요 사용자
- 한국정보통신기술협회(TTA) 표준화 전문가
- ICT/통신 업계 애널리스트
- 기술 정책 연구자

### 핵심 가치
- ⏱️ **시간 절약**: 수동 뉴스 수집 시간을 90% 감축
- 🎯 **정확한 분석**: AI 기반 핵심 이슈 자동 도출
- 📊 **자동화**: 일일/주간/월간 리포트 자동 생성 및 발송
- 🔄 **통합 관리**: 웹 대시보드를 통한 중앙 집중식 관리

---

## ✨ 주요 기능

### 1. 📰 자동 뉴스 수집
- **Google Alerts RSS**: 맞춤형 키워드 기반 실시간 수집
- **Naver 뉴스 API**: 국내 ICT 뉴스 통합 검색
- **중복 제거**: URL 기반 자동 중복 필터링
- **품질 평가**: AI 기반 뉴스 품질 점수 산출

### 2. 🤖 AI 분석 엔진 (멀티 모델)
- **OpenAI GPT-4**: 정교한 자연어 분석
- **Anthropic Claude**: 장문 컨텍스트 분석
- **Google Gemini**: 다국어 및 멀티모달 분석
- **Perplexity**: 실시간 웹 검색 기반 분석

**분석 항목:**
- 핵심 키워드 추출
- 주요 이슈 요약
- 산업 영향도 평가
- 트렌드 패턴 분석

### 3. 📊 트렌드 리포트 생성
- **주간 리포트**: 7일간 핵심 이슈 TOP 5
- **월간 리포트**: 30일간 종합 트렌드 분석
- **Google Docs 자동 생성**: 서식이 적용된 전문 리포트
- **HTML 이메일**: 시각적으로 세련된 요약 리포트

### 4. 🖥️ 웹 대시보드 (Streamlit)
- **실시간 수집**: 버튼 클릭으로 즉시 뉴스 수집
- **분석 시각화**: Plotly 차트로 트렌드 표시
- **설정 관리**: GUI를 통한 API 키 및 키워드 설정
- **통계 대시보드**: 수집/분석 현황 실시간 모니터링

### 5. 📧 자동 이메일 발송
- **Gmail SMTP**: 안전한 이메일 발송
- **HTML 리포트**: 모바일 최적화된 반응형 디자인
- **첨부 링크**: Google Docs 전체 리포트 링크
- **다중 수신자**: 여러 이메일 주소 동시 발송

### 6. 🗄️ 데이터베이스 관리
- **SQLite**: 로컬 파일 기반 데이터베이스
- **자동 마이그레이션**: 스키마 변경 시 자동 업데이트
- **백업 지원**: 데이터 손실 방지
- **인덱싱**: 빠른 검색 성능

---

## 🛠️ 기술 스택

### Backend
- **Python 3.9+**
- **SQLAlchemy 2.0**: ORM 데이터베이스
- **OpenAI SDK**: GPT-4 분석
- **Google API**: Docs/Drive 통합
- **feedparser**: RSS 피드 파싱
- **BeautifulSoup4**: 웹 스크래핑

### Frontend
- **Streamlit**: 웹 대시보드
- **Plotly**: 인터랙티브 차트
- **Pandas**: 데이터 처리

### Infrastructure
- **SQLite**: 데이터 저장
- **Gmail SMTP**: 이메일 발송
- **Windows 작업 스케줄러**: 자동화

---

## 📦 설치 방법

### 1. 시스템 요구사항
```
OS: Windows 10/11, macOS, Linux
Python: 3.9 이상
메모리: 최소 4GB RAM
저장공간: 500MB 이상
```

### 2. Python 패키지 설치
```bash
# 저장소 클론 (또는 파일 다운로드)
cd IRONAGE_AI_Analytics

# 가상 환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 3. 디렉토리 구조 생성
```bash
mkdir -p data/logs
mkdir -p data/reports
```

### 4. 설정 파일 생성
```bash
# data/config.json 파일 생성 (또는 웹 UI에서 설정)
{
  "openai_api_key": "sk-...",
  "naver_client_id": "...",
  "naver_client_secret": "...",
  "gmail_sender": "your-email@gmail.com",
  "gmail_password": "your-app-password",
  "gmail_receivers": ["receiver@example.com"],
  "google_alerts_rss": [
    "https://www.google.com/alerts/feeds/..."
  ],
  "naver_queries": ["5G", "6G", "IoT", "AI"]
}
```

---

## 🚀 사용 방법

### 웹 대시보드 실행
```bash
streamlit run main_app.py
```

브라우저에서 `http://localhost:8501` 접속

### CLI 명령어

#### 일일 뉴스 수집 및 분석
```bash
python news_engine.py daily
```

**실행 내용:**
1. Google Alerts RSS 수집
2. Naver 뉴스 검색
3. AI 기반 품질 필터링
4. 핵심 뉴스 AI 분석
5. 데이터베이스 저장

#### 주간 트렌드 리포트
```bash
python news_engine.py weekly
```

**생성 내용:**
- 최근 7일간 뉴스 분석
- 핵심 이슈 TOP 5 도출
- Google Docs 리포트
- HTML 이메일 발송

#### 월간 종합 리포트
```bash
python news_engine.py monthly
```

**생성 내용:**
- 최근 30일간 트렌드 분석
- 기술 하이라이트
- 시장 인사이트
- 주차별 변화 추이

#### DB 통계 확인
```bash
python news_engine.py test
```

---

## ⚙️ 설정 가이드

### 1. OpenAI API 키 발급
1. https://platform.openai.com 접속
2. API Keys 메뉴에서 새 키 생성
3. `data/config.json`에 추가:
   ```json
   "openai_api_key": "sk-proj-..."
   ```

### 2. Naver API 키 발급
1. https://developers.naver.com/apps 접속
2. 애플리케이션 등록
3. 검색 API 추가
4. 키 복사 후 설정:
   ```json
   "naver_client_id": "...",
   "naver_client_secret": "..."
   ```

### 3. Gmail 앱 비밀번호 발급
1. Google 계정 > 보안 > 2단계 인증 활성화
2. 앱 비밀번호 생성
3. 16자리 비밀번호 설정:
   ```json
   "gmail_sender": "your-email@gmail.com",
   "gmail_password": "abcd efgh ijkl mnop"
   ```

### 4. Google Docs API 인증
1. https://console.cloud.google.com 접속
2. 프로젝트 생성
3. Google Docs API + Google Drive API 활성화
4. OAuth 2.0 클라이언트 ID 생성
5. `credentials.json` 다운로드 후 프로젝트 루트에 저장

### 5. Google Alerts RSS 설정
1. https://www.google.com/alerts 접속
2. 키워드 설정 (예: "5G 표준화", "ITU-R")
3. RSS 피드 생성
4. RSS URL 복사 후 설정:
   ```json
   "google_alerts_rss": [
     "https://www.google.com/alerts/feeds/..."
   ]
   ```

---

## 📁 프로젝트 구조

```
IRONAGE_AI_Analytics/
│
├── news_engine.py          # 핵심 엔진 (뉴스 수집, AI 분석)
├── trend_analyzer.py       # 트렌드 분석 모듈
├── main_app.py             # Streamlit 웹 대시보드
├── requirements.txt        # Python 패키지 목록
├── README.md               # 프로젝트 문서
├── CODE_ANALYSIS_REPORT.md # 코드 분석 리포트
│
├── data/
│   ├── config.json         # 설정 파일
│   ├── news.db             # SQLite 데이터베이스
│   ├── logs/               # 로그 파일
│   │   └── ironage_YYYYMMDD.log
│   └── reports/            # 리포트 메타데이터
│       ├── weekly_YYYYWW.json
│       └── monthly_YYYYMM.json
│
├── credentials.json        # Google API OAuth 인증
└── token.json              # Google API 액세스 토큰
```

---

## 📚 API 문서

### news_engine.py 주요 함수

#### `get_news_data() -> List[Dict]`
Google Alerts RSS와 Naver API에서 뉴스 수집

**반환값:**
```python
[
  {
    'title': '뉴스 제목',
    'link': 'https://...',
    'source': '출처',
    'published': datetime,
    'content': '본문 내용'
  },
  ...
]
```

#### `filter_news_by_ai(articles: List[Dict]) -> List[Dict]`
AI 기반 뉴스 품질 필터링 (상위 20% 선별)

#### `analyze_news_with_ai(article: Dict) -> Dict`
개별 뉴스 AI 분석

**반환값:**
```python
{
  'title': '뉴스 제목',
  'analysis': 'AI 분석 결과',
  'keywords': ['키워드1', '키워드2', ...],
  'quality_score': 0.85
}
```

#### `run_daily_collection()`
일일 자동 수집 워크플로우

#### `run_weekly_report() -> str`
주간 리포트 생성 (Google Docs URL 반환)

#### `run_monthly_report() -> str`
월간 리포트 생성 (Google Docs URL 반환)

### trend_analyzer.py 주요 함수

#### `generate_statistics_data(articles, period_days) -> Dict`
통계 데이터 생성

**반환값:**
```python
{
  'total_articles': 150,
  'avg_quality_score': 0.82,
  'source_distribution': {'TechCrunch': 30, ...},
  'top_keywords': [('5G', 45), ('AI', 38), ...],
  'daily_trend': {...}
}
```

#### `analyze_weekly_trends(articles) -> Dict`
주간 트렌드 AI 분석

**반환값:**
```python
{
  'key_issues': [
    {
      'title': '이슈 제목',
      'description': '상세 설명',
      'importance': 'high',
      'related_articles': [...]
    },
    ...
  ],
  'trends': [
    {
      'trend': '트렌드 설명',
      'impact': '산업 영향'
    },
    ...
  ],
  'statistics': {...}
}
```

---

## 🔍 문제 해결

### 자주 묻는 질문 (FAQ)

#### Q1: "OpenAI API 키가 설정되지 않았습니다" 오류
**A:** `data/config.json` 파일에 유효한 OpenAI API 키를 설정하세요.
```json
{
  "openai_api_key": "sk-proj-..."
}
```

#### Q2: Google Docs 생성 실패
**A:** 
1. `credentials.json` 파일이 프로젝트 루트에 있는지 확인
2. Google Docs API와 Drive API가 활성화되어 있는지 확인
3. `token.json` 삭제 후 재인증 시도

#### Q3: 이메일 발송 실패
**A:** 
1. Gmail 2단계 인증 활성화 확인
2. 앱 비밀번호 사용 (일반 비밀번호 불가)
3. 방화벽에서 SMTP 포트(587) 허용 확인

#### Q4: Naver API 호출 실패
**A:** 
1. API 키 유효성 확인
2. 일일 호출 한도 확인 (25,000회/일)
3. 검색 API가 활성화되어 있는지 확인

#### Q5: 데이터베이스 오류
**A:** 
```bash
# 데이터베이스 재생성
rm data/news.db
python news_engine.py test
```

### 로그 확인
```bash
# 최신 로그 파일 확인
cat data/logs/ironage_$(date +%Y%m%d).log

# 실시간 로그 모니터링
tail -f data/logs/ironage_$(date +%Y%m%d).log
```

---

## 🔧 고급 설정

### Windows 작업 스케줄러 설정

#### 1. 일일 수집 (매일 오전 9시)
```powershell
# 작업 스케줄러 열기
Win + R → taskschd.msc

# 새 작업 만들기
이름: IRONAGE 일일 수집
트리거: 매일 09:00
동작: python C:\path\to\news_engine.py daily
```

#### 2. 주간 리포트 (매주 월요일 오전 9시)
```powershell
이름: IRONAGE 주간 리포트
트리거: 매주 월요일 09:00
동작: python C:\path\to\news_engine.py weekly
```

#### 3. 월간 리포트 (매월 1일 오전 9시)
```powershell
이름: IRONAGE 월간 리포트
트리거: 매월 1일 09:00
동작: python C:\path\to\news_engine.py monthly
```

### 환경 변수 설정 (옵션)
```bash
# Linux/macOS
export OPENAI_API_KEY="sk-..."
export LOG_LEVEL="INFO"

# Windows PowerShell
$env:OPENAI_API_KEY="sk-..."
$env:LOG_LEVEL="INFO"
```

---

## 📊 통계 및 성능

### 처리 성능
- **뉴스 수집**: 100개 기사 약 30초
- **AI 분석**: 기사당 평균 3초
- **리포트 생성**: 150개 기사 기준 약 2분
- **데이터베이스 저장**: 기사당 0.01초

### 비용 추정 (OpenAI GPT-4)
- **일일 수집**: 약 $0.50 (20개 기사 분석)
- **주간 리포트**: 약 $3.00 (150개 기사 트렌드 분석)
- **월간 리포트**: 약 $10.00 (500개 기사 종합 분석)

**월간 총 비용**: 약 $50-60 (API 사용량에 따라 변동)

---

## 🤝 기여 및 지원

### 개발팀
- **소속**: 한국정보통신기술협회(TTA) 표준화본부
- **팀**: 이동통신표준팀
- **버전**: v4.2
- **최종 업데이트**: 2024-11-14

### 문의
- **기술 문의**: TTA 표준화본부
- **버그 리포트**: 이슈 트래커 등록
- **기능 제안**: 피드백 양식 제출

---

## 📝 라이선스

본 시스템은 한국정보통신기술협회(TTA) 내부용으로 개발되었습니다.

---

## 🎉 업데이트 히스토리

### v4.2 (2024-11-14)
- ✅ OpenAI SDK v1.12+ 완전 호환
- ✅ trend_analyzer.py 모듈 분리
- ✅ 주간/월간 리포트 AI 분석 강화
- ✅ HTML 이메일 디자인 개선

### v4.1 (2024-11-01)
- ✅ 멀티 AI 모델 지원 (Claude, Gemini, Perplexity)
- ✅ 자동 DB 마이그레이션
- ✅ 성능 모니터링 데코레이터
- ✅ Streamlit 대시보드 개선

### v4.0 (2024-10-15)
- ✅ Streamlit 웹 대시보드 추가
- ✅ Google Docs 자동 생성
- ✅ Gmail 이메일 발송
- ✅ SQLAlchemy 2.0 마이그레이션

---

## 🌟 주요 특징 요약

| 특징 | 설명 | 상태 |
|------|------|------|
| 자동 수집 | Google Alerts + Naver API | ✅ |
| AI 분석 | GPT-4 기반 핵심 이슈 도출 | ✅ |
| 트렌드 분석 | 주간/월간 통계 및 인사이트 | ✅ |
| 리포트 생성 | Google Docs 자동 생성 | ✅ |
| 이메일 발송 | HTML 형식 자동 발송 | ✅ |
| 웹 대시보드 | Streamlit 기반 GUI | ✅ |
| 자동화 | Windows 스케줄러 통합 | ✅ |
| 멀티 AI | 4개 AI 모델 지원 | ✅ |

---

**© 2024 한국정보통신기술협회(TTA). All rights reserved.**
