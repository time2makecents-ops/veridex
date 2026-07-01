param(
  [string]$WorkingDirectory = "C:\Office-App"
)

$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$batchPath = Join-Path $startupDir "Veridex Backend.cmd"

if (Test-Path $batchPath) {
  Remove-Item $batchPath -Force
  Write-Host "Removed startup launcher at $batchPath"
} else {
  Write-Host "Startup launcher not found."
}
