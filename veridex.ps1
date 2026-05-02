param(
  [ValidateSet("start", "stop", "restart", "status")]
  [string]$Action = "start"
)

$backendPort = 8078
$frontendPort = 3078
$root = "C:\Office-App"
$backendCommand = Join-Path $root "run_server.cmd"
$frontendDir = Join-Path $root "office_app\frontend"
$smokeScript = Join-Path $root "office_app\smoke_test.ps1"

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
  $pids = Get-ListeningPids -Ports @($backendPort, $frontendPort)
  if (-not $pids) {
    Write-Host "Veridex is not listening on $backendPort or $frontendPort."
    return
  }
  foreach ($processId in $pids) {
    if ($processId -and $processId -ne 0) {
      try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Host "Stopped PID $processId"
      } catch {
        Write-Host "Could not stop PID ${processId}: $($_.Exception.Message)"
      }
    }
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
  Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$backendCommand`"" -WorkingDirectory $root
}

function Start-Frontend {
  $nodePath = (Get-Command node -ErrorAction Stop).Source
  Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "`"$nodePath`" server.cjs" -WorkingDirectory $frontendDir
}

switch ($Action) {
  "stop" {
    Stop-Veridex
  }
  "status" {
    $backendUp = Test-NetConnection 127.0.0.1 -Port $backendPort -InformationLevel Quiet
    $frontendUp = Test-NetConnection 127.0.0.1 -Port $frontendPort -InformationLevel Quiet
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
    if (-not (Wait-Port -Port $frontendPort -TimeoutSeconds 30)) {
      Show-StartupHelp
      throw "Frontend failed to start on port $frontendPort."
    }
    Write-Host "Veridex restarted."
    if (Test-Path $smokeScript) {
      Write-Host "Run smoke test:" -ForegroundColor Green
      Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File $smokeScript"
    }
  }
  default {
    $backendUp = Test-NetConnection 127.0.0.1 -Port $backendPort -InformationLevel Quiet
    $frontendUp = Test-NetConnection 127.0.0.1 -Port $frontendPort -InformationLevel Quiet
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
      if (-not (Wait-Port -Port $frontendPort -TimeoutSeconds 30)) {
        Show-StartupHelp
        throw "Frontend failed to start on port $frontendPort."
      }
    }
    Write-Host "Veridex started."
    if (Test-Path $smokeScript) {
      Write-Host "Run smoke test:" -ForegroundColor Green
      Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File $smokeScript"
    }
  }
}
