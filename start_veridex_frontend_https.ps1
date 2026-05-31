param(
  [string]$WorkingDirectory = "C:\Office-App\office_app\frontend",
  [string]$LogRoot = "C:\Office-App"
)

$frontendPidFile = Join-Path $LogRoot ".veridex-frontend-cmd.pid"
$proc = Start-Process `
  -FilePath "cmd.exe" `
  -ArgumentList "/k", 'title Veridex Frontend && node server.cjs' `
  -WorkingDirectory $WorkingDirectory `
  -PassThru
if ($proc -and $proc.Id) {
  Set-Content -Path $frontendPidFile -Value "$($proc.Id)" -Encoding ascii
}
