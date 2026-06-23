# 단계별 추진 계획

## Phase 1. Google Sites 포털 구성

목표: 직원이 접근할 공식 입구를 먼저 만듭니다.

작업:

```text
1. Google Sites 새 사이트 생성
2. 홈, AI 검색, 이슈 맵, 보고서 보관함, 활용 가이드, 운영 현황 페이지 구성
3. Google Docs/Excel 링크 연결
4. Streamlit 대시보드 버튼 링크 연결
5. 접근 권한을 TTA 내부로 제한
```

완료 기준:

```text
TTA 직원 계정으로 Sites 접속 가능
AI 검색 대시보드로 이동 가능
최신 보고서/Excel에 접근 가능
홈 카드, 보고서 카드, 운영 현황 카드 삽입 완료
```

## Phase 2. Streamlit 대시보드 포털형 개편

목표: 현재 `tta_staff_search_dashboard`를 Google Sites에 어울리는 검색 엔진으로 다듬습니다.

작업:

```text
1. 첫 화면을 검색창 중심에서 오늘의 레이더 중심으로 개편
2. 기본 검색 기간, 필터, 결과 없음 안내 개선
3. 단별 추천 이슈 표시
4. Sites 임베드용 레이아웃 옵션 추가
5. URL 파라미터 ?embed=1로 포털형 화면 사용
6. 내부 배포 스크립트로 상시 실행 환경 구성
```

완료 기준:

```text
직원이 별도 설명 없이 검색과 이슈 확인 가능
Sites에서 iframe 또는 버튼 링크로 안정적으로 사용 가능
내부 PC/서버 재부팅 후 대시보드 자동 실행 가능
```

## Phase 3. 보고서 메타데이터 연결

목표: Google Docs/Excel 산출물을 DB에서 추적합니다.

추가 테이블:

```text
report_artifacts
- id
- report_type
- title
- period_start
- period_end
- google_doc_url
- excel_file_url
- source_article_count
- generated_at
- status
```

완료 기준:

```text
보고서 보관함에서 기간별 문서와 Excel을 자동 표시
보고서와 원본 기사 추적 가능
```

## Phase 4. Intelligence Radar 고도화

목표: 검색 도구를 표준화 이슈 탐지 시스템으로 확장합니다.

추가 모듈:

```text
radar.py
scoring.py
issue_board.py
report_export.py
```

추가 테이블:

```text
issue_candidates
entity_snapshots
article_entities
entity_edges
```

완료 기준:

```text
급등 이슈 자동 탐지
표준화 영향도 점수 계산
단별 대응 후보 표시
GraphRAG식 관계 요약 제공
```

## Phase 5. 운영 배포

목표: 직원이 안정적으로 사용할 수 있도록 배포 방식을 확정합니다.

선택지:

```text
1. Streamlit 내부 서버 배포
2. Streamlit Cloud/유사 플랫폼 배포
3. FastAPI + Next.js로 확장
```

권장:

```text
초기: Google Sites + Streamlit 링크
안정화: Google Sites + Streamlit iframe
확장: FastAPI API 서버 + 전용 웹 포털
```
