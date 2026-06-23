# Google Sites 생성 절차

## 1. 새 사이트 생성

1. 브라우저에서 `https://sites.google.com` 접속
2. TTA Google 계정으로 로그인
3. `+` 또는 `Blank` 선택
4. 사이트 이름 입력:

```text
TTA Trend Portal
```

5. 사이트 문서 이름:

```text
TTA ICT Trend Radar
```

6. 상단 제목:

```text
TTA ICT Trend Radar
```

## 2. 권한 설정

게시 전 공유 설정에서 다음 원칙을 적용합니다.

```text
Published site: Restricted
Viewer: tta.or.kr 내부 사용자 또는 지정 Google Group
Editor: 운영 담당자만
```

권장 그룹:

```text
trend-viewers@tta.or.kr
trend-admins@tta.or.kr
```

그룹이 아직 없다면 1차 버전은 특정 사용자 이메일로 제한하고, 이후 Google Workspace 그룹으로 전환합니다.

## 3. 확정 URL

사이트 URL이 확정되었습니다.

```text
https://sites.google.com/tta.or.kr/trend-radar
```

## 4. 페이지 생성 순서

`site-map.md` 기준으로 다음 페이지를 만듭니다.

```text
홈
AI 검색
이슈 맵
보고서 보관함
활용 가이드
운영 현황
```

## 5. 임베드 방식

1차 권장 방식은 버튼 링크입니다.

```text
AI 검색 열기 → Streamlit 대시보드 새 창
```

iframe 임베드는 Streamlit 배포 URL에서 정상 동작하는지 확인한 후 적용합니다.
대시보드는 Google Sites용 `?embed=1` 모드를 지원하도록 구성합니다.

Google Sites에서 임베드:

```text
Insert → Embed → Embed code
```

그 후 `embeds/streamlit-embed.html` 내용을 붙여 넣습니다.
배포 주소는 이미 `http://10.10.10.27:8507?embed=1`로 설정되어 있습니다.

## 6. 게시 전 체크

- 사이트 접근 권한이 TTA 내부로 제한되었는가
- Google Docs/Sheets 파일 권한도 사이트 사용자에게 열려 있는가
- Streamlit 대시보드 URL이 외부 공개가 아니라 내부 직원 접근으로 제한되어 있는가
- API 키, DB URL, 서비스 계정 키가 Sites 본문이나 HTML에 포함되어 있지 않은가
- 보고서 링크가 최신 문서로 연결되는가
