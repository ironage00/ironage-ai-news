# 내부 배포 스크립트

이 폴더는 `TTA Trend Portal\dashboard`를 TTA 내부 PC 또는 서버에서 실행하기 위한 스크립트를 포함합니다.

## 수동 실행

```powershell
TTA Trend Portal\deploy\Run-Portal-Dashboard.cmd
```

접속:

```text
http://localhost:8507/?embed=1
http://10.10.10.27:8507/?embed=1
```

## 숨김 실행

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Start-Portal-Dashboard-Hidden.ps1"
```

## 로그인 시 자동 실행 등록

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Register-Portal-Dashboard-Startup.ps1"
```

등록 후 Windows 작업 스케줄러에 `TTA ICT Trend Radar Dashboard` 작업이 생성됩니다.

현재 사용자 권한에서 작업 스케줄러 등록이 막히면 시작프로그램 폴더 방식으로 등록합니다.

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Register-Portal-Dashboard-StartupFolder.ps1"
```

## 자동 실행 제거

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Unregister-Portal-Dashboard-Startup.ps1"
```

시작프로그램 폴더 방식 제거:

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Unregister-Portal-Dashboard-StartupFolder.ps1"
```

## 운영 Supabase 연결

운영 DB를 사용하려면 실행 환경에 아래 값을 설정합니다.

```powershell
$env:DATABASE_URL="postgresql://..."
$env:OPENAI_API_KEY="sk-..."
```

Google Sites에 넣는 URL은 내부 직원들이 접근 가능한 배포 주소여야 합니다.

```text
http://10.10.10.27:8507/?embed=1
```

## Supabase 공유 저장

여러 직원이 대응 상태를 공유하려면 아래 보조 테이블을 먼저 생성합니다.

```powershell
$env:DATABASE_URL="postgresql://..."
python "TTA Trend Portal\scripts\setup_supabase_tables.py"
python "TTA Trend Portal\scripts\sync_report_artifacts.py"
```
