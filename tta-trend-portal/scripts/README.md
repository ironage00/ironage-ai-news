# TTA Trend Portal Scripts

이 폴더는 기존 운영 코드와 분리된 포털 관리 스크립트입니다.

## Supabase 보조 테이블 생성

```powershell
$env:DATABASE_URL="postgresql://..."
python "TTA Trend Portal\scripts\setup_supabase_tables.py"
```

## 보고서 산출물 CSV를 Supabase로 동기화

```powershell
$env:DATABASE_URL="postgresql://..."
python "TTA Trend Portal\scripts\sync_report_artifacts.py"
```

`DATABASE_URL`이 없거나 Supabase 테이블이 아직 없으면 대시보드는 계속
`TTA Trend Portal\data\report_artifacts.csv`와
`TTA Trend Portal\data\issue_actions.csv`를 사용합니다.
