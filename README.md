# 🚀 IRONAGE AI Analytics System v5.0

**ICT/통신 업계 뉴스 수집 및 자율 인텔리전스 분석 시스템**

한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀을 위한 자동화된 뉴스 수집, AI 분석, 지식 그래프 시각화 및 자율 리포트 생성 시스템입니다.

---

## 📋 목차

1. [시스템 개요](#-시스템-개요)
2. [주요 기능 (New v5.0)](#-주요-기능-new-v50)
3. [기술 스택](#-기술-스택)
4. [설치 및 설정](#-설치-및-설정)
5. [프로젝트 구조](#-프로젝트-구조)
6. [사용 방법](#-사용-방법)
7. [결과물 관리 규정](#-결과물-관리-규정)
8. [업데이트 히스토리](#-업데이트-히스토리)

---

## 🎯 시스템 개요

### 목적
ICT/통신 분야의 최신 뉴스를 자동으로 수집하고, RAG(Retrieval-Augmented Generation)와 지식 그래프를 활용하여 핵심 이슈와 급등 트렌드를 자율적으로 분석하여 주간/월간 리포트를 생성하는 차세대 인텔리전스 시스템입니다.

### 핵심 가치
- **자율성**: Phase 4 '자율 인텔리전스' 모듈을 통한 상태 기계(State Machine) 기반 리포트 자동 생성
- **통찰력**: 단순 요약을 넘어 엔티티 급등 감지 및 세부 시사점 도출
- **확장성**: Supabase(PostgreSQL) 연동을 통한 클라우드 데이터 관리 및 GitHub Actions 자동화

---

## ✨ 주요 기능 (New v5.0)

### 1. 🧠 자율 인텔리전스 리포트 (Phase 4)
- **State Machine 파이프라인**: 데이터 로드 → 급등 감지 → RAG 검색 → 내러티브 생성 → 보고서 작성 → 발송의 전 과정을 자율적으로 수행
- **급등 엔티티 감지**: 이전 기간 대비 언급 횟수가 급증한 기업, 기술, 국가를 자동으로 선별

### 2. 🔍 RAG 기반 뉴스 검색 및 분석
- **의미론적 검색**: OpenAI 임베딩(`text-embedding-3-small`)을 활용하여 질문의 맥락에 맞는 관련 기사 추출
- **하이브리드 검색**: 코사인 유사도 검색과 키워드 검색을 결합하여 분석 품질 및 커버리지 극대화

### 3. 🕸️ 지식 그래프 (Phase 3)
- **엔티티 연관 관계 시각화**: 기사 내 등장하는 기업/기술/국가 간의 공출현(Co-occurrence) 관계를 네트워크 그래프로 표시
- **인터랙티브 대시보드**: Pyvis를 활용한 동적 그래프 조작 및 상세 정보 확인

### 4. 🗄️ 클라우드 데이터베이스 전환
- **Supabase (PostgreSQL)**: 로컬 SQLite를 넘어 클라우드 기반 관리 체계로 전환 (SQLAlchemy 2.0 ORM 사용)
- **하이브리드 스토리지**: GitHub Actions 운영 시 SQLite를 로컬 캐시로 활용하여 성능과 안정성 확보

### 5. 📧 지능형 리포트 발송
- **Google Docs & OAuth2**: 더 안정적인 OAuth2 인증 기반 리포트 생성 (`token.json`)
- **멀티 모델 지원**: GPT-4o, Claude 3.5, Gemini 1.5, Perplexity API를 상황에 맞게 교체 사용

---

## 🛠️ 기술 스택

- **Language**: Python 3.11+
- **Database**: Supabase (PostgreSQL), SQLite
- **AI/ML**: OpenAI (GPT-4o, Embeddings), Anthropic Claude, Google Gemini
- **Frontend**: Streamlit, Plotly, Pyvis
- **Infrastructure**: GitHub Actions, Google API (Docs/Drive/OAuth2)

---

## 📦 설치 및 설정

### 1. 의존성 설치
```bash
# uv 사용 시 (권장)
uv pip install -r requirements.txt

# pip 사용 시
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (`.env` 또는 `streamlit_secrets.toml`)
```ini
DATABASE_URL=postgresql://...         # Supabase 연결 문자열
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
CLAUDE_API_KEY=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
GMAIL_SENDER=...
GMAIL_PASSWORD=...                    # 앱 비밀번호
GOOGLE_TOKEN_JSON='{...}'             # OAuth2 토큰 JSON (Base64 또는 문자열)
```

---

## 📁 프로젝트 구조

```
IRONAGE_AI_Analytics/
├── .github/workflows/       # GitHub Actions 자동화 스크립트 (Daily/Weekly)
├── results/                 # [중요] 최종 분석 보고서 저장소
├── news_engine.py           # 핵심 코어 (수집, 분석, 데이터 엔진)
├── auto_intel_report.py     # 자율 인텔리전스 오케스트레이터 (Phase 4)
├── rag_search.py            # RAG 및 벡터 검색 모듈
├── knowledge_graph.py       # 지식 그래프 및 급등 감지 모듈
├── trend_analyzer.py        # 트렌드 분석 및 보고서 양식 생성
├── main_app.py              # Streamlit 통합 웹 대시보드
├── requirements.txt         # 종속성 목록
├── token.json               # Google API OAuth2 토큰
└── data/                    # 로컬 데이터 및 로그 폴더
```

---

## 🚀 사용 방법

### 웹 대시보드 실행
```bash
streamlit run main_app.py
```

### 자율 인텔리전스 리포트 실행 (CLI)
```bash
# 주간 리포트 생성 및 전송
python auto_intel_report.py

# 또는 news_engine.py를 통한 수집
python news_engine.py daily
```

---

## 📊 결과물 관리 규정

모든 분석 결과 및 보고서는 다음의 규칙을 따릅니다:

1. **저장 위치**: `results/` 폴더 내에 생성
2. **파일명 형식**: `[YYMMDD]_[보고서종류].md`
   - 예: `260522_주간트렌드분석.md`
   - 예: `260601_월간인텔리전스.md`

---

## 🎉 업데이트 히스토리

### v5.0 (2026-05-22)
- ✅ **Phase 4 완료**: 자율 인텔리전스 리포트 오케스트레이터 도입
- ✅ **RAG 도입**: 뉴스 데이터 기반 벡터 검색 및 답변 생성 최적화
- ✅ **DB 전환**: SQLite 위주에서 Supabase (PostgreSQL) 클라우드 연동으로 업그레이드
- ✅ **자동화**: GitHub Actions 기반 24/7 무중단 뉴스 수집 파이프라인 구축

### v4.2 (2024-11-14)
- ✅ OpenAI SDK v1.12+ 완전 호환
- ✅ trend_analyzer.py 모듈 분리 및 HTML 이메일 개선

---

**© 2026 한국정보통신기술협회(TTA). All rights reserved.**
