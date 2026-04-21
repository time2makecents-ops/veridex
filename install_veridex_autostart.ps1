param(
  [string]$WorkingDirectory = "C:\Office-App"
)

$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$batchPath = Join-Path $startupDir "Veridex Backend.cmd"
$targetScript = Join-Path $WorkingDirectory "start_veridex_backend.ps1"

$content = "@echo off`r`nstart `"`" powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$targetScript`"`r`n"
Set-Content -Path $batchPath -Value $content -Encoding ASCII
Write-Host "Created startup launcher at $batchPath"
