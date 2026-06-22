# TTA Intelligence Radar v0.1

TTA 직원이 기존 뉴스 원장(Supabase/PostgreSQL 또는 로컬 SQLite)을 검색하고 RAG/GraphRAG 관점으로 활용하기 위한 독립 레이더 대시보드입니다.

이 폴더는 기존 `news_engine.py`, `main_app.py`, `rag_search.py`, `knowledge_graph.py`를 수정하거나 import하지 않습니다.

## 기능

- 오늘의 레이더:
  - 급등 키워드
  - 신규 등장 엔티티
  - 단별 추천 이슈
- 표준화 대응 보드:
  - 이슈 후보
  - 영향도/긴급도
  - 관련 기사
  - 권장 조치
  - 담당 단, 검토 상태, 조치 메모 저장
- 보고서 보관함:
  - Google Docs 주간/월간 보고서
  - Google Sheets/Excel 누적 분석 파일
  - 향후 DB `report_artifacts` 테이블 자동 연동
- 이슈 맵:
  - 기업, 기술, 국가, 표준 키워드 관계
  - 중심 엔티티
  - 주요 클러스터 후보
- 질문형 분석실:
  - 기존 RAG/키워드 검색
  - 근거 기사
  - 답변 생성
- 기사 조건 검색: 날짜, 단, 출처, 분석 여부, 키워드
- Google Sites 임베드용 포털 화면: `?embed=1`
- 요약 지표 카드: 전체 기사, 분석 완료, 임베딩, 임베딩 누락
- 빠른 질문 버튼: 자주 쓰는 표준화 질의 즉시 실행
- 자연어 검색:
  - Supabase + pgvector + OpenAI API가 있으면 벡터 RAG 검색
- 없으면 키워드 기반 검색으로 fallback
- 근거 기사 기반 답변 초안 생성
- 엔티티 관계 탐색: 기업, 기술, 국가, 표준 키워드 공출현 그래프
- GraphRAG식 클러스터 요약: 관계망 중심 엔티티와 관련 기사 묶음 확인
- 보고서/엑셀 산출물 링크를 `data/report_artifacts.csv` 또는 DB `report_artifacts` 테이블에서 표시

## v0.1 점수 기준

- 급등 키워드: 최근 기간 등장 빈도, 기준기간 대비 증가, 빈도 비율을 조합합니다.
- 신규 엔티티: 최근 기간에는 있으나 기준기간에는 없던 기업/기술/국가/표준 키워드를 표시합니다.
- 영향도: 표준화 키워드, 품질점수, 엔티티 수, 기술/정책/보안 신호를 반영합니다.
- 긴급도: 최신성, 발표/상용화/규제/경쟁/투자 등 대응 필요 신호를 반영합니다.

점수는 1차 휴리스틱입니다. 운영 데이터가 쌓이면 실제 대응 이력 기반으로 가중치를 조정하는 구조로 발전시키는 것이 좋습니다.

## 실행

```powershell
cd "TTA Trend Portal\dashboard"
python -m pip install -r requirements.txt
streamlit run app.py
```

또는:

```powershell
"TTA Trend Portal\deploy\Run-Portal-Dashboard.cmd"
```

Google Sites 임베드 테스트:

```text
http://localhost:8507?embed=1
```

실제 Google Sites 게시에는 로컬 주소가 아니라 배포된 Streamlit URL을 사용해야 합니다.

## 환경 변수

운영 Supabase를 읽으려면:

```powershell
$env:DATABASE_URL="postgresql://..."
$env:OPENAI_API_KEY="sk-..."
```

`DATABASE_URL`이 없으면 기본적으로 저장소의 `data/news.db`를 읽습니다.

## 로컬 포털 데이터

- `TTA Trend Portal\data\report_artifacts.csv`: Google Docs/Excel 산출물 목록
- `TTA Trend Portal\data\issue_actions.csv`: 표준화 대응 보드의 담당 단, 검토 상태, 조치 메모

Supabase에 `report_artifacts`, `issue_actions` 테이블이 있으면 대시보드는 DB를 우선 사용합니다.
테이블이 없거나 접속할 수 없으면 위 CSV 파일로 fallback합니다.

## 권한 정책

1차 버전은 TTA 직원 내부 사용을 전제로 합니다.

- `TTA_ALLOWED_EMAIL_DOMAIN`: 기본값 `tta.or.kr`
- 앱 화면에서 이메일을 입력하고 도메인을 확인합니다.
- 실제 운영 배포 시에는 Google Workspace OAuth 또는 사내 SSO 연동을 권장합니다.

## EXE 패키징

Streamlit 앱은 완전한 단일 exe보다 “런처 exe” 방식이 안정적입니다.

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --name TTA-Staff-Search launcher.py
```

생성된 exe는 내부적으로 `streamlit run app.py`를 실행합니다.
