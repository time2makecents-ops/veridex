param(
  [ValidateSet("start", "stop", "restart", "status")]
  [string]$Action = "start"
)

$backendPort = 8078
$frontendPort = 3078
$root = "C:\Office-App"
$backendScript = Join-Path $root "start_veridex_backend.ps1"
$frontendScript = Join-Path $root "start_veridex_frontend_https.ps1"

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
  foreach ($pid in $pids) {
    if ($pid -and $pid -ne 0) {
      try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "Stopped PID $pid"
      } catch {
        Write-Host "Could not stop PID ${pid}: $($_.Exception.Message)"
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

switch ($Action) {
  "stop" {
    Stop-Veridex
  }
  "status" {
    $backendUp = Test-NetConnection 127.0.0.1 -Port $backendPort -InformationLevel Quiet
    $frontendUp = Test-NetConnection 127.0.0.1 -Port $frontendPort -InformationLevel Quiet
    Write-Host "Backend ($backendPort): $backendUp"
    Write-Host "Frontend ($frontendPort): $frontendUp"
  }
  "restart" {
    Stop-Veridex
    Start-Sleep -Seconds 2
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendScript
    if (-not (Wait-Port -Port $backendPort -TimeoutSeconds 30)) {
      throw "Backend failed to start on port $backendPort."
    }
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $frontendScript
    if (-not (Wait-Port -Port $frontendPort -TimeoutSeconds 30)) {
      throw "Frontend failed to start on port $frontendPort."
    }
    Write-Host "Veridex restarted."
  }
  default {
    $backendUp = Test-NetConnection 127.0.0.1 -Port $backendPort -InformationLevel Quiet
    $frontendUp = Test-NetConnection 127.0.0.1 -Port $frontendPort -InformationLevel Quiet
    if ($backendUp -and $frontendUp) {
      Write-Host "Veridex is already running."
      return
    }
    if (-not $backendUp) {
      Start-Process powershell.exe -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendScript
      if (-not (Wait-Port -Port $backendPort -TimeoutSeconds 30)) {
        throw "Backend failed to start on port $backendPort."
      }
    }
    if (-not $frontendUp) {
      Start-Process powershell.exe -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $frontendScript
      if (-not (Wait-Port -Port $frontendPort -TimeoutSeconds 30)) {
        throw "Frontend failed to start on port $frontendPort."
      }
    }
    Write-Host "Veridex started."
  }
}
