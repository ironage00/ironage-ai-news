# TODOS.md

항목은 언제 추가되었는지와 어느 CEO 계획/스프린트에서 연기되었는지 추적합니다.

---

## Deferred from CEO Plan 2026-05-11 (Streamlit Cloud 배포)

- [ ] **D3: Google OAuth 90일 만료 경고 배너** — `token.json`이 마지막 수정일 기준 80일 경과 시 대시보드 상단에 주황색 배너 표시. 배포 후 실제 80일이 가까워지면 추가.
- [ ] **schedule_daily 컬럼**: `user_settings`에 `schedule_daily BOOLEAN` 추가 + `daily-collection.yml`에서 사용자별 수집 스킵 로직. 이번 스프린트에서는 YAGNI로 제외.
- [ ] **Approach B 업그레이드**: 사용자 5명 이상, 또는 팀별 키워드가 완전히 달라 공유 DB가 의미 없어질 때 → 팀별 독립 DB 격리.
- [ ] **D3 자동화 대안**: GitHub Actions weekly cron에서 `token.json` 생성일 확인 후 만료 임박 시 이메일 알림 발송 (`check_token_expiry.yml`).
- [x] **streamlit-authenticator → Google OAuth 전환**: 2026-05-12 완료. TTA @tta.or.kr Workspace 계정으로 `st.login()` 방식 채택. `auth_config.yaml` 불필요.
- [ ] **DESIGN.md 생성** — 현재 앱 디자인 시스템(Pretendard, TTA Blue #005aab, TTA Gold #c5a059, glassmorphism 카드, 다크 사이드바 #0f172a)을 `doc/DESIGN.md`로 문서화. 이번 스프린트는 기존 CSS 패턴 재사용으로 충분하나, 컴포넌트 추가 시 기준 문서 필요.

## Deferred from CEO Plan 2026-05-06 (Bug Fix + Phase 5-7)

- [ ] **자동 모델 폴백 순서**: AI 모델 실패 시 자동으로 다음 모델 시도하는 우선순위 체인. 현재는 수동 선택.
- [ ] **분석 결과 인라인 편집 UI**: 뉴스 피드에서 AI 분석 결과를 직접 편집하는 UI.
