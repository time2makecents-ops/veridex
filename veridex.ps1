param(
  [ValidateSet("start", "stop", "restart", "status")]
  [string]$Action = "start"
  ,
  [switch]$GroqFallbackTest
)

$backendPort = 8078
$frontendPort = 3078
$root = "C:\Office-App"
$backendCommand = Join-Path $root "run_server.cmd"
$frontendDir = Join-Path $root "office_app\frontend"
$frontendStdoutLog = Join-Path $root "frontend-https.out.log"
$frontendStderrLog = Join-Path $root "frontend-https.err.log"
$smokeScript = Join-Path $root "office_app\smoke_test.ps1"
$backendPidFile = Join-Path $root ".veridex-backend-cmd.pid"
$frontendPidFile = Join-Path $root ".veridex-frontend-cmd.pid"

function Get-ListeningPids {
  param([int[]]$Ports)
  $pids = @()
  foreach ($port in $Ports) {
    try {
      $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop
      $pids += $conns.OwningProcess
    } catch {
      $lines = netstat -ano | Select-String ":$port\s"
      foreach ($line in $lines) {
        $parts = ($line.ToString() -split '\s+') | Where-Object { $_ }
        if ($parts.Count -gt 0) {
          $candidate = $parts[-1]
          if ($candidate -match '^\d+$') {
            $pids += [int]$candidate
          }
        }
      }
    }
  }
  $pids | Sort-Object -Unique
}

function Stop-Veridex {
  foreach ($pidFile in @($backendPidFile, $frontendPidFile)) {
    if (Test-Path $pidFile) {
      try {
        $savedPid = [int](Get-Content -Path $pidFile -ErrorAction Stop | Select-Object -First 1)
        if ($savedPid -gt 0) {
          taskkill /PID $savedPid /T /F | Out-Null
          Write-Host "Stopped saved PID $savedPid"
        }
      } catch {}
      try { Remove-Item -Path $pidFile -Force -ErrorAction Stop } catch {}
    }
  }
  $pids = Get-ListeningPids -Ports @($backendPort, $frontendPort)
  if (-not $pids) {
    Write-Host "Veridex is not listening on $backendPort or $frontendPort."
  }
  foreach ($processId in $pids) {
    if ($processId -and $processId -ne 0) {
      try {
        # Kill process tree so wrapper cmd windows close too.
        taskkill /PID $processId /T /F | Out-Null
        Write-Host "Stopped PID $processId"
      } catch {
        Write-Host "Could not stop PID ${processId}: $($_.Exception.Message)"
      }
    }
  }
  # Also close lingering Veridex cmd windows by title and by command line.
  $cmdCandidates = @()
  $cmdByTitle = Get-Process -Name "cmd" -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "Veridex Frontend*" -or $_.MainWindowTitle -like "Veridex Backend*"
  }
  if ($cmdByTitle) { $cmdCandidates += $cmdByTitle.Id }
  try {
    $cmdByCommand = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction Stop | Where-Object {
      $_.CommandLine -and (
        $_.CommandLine -like "*title Veridex Frontend*" -or
        $_.CommandLine -like "*title Veridex Backend*" -or
        $_.CommandLine -like "*node server.cjs*" -or
        $_.CommandLine -like "*run_server.cmd*"
      )
    }
    if ($cmdByCommand) { $cmdCandidates += ($cmdByCommand | ForEach-Object { [int]$_.ProcessId }) }
  } catch {}
  foreach ($cmdPid in ($cmdCandidates | Sort-Object -Unique)) {
    try {
      taskkill /PID $cmdPid /T /F | Out-Null
      Write-Host "Closed Veridex cmd PID $cmdPid"
    } catch {}
  }
}

