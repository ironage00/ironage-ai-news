# 보고서 링크 관리표

Google Sites 보고서 보관함에 넣을 Google Docs/Excel 링크를 관리하는 템플릿입니다.

## 관리 원칙

```text
Supabase = 데이터 원장
Google Docs = 보고서 열람/공유
Google Excel/Sheets = 기사 목록 검토/감사
Google Sites = 직원용 입구
```

## CSV 컬럼

| 컬럼 | 설명 |
|---|---|
| `report_type` | weekly, monthly, excel, auto-intel |
| `title` | 보고서 제목 |
| `period_start` | 기간 시작일 |
| `period_end` | 기간 종료일 |
| `google_doc_url` | Google Docs 링크 |
| `excel_file_url` | Excel 또는 Sheets 링크 |
| `owner` | 담당 조직 |
| `visibility` | tta_internal, admin_only 등 |
| `status` | draft, published, archived |
| `notes` | 비고 |

## 다음 자동화 단계

이 CSV는 이후 Supabase 테이블로 옮길 수 있습니다.

```sql
CREATE TABLE IF NOT EXISTS report_artifacts (
  id BIGSERIAL PRIMARY KEY,
  report_type TEXT NOT NULL,
  title TEXT NOT NULL,
  period_start DATE,
  period_end DATE,
  google_doc_url TEXT,
  excel_file_url TEXT,
  owner TEXT,
  visibility TEXT DEFAULT 'tta_internal',
  status TEXT DEFAULT 'published',
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

