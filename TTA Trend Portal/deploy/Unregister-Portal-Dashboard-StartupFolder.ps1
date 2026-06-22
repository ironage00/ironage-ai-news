$ErrorActionPreference = "Stop"

$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "TTA ICT Trend Radar Dashboard.lnk"

if (Test-Path -LiteralPath $ShortcutPath) {
  Remove-Item -LiteralPath $ShortcutPath -Force
  Write-Host "Removed startup shortcut: $ShortcutPath"
} else {
  Write-Host "Startup shortcut not found: $ShortcutPath"
}