function Wait-Port {
  param(
    [int]$Port,
    [int]$TimeoutSeconds = 20
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      if ((Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet)) {
        return $true
      }
    } catch {}
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Test-FrontendReady {
  try {
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    $nodeScript = @"
const https = require('https');
const req = https.get('https://127.0.0.1:3078', { rejectUnauthorized: false }, (res) => {
  console.log(String(res.statusCode || 0));
  res.resume();
});
req.on('error', () => {
  console.log('0');
  process.exitCode = 1;
});
req.setTimeout(3000, () => {
  console.log('0');
  req.destroy();
  process.exitCode = 1;
});
"@
    $status = ($nodeScript | & $nodePath -).Trim()
    return ($status -match '^\d+$' -and [int]$status -ge 200 -and [int]$status -lt 400)
  } catch {
    return $false
  }
}

function Wait-FrontendReady {
  param([int]$TimeoutSeconds = 30)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-FrontendReady) {
      return $true
    }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Show-StartupHelp {
  Write-Host ""
  Write-Host "Recommended start command:" -ForegroundColor Yellow
  Write-Host "  C:\Office-App\veridex.cmd"
  Write-Host ""
  Write-Host "Manual backend command:" -ForegroundColor Yellow
  Write-Host "  cd /d C:\Office-App"
  Write-Host "  run_server.cmd"
  Write-Host ""
  Write-Host "Manual frontend command:" -ForegroundColor Yellow
  Write-Host "  cd /d C:\Office-App\office_app\frontend"
  Write-Host "  node server.cjs"
  Write-Host ""
  Write-Host "Validation command:" -ForegroundColor Yellow
  Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Office-App\office_app\smoke_test.ps1"
}

function Start-Backend {
  if ($GroqFallbackTest) {
    $env:GEMINI_API_KEY = "invalid-gemini-key-for-groq-fallback-test"
  }
  $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "title Veridex Backend && `"$backendCommand`"" -WorkingDirectory $root -PassThru
  if ($proc -and $proc.Id) {
    Set-Content -Path $backendPidFile -Value "$($proc.Id)" -Encoding ascii
  }
}

function Start-Frontend {
  $proc = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/k", 'title Veridex Frontend && node server.cjs' `
    -WorkingDirectory $frontendDir `
    -PassThru
  if ($proc -and $proc.Id) {
    Set-Content -Path $frontendPidFile -Value "$($proc.Id)" -Encoding ascii
  }
}

switch ($Action) {
  "stop" {
    Stop-Veridex
  }
  "status" {
    $backendUp = Test-NetConnection 127.0.0.1 -Port $backendPort -InformationLevel Quiet
    $frontendUp = Test-FrontendReady
    Write-Host "Backend ($backendPort): $backendUp"
    Write-Host "Frontend ($frontendPort): $frontendUp"
    if ($backendUp -and $frontendUp -and (Test-Path $smokeScript)) {
      Write-Host "Run smoke test:" -ForegroundColor Green
      Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File $smokeScript"
    } elseif (-not $backendUp -or -not $frontendUp) {
      Show-StartupHelp
    }
  }
  "restart" {
    Stop-Veridex
    Start-Sleep -Seconds 2
    Start-Backend
    if (-not (Wait-Port -Port $backendPort -TimeoutSeconds 30)) {
      Show-StartupHelp
      throw "Backend failed to start on port $backendPort."
    }
    Start-Frontend
    if (-not (Wait-FrontendReady -TimeoutSeconds 30)) {
      Show-StartupHelp
      throw "Frontend failed to start on port $frontendPort. Check $frontendStdoutLog and $frontendStderrLog."
    }
    Write-Host "Veridex restarted."
    if (Test-Path $smokeScript) {
      Write-Host "Run smoke test:" -ForegroundColor Green
      Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File $smokeScript"
    }
  }
  default {
    $backendUp = Test-NetConnection 127.0.0.1 -Port $backendPort -InformationLevel Quiet
    $frontendUp = Test-FrontendReady
    if ($backendUp -and $frontendUp) {
      Write-Host "Veridex is already running."
      return
    }
    if (-not $backendUp) {
      Start-Backend
      if (-not (Wait-Port -Port $backendPort -TimeoutSeconds 30)) {
        Show-StartupHelp
        throw "Backend failed to start on port $backendPort."
      }
    }
    if (-not $frontendUp) {
      Start-Frontend
      if (-not (Wait-FrontendReady -TimeoutSeconds 30)) {
        Show-StartupHelp
        throw "Frontend failed to start on port $frontendPort. Check $frontendStdoutLog and $frontendStderrLog."
      }
    }
    Write-Host "Veridex started."
    if (Test-Path $smokeScript) {
      Write-Host "Run smoke test:" -ForegroundColor Green
      Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File $smokeScript"
    }
  }
}
