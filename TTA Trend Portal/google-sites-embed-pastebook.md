# Google Sites Embed Pastebook

이 문서는 `https://sites.google.com/tta.or.kr/trend-radar`에 붙여 넣을 임베드 블록 순서를 정리한 적용본입니다.

## 1. 홈

Google Sites 편집 화면에서 홈 페이지를 열고 아래 순서로 배치합니다.

1. 페이지 제목: `TTA Intelligence Radar`
2. `삽입 > 임베드 > 코드 삽입`
3. `TTA Trend Portal/embeds/home-cards.html` 전체 붙여 넣기
4. 바로 아래에 `TTA Trend Portal/embeds/quick-links.html` 붙여 넣기

권장 레이아웃:

- 사이트 기본 제목 영역은 짧게 유지
- 첫 화면에는 `home-cards.html`만 보이게 배치
- `quick-links.html`은 홈 하단 또는 모든 하위 페이지 공통 하단에 배치

## 2. AI 검색 / Intelligence Radar

1. 페이지 제목: `Intelligence Radar`
2. 상단 설명: `오늘의 레이더, 표준화 대응 보드, 보고서 보관함, 이슈 맵, 질문형 분석실을 실행합니다.`
3. `TTA Trend Portal/embeds/streamlit-embed.html` 붙여 넣기

참고:

- Google Sites가 HTTPS이고 Streamlit이 HTTP이면 iframe이 차단될 수 있습니다.
- 이 경우 같은 임베드 안의 `대시보드 새 창으로 열기` 버튼을 사용합니다.
- 장기적으로는 사내 HTTPS 리버스 프록시를 붙이는 것이 가장 좋습니다.

## 3. 보고서 보관함

1. 페이지 제목: `보고서 보관함`
2. `TTA Trend Portal/embeds/report-library.html` 붙여 넣기
3. 페이지 하단에 `TTA Trend Portal/embeds/quick-links.html` 붙여 넣기

## 4. 이슈 맵

1. 페이지 제목: `이슈 맵`
2. `TTA Trend Portal/embeds/streamlit-embed.html` 붙여 넣기
3. 페이지 설명에는 `기업, 기술, 국가, 표준 키워드의 관계를 확인합니다.` 사용

## 5. 운영 현황

1. 페이지 제목: `운영 현황`
2. `TTA Trend Portal/embeds/status-summary.html` 붙여 넣기
3. 하단에 `TTA Trend Portal/embeds/quick-links.html` 붙여 넣기

## 6. 활용 가이드

권장 문구:

```text
1. 홈에서 오늘 급등한 표준화 신호를 확인합니다.
2. Intelligence Radar에서 대응 보드와 질문형 분석실을 엽니다.
3. 관련 기사와 근거를 확인한 뒤 담당 단, 검토 상태, 조치 메모를 남깁니다.
4. 보고서 보관함에서 주간 보고서와 Excel 원자료를 공유합니다.
```

## 게시 전 확인

- 홈 첫 화면에서 `오늘의 ICT 표준화 신호를 한 화면에서 읽습니다` 문구가 보이는지 확인
- `대시보드 새 창으로 열기` 버튼이 `http://10.10.10.27:8507?embed=1`로 열리는지 확인
- 주간 보고서 Google Docs 링크가 열리는지 확인
- Excel 링크가 열리는지 확인
- 일반 직원 계정으로 게시 사이트가 보이는지 확인
- 외부 계정으로 차단되는지 확인
