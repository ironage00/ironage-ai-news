$ErrorActionPreference = "Stop"

$TaskName = "TTA ICT Trend Radar Dashboard"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Resolve-Path (Join-Path $ScriptRoot "Start-Portal-Dashboard-Hidden.ps1")

$Action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Principal $Principal `
  -Description "Starts TTA ICT Trend Radar Streamlit dashboard at logon." `
  -Force

Write-Host "Registered startup task: $TaskName"
