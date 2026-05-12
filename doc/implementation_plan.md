# IRONAGE AI Analytics System v4.2 고도화 계획

본 계획은 기존 뉴스 분석 시스템을 프리미엄급 대시보드 UI로 개편하고, AI 분석 항목을 고도화하여 단순 정보 전달을 넘어 표준화 대응을 위한 전략적 인사이트를 제공하는 것을 목표로 합니다.

## User Review Required

> [!IMPORTANT]
> **AI 분석 항목 확장**: 다음과 같은 새로운 메트릭이 추가됩니다. AI 모델의 프롬프트를 대폭 수정해야 하므로 분석 시간과 비용이 약간 증가할 수 있습니다.
> - **영향도(Impact Level)**: 뉴스 내용의 긴급성 및 중요도 (Critical, High, Medium, Low)
> - **TTA 조치 사항(TTA Action Item)**: 협회 차원에서 즉시 대응이 필요한 사항
> - **표준화 격차(Standardization Gap)**: 현재 표준화 현황과 기사 내용 간의 차이 분석

> [!NOTE]
> **디자인 테마**: 다크 모드 기반의 글래스모피즘(Glassmorphism)과 애니메이션 효과가 적용된 현대적인 UI로 전환됩니다.

## Proposed Changes

### 1. 전역 스타일 및 디자인 고도화 (main_app.py / CSS)
- [x] 전역 CSS 적용 (카드 효과, 호버 효과, 애니메이션)
- [x] 뉴스 태그 컬러링 시스템 (기술, 정책, 기업, 표준 카테고리별 색상 지정)
- [x] 사이드바 및 레이아웃 배치 최적화 (풀스크린 활용도 제고)

---

### 2. AI 분석 엔진 고도화 (news_engine.py / Prompt)
- [x] **분석 프롬프트 수정**: `impact_level`, `tta_action_item`, `standardization_gap` 항목을 명시적으로 요구하도록 프롬프트 업데이트.
- [x] **JSON 파싱 로직 개선**: 새로 추가된 항목들을 포함한 JSON 블록을 추출할 수 있도록 `_extract_keyword_json` 및 관련 로직 수정.
- [x] **데이터 처리**: 선별된 뉴스 목록에 위 항목들을 매핑하여 리포트 생성기로 전달. (`_get_impact_info` 헬퍼, `IMPACT_LEVEL_*` 상수 추가)

---

### 3. 리포트 연동 (news_engine.py / Google Docs & Gmail)
- [x] **Google Docs 리포트**: 영향도 아이콘 및 TTA 조치 사항 섹션을 문서 상단에 배치하여 시각적 가독성 향상.
- [x] **Gmail 리포트**: 영향도별로 뉴스 리스트를 분류(Critical/High 우선 노출). 영향도 배지, TTA 섹션, 표준화 격차 섹션 추가.
- [x] **Excel 리포트**: 주간 엑셀에 `영향도`, `TTA 조치 사항`, `표준화 격차` 컬럼 추가.

---

### 4. 대시보드 시각화 (main_app.py)
- [x] **영향도 차트 추가**: 수집된 뉴스의 영향도 분포를 보여주는 도넛 차트.
- [x] **주요 조치 사항 요약**: Critical 등급의 뉴스에서 추출된 TTA 조치 사항을 대시보드 상단에 배치.

## Verification Plan

### Automated Tests
- `news_engine.py`의 테스트 모드(스크랩 없이 기존 데이터 활용)를 사용하여 AI 분석 및 리포트 생성 로직 검증.
- 새롭게 정의된 JSON 구조가 올바르게 파싱되는지 유닛 테스트 실행.

### Manual Verification
- Streamlit 대시보드 실행 후 디자인 요소(호버, 애니메이션) 작동 확인.
- 생성된 Google Doc 리포트의 스타일 및 내용 정합성 확인.
- 테스트 메일 발송 후 모바일 및 데스크탑 뷰 확인.
