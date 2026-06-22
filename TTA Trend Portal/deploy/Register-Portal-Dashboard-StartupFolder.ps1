$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Resolve-Path (Join-Path $ScriptRoot "Start-Portal-Dashboard-Hidden.ps1")
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TTA ICT Trend Radar Dashboard.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$Shortcut.WorkingDirectory = $ScriptRoot
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Starts TTA ICT Trend Radar Streamlit dashboard at Windows logon."
$Shortcut.Save()

Write-Host "Registered startup shortcut: $ShortcutPath"
