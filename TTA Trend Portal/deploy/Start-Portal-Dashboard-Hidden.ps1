$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DashboardDir = Resolve-Path (Join-Path $ScriptRoot "..\..\tta_staff_search_dashboard")
$Port = if ($env:TTA_TREND_PORT) { $env:TTA_TREND_PORT } else { "8507" }

Start-Process `
  -FilePath "python" `
  -ArgumentList @("-m", "streamlit", "run", "app.py", "--server.port", $Port, "--server.headless", "true") `
  -WorkingDirectory $DashboardDir `
  -WindowStyle Hidden

Write-Host "TTA ICT Trend Radar dashboard started."
Write-Host "URL: http://localhost:$Port/?embed=1"

