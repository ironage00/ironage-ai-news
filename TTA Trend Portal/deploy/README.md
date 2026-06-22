# 내부 배포 스크립트

이 폴더는 `tta_staff_search_dashboard`를 TTA 내부 PC 또는 서버에서 실행하기 위한 스크립트를 포함합니다.

## 수동 실행

```powershell
TTA Trend Portal\deploy\Run-Portal-Dashboard.cmd
```

접속:

```text
http://localhost:8507/?embed=1
```

## 숨김 실행

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Start-Portal-Dashboard-Hidden.ps1"
```

## 로그인 시 자동 실행 등록

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Register-Portal-Dashboard-Startup.ps1"
```

## 자동 실행 제거

```powershell
powershell -ExecutionPolicy Bypass -File "TTA Trend Portal\deploy\Unregister-Portal-Dashboard-Startup.ps1"
```

## 운영 Supabase 연결

운영 DB를 사용하려면 실행 환경에 아래 값을 설정합니다.

```powershell
$env:DATABASE_URL="postgresql://..."
$env:OPENAI_API_KEY="sk-..."
```

Google Sites에 넣는 URL은 내부 직원들이 접근 가능한 배포 주소여야 합니다.

```text
http://내부서버주소:8507/?embed=1
```

