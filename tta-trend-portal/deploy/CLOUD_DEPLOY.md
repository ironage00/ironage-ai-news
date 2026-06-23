# tta-radar Streamlit Cloud 운영 가이드

기존 Supabase DB(54,522건)가 연결되어 있으므로 **데이터 마이그레이션 없이** 바로 배포 가능합니다.

---

## 현재 상태 (완료)

| 항목 | 상태 |
|------|------|
| Supabase `news_articles` | 54,522건 ✅ |
| Supabase `article_embeddings` | 4,714건 ✅ |
| Supabase `report_artifacts` | 생성 완료 ✅ |
| Supabase `issue_actions` | 생성 완료 ✅ |
| `dashboard/db.py` Supabase 연결 | 테스트 완료 ✅ |

---

## 1단계 — GitHub push

```powershell
git add tta-trend-portal .github/workflows/daily-supabase-sync.yml
git commit -m "feat: Streamlit-only tta-radar operation"
git push origin codex/tta-trend-portal
```

또는 main 브랜치에 머지 후 push.

---

## 2단계 — Streamlit Community Cloud 배포 (5분)

1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인
2. `Create app` 클릭
3. 설정:

| 항목 | 값 |
|------|-----|
| Repository | `ironage00/ironage-ai-news` |
| Branch | `main` 또는 `codex/tta-trend-portal` |
| Main file path | `tta-trend-portal/dashboard/app.py` |
| App URL | `tta-radar` |

4. `Advanced settings > Secrets` 클릭 후 입력:

```toml
DATABASE_URL = "postgresql://postgres.tddarimbgdyxwlsnrifl:..."
OPENAI_API_KEY = "sk-..."
TTA_ALLOWED_EMAIL_DOMAIN = "tta.or.kr"
```

> `DATABASE_URL` 값은 프로젝트 루트 `.env` 파일에 있습니다.

5. `Deploy!` 클릭 → `https://tta-radar.streamlit.app` 접속 확인

---

## 4단계 — 일별 자동 동기화

새 기사가 SQLite에 수집된 후 Supabase에도 반영합니다.

```powershell
# 수동 실행 (증분만)
cd "D:\AI_project\2604_AI_news(anti)_1.5"
python "tta-trend-portal\scripts\daily_sync.py"

# 전체 재동기화
python "tta-trend-portal\scripts\daily_sync.py" --full
```

`.env`의 `DATABASE_URL`을 자동으로 읽습니다.

GitHub Actions로 자동화하려면 `.github/workflows/daily_sync.yml` 생성:

```yaml
name: Daily Supabase Sync
on:
  schedule:
    - cron: '30 0 * * *'   # 매일 09:30 KST
  workflow_dispatch:
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install psycopg2-binary
      - run: python "tta-trend-portal/scripts/daily_sync.py"
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

---

## 완료 후 체크리스트

- [ ] Streamlit Cloud URL 접속 → 기사 54,522건 로드 확인
- [ ] `https://tta-radar.streamlit.app/?embed=1` 접속 확인
- [ ] TTA 이메일 도메인 검증 확인
- [ ] 오늘의 레이더 탭 → 급등 키워드 표시 확인
- [ ] 질문형 분석실 → RAG 답변 확인
