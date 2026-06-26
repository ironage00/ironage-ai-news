# 내부 배포 스크립트

이 폴더는 `tta-trend-portal\dashboard`를 로컬 개발 또는 내부망 임시 실행에 사용하는 스크립트를 포함합니다. 운영은 `https://tta-radar.streamlit.app` 기준입니다.

## 수동 실행

```powershell
tta-trend-portal\deploy\Run-Portal-Dashboard.cmd
```

접속:

운영 URL: `https://tta-radar.streamlit.app`

로컬 개발 URL: `http://localhost:8507/?embed=1`

## 숨김 실행

```powershell
powershell -ExecutionPolicy Bypass -File "tta-trend-portal\deploy\Start-Portal-Dashboard-Hidden.ps1"
```

## 로그인 시 자동 실행 등록

```powershell
powershell -ExecutionPolicy Bypass -File "tta-trend-portal\deploy\Register-Portal-Dashboard-Startup.ps1"
```

등록 후 Windows 작업 스케줄러에 `TTA ICT Trend Radar Dashboard` 작업이 생성됩니다.

현재 사용자 권한에서 작업 스케줄러 등록이 막히면 시작프로그램 폴더 방식으로 등록합니다.

```powershell
powershell -ExecutionPolicy Bypass -File "tta-trend-portal\deploy\Register-Portal-Dashboard-StartupFolder.ps1"
```

## 자동 실행 제거

```powershell
powershell -ExecutionPolicy Bypass -File "tta-trend-portal\deploy\Unregister-Portal-Dashboard-Startup.ps1"
```

시작프로그램 폴더 방식 제거:

```powershell
powershell -ExecutionPolicy Bypass -File "tta-trend-portal\deploy\Unregister-Portal-Dashboard-StartupFolder.ps1"
```

## 운영 Supabase 연결

운영 DB를 사용하려면 실행 환경에 아래 값을 설정합니다.

```powershell
$env:DATABASE_URL="postgresql://..."
$env:OPENAI_API_KEY="sk-..."
```

## Supabase 공유 저장

여러 직원이 대응 상태를 공유하려면 아래 보조 테이블을 먼저 생성합니다.

```powershell
$env:DATABASE_URL="postgresql://..."
python "tta-trend-portal\scripts\setup_supabase_tables.py"
python "tta-trend-portal\scripts\sync_report_artifacts.py"
```
