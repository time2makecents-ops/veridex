param(
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$root = "C:\Office-App"
$backendPort = 8078
$frontendPort = 3078
$frontendDir = Join-Path $root "office_app\frontend"
$backendCmd = Join-Path $root "run_server_redca.cmd"
$nodePath = "C:\Program Files\nodejs\node.exe"
$chromePath = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
$appUrl = "https://127.0.0.1:3078/chat"
$backendOut = Join-Path $root "logs\backend-redca.out.log"
$backendErr = Join-Path $root "logs\backend-redca.err.log"
$frontendOut = Join-Path $root "logs\frontend-redca.out.log"
$frontendErr = Join-Path $root "logs\frontend-redca.err.log"

if (-not (Test-Path $nodePath)) {
  $nodePath = (Get-Command node -ErrorAction Stop).Source
}

if (-not (Test-Path $chromePath)) {
  $chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
}

function Stop-Port {
  param([int[]]$Ports)
  foreach ($port in $Ports) {
    try {
      $connections = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop
      foreach ($connection in $connections) {
        if ($connection.OwningProcess) {
          Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
      }
    } catch {}
  }
}

function Wait-Port {
  param(
    [int]$Port,
    [int]$TimeoutSeconds = 30
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet) {
      return $true
    }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Test-Frontend {
  $script = @"
const https = require('https');
const req = https.get('$appUrl', { rejectUnauthorized: false }, (res) => {
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
  try {
    $status = ($script | & $nodePath -).Trim()
    return ($status -match '^\d+$' -and [int]$status -ge 200 -and [int]$status -lt 400)
  } catch {
    return $false
  }
}

function Wait-Frontend {
  param([int]$TimeoutSeconds = 45)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Frontend) {
      return $true
    }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

New-Item -ItemType Directory -Path (Join-Path $root "logs") -Force | Out-Null
Stop-Port -Ports @($backendPort, $frontendPort)

Start-Process `
  -FilePath "cmd.exe" `
  -ArgumentList "/c", "`"$backendCmd`"" `
  -WorkingDirectory $root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $backendOut `
  -RedirectStandardError $backendErr | Out-Null

if (-not (Wait-Port -Port $backendPort -TimeoutSeconds 30)) {
  throw "Backend did not start on port $backendPort. Check $backendErr"
}

Start-Process `
  -FilePath $nodePath `
  -ArgumentList "server.cjs" `
  -WorkingDirectory $frontendDir `
  -WindowStyle Hidden `
  -RedirectStandardOutput $frontendOut `
  -RedirectStandardError $frontendErr | Out-Null

if (-not (Wait-Frontend -TimeoutSeconds 45)) {
  throw "Frontend did not start on port $frontendPort. Check $frontendErr"
}

Write-Host "Veridex is running."
Write-Host "Backend:  http://127.0.0.1:8078"
Write-Host "Frontend: $appUrl"

if (-not $NoOpen) {
  if (Test-Path $chromePath) {
    Start-Process -FilePath $chromePath -ArgumentList $appUrl
  } else {
    throw "Chrome was not found. Expected C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
  }
}
