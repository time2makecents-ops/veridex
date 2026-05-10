param(
  [string]$WorkingDirectory = "C:\Office-App\office_app\frontend",
  [string]$LogRoot = "C:\Office-App"
)

$nodePath = (Get-Command node -ErrorAction Stop).Source
$stdoutLog = Join-Path $LogRoot "frontend-https.out.log"
$stderrLog = Join-Path $LogRoot "frontend-https.err.log"

foreach ($logPath in @($stdoutLog, $stderrLog)) {
  if (Test-Path $logPath) {
    Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
  }
}

Start-Process `
  -FilePath $nodePath `
  -ArgumentList "server.cjs" `
  -WorkingDirectory $WorkingDirectory `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog | Out-Null
