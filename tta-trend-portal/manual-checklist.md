# 수동 구축 체크리스트

## Google Sites

- [ ] 새 사이트 생성
- [ ] 사이트 이름 `TTA Intelligence Radar` 설정
- [ ] URL 후보 `trend` 확인
- [ ] 홈 페이지 생성
- [ ] Intelligence Radar 페이지 생성
- [ ] 이슈 맵 페이지 생성
- [ ] 보고서 보관함 페이지 생성
- [ ] 활용 가이드 페이지 생성
- [ ] 운영 현황 페이지 생성

## 권한

- [ ] Published site를 Restricted로 설정
- [ ] TTA 직원 또는 Google Group에 viewer 권한 부여
- [ ] 편집자는 운영 담당자로 제한
- [ ] 임베드된 Docs/Sheets 파일 권한 확인

## 연결

- [ ] Streamlit 대시보드 URL 연결
- [ ] `embeds/home-cards.html`의 대시보드/주간 보고서/Excel 링크 확인
- [ ] `embeds/streamlit-embed.html`의 Streamlit 내부 주소 확인
- [ ] `embeds/report-library.html`의 보고서/Excel URL 확인
- [ ] `embeds/quick-links.html`의 바로가기 URL 확인
- [ ] `templates/sites-link-inventory.csv`에 실제 링크 기록 확인
- [ ] `templates/report-links.csv`에 보고서 링크 기록 확인
- [ ] 주간 보고서 Google Docs 링크 연결
- [ ] 월간 보고서 Google Docs 링크 연결
- [ ] Excel 누적표 링크 연결
- [ ] 검색 가이드 문구 반영

## Streamlit 대시보드

- [ ] 내부 실행 PC/서버 결정
- [ ] `TTA Trend Portal\deploy\Run-Portal-Dashboard.cmd`로 실행 확인
- [ ] `http://localhost:8507/?embed=1` 로컬 확인
- [ ] `http://10.10.10.27:8507/?embed=1` 내부망 확인
- [ ] 내부 직원이 접근 가능한 URL 확보
- [ ] Google Sites iframe 또는 버튼 링크 연결

## 검증

- [ ] 일반 직원 계정으로 접속 가능
- [ ] 권한 없는 계정으로 접속 차단
- [ ] AI 검색 버튼 정상 이동
- [ ] AI 검색 iframe 정상 표시
- [ ] iframe이 차단될 경우 새 창 열기 버튼 정상 작동
- [ ] 보고서 링크 정상 열림
- [ ] 모바일 화면 확인

## 적용 순서

- [ ] 홈: `embeds/home-cards.html`
- [ ] 홈 하단: `embeds/quick-links.html`
- [ ] Intelligence Radar: `embeds/streamlit-embed.html`
- [ ] 이슈 맵: `embeds/streamlit-embed.html`
- [ ] 보고서 보관함: `embeds/report-library.html`
- [ ] 운영 현황: `embeds/status-summary.html`
- [ ] 각 하위 페이지 하단: `embeds/quick-links.html`
