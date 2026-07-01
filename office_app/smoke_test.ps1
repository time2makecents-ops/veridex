param(
    [switch]$Deep
)

$ErrorActionPreference = "Stop"

$backend = "http://127.0.0.1:8078"
$frontend = "https://127.0.0.1:3078"
$root = "C:\Office-App"
function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Get-EnvValue {
    param([string]$Name)
    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if ($processValue) {
        return $processValue
    }
    $paths = @(
        (Join-Path $root ".env"),
        (Join-Path $root ".env.local"),
        (Join-Path $root "office_app\.env"),
        (Join-Path $root "office_app\.env.local")
    )
    foreach ($path in $paths) {
        if (-not (Test-Path $path)) {
            continue
        }
        foreach ($line in Get-Content $path) {
            $trimmed = $line.Trim()
            if (-not $trimmed -or $trimmed.StartsWith("#") -or $trimmed -notmatch "=") {
                continue
            }
            $parts = $trimmed.Split("=", 2)
            if ($parts[0].Trim() -eq $Name) {
                return $parts[1].Trim().Trim('"').Trim("'")
            }
        }
    }
    return ""
}

function Test-Port {
    param(
        [string]$Name,
        [int]$Port
    )
    $up = Test-NetConnection 127.0.0.1 -Port $Port -InformationLevel Quiet
    if (-not $up) {
        throw "$Name is not listening on port $Port."
    }
    Write-Host "$Name port $Port is listening." -ForegroundColor Green
}

function Invoke-Tool {
    param(
        [string]$Tool,
        [hashtable]$Arguments
    )
    $body = @{
        tool = $Tool
        arguments = $Arguments
    } | ConvertTo-Json -Depth 10
    Invoke-RestMethod -Uri "$backend/call" -Method Post -ContentType "application/json" -Body $body
}

Write-Host "VERIDEX SMOKE TEST" -ForegroundColor Green
Write-Host "Backend:  $backend"
Write-Host "Frontend: $frontend"

Write-Step "Ports"
Test-Port -Name "Backend" -Port 8078
Test-Port -Name "Frontend" -Port 3078

Write-Step "Backend Health"
$health = Invoke-RestMethod "$backend/health" -Method Get
$health | ConvertTo-Json -Depth 5

Write-Step "Tools"
$tools = Invoke-RestMethod "$backend/tools" -Method Get
$toolNames = @($tools.tools)
$requiredTools = @(
    "office.workspace_new",
    "office.workspaces_list",
    "office.bootstrap",
    "office.state_get",
    "office.room_set",
    "office.room_capabilities",
    "office.search_web",
    "office.search_reviews",
    "office.search_places",
    "office.image_generate",
    "office.file_upload",
    "office.file_list",
    "office.file_get"
)
$missingTools = @($requiredTools | Where-Object { $toolNames -notcontains $_ })
if ($missingTools.Count -gt 0) {
    throw "Missing expected tools: $($missingTools -join ', ')"
}
Write-Host "Required tools detected." -ForegroundColor Green

Write-Step "Frontend HTTPS"
$node = Get-Command node -ErrorAction Stop
$nodeScript = @"
const https = require('https');
const req = https.get('$frontend', { rejectUnauthorized: false }, (res) => {
  console.log(String(res.statusCode || 0));
  res.resume();
});
req.on('error', () => {
  console.log('0');
  process.exitCode = 1;
});
req.setTimeout(10000, () => {
  console.log('0');
  req.destroy();
  process.exitCode = 1;
});
"@
$frontendStatus = ($nodeScript | & $node.Source -).Trim()
if ($frontendStatus -notmatch '^\d+$' -or [int]$frontendStatus -lt 200 -or [int]$frontendStatus -ge 400) {
    throw "Frontend returned HTTP $frontendStatus."
}
Write-Host "Frontend returned HTTP $frontendStatus." -ForegroundColor Green

Write-Step "Search Provider Config"
$serpapiReady = [bool](Get-EnvValue "SERPAPI_API_KEY")
$googleApiReady = [bool]((Get-EnvValue "GOOGLE_SEARCH_API_KEY") -or (Get-EnvValue "GEMINI_API_KEY"))
$googleEngineReady = [bool]((Get-EnvValue "GOOGLE_SEARCH_ENGINE_ID") -or (Get-EnvValue "GOOGLE_CSE_ID"))
Write-Host "serpapi_ready=$($serpapiReady.ToString().ToLower())"
Write-Host "google_custom_ready=$(($googleApiReady -and $googleEngineReady).ToString().ToLower())"
Write-Host "duckduckgo_fallback=true"

if ($Deep) {
    Write-Step "Deep Backend Tool Flow"
    $label = "Smoke Test " + (Get-Date -Format "yyyyMMdd-HHmmss")
    $workspace = Invoke-Tool -Tool "office.workspace_new" -Arguments @{ label = $label }
    $workspaceId = $workspace.structuredContent.workspace_id
    if (-not $workspaceId) {
        throw "office.workspace_new did not return workspace_id."
    }
    Write-Host "Workspace created: $workspaceId" -ForegroundColor Green

    $state = Invoke-Tool -Tool "office.state_get" -Arguments @{ workspace_id = $workspaceId }
    if (-not $state.structuredContent.active_room) {
        throw "office.state_get did not return active_room."
    }
    Write-Host "Initial room: $($state.structuredContent.active_room)" -ForegroundColor Green

    $room = Invoke-Tool -Tool "office.room_set" -Arguments @{ workspace_id = $workspaceId; room_id = "marketing_room" }
    if ($room.structuredContent.active_room -ne "marketing_room") {
        throw "office.room_set did not enter marketing_room."
    }
    Write-Host "Room change OK: marketing_room" -ForegroundColor Green

    $search = Invoke-Tool -Tool "office.search_web" -Arguments @{ workspace_id = $workspaceId; query = "Eugene Oregon city government"; limit = 1 }
    if (-not $search.structuredContent.provider) {
        throw "office.search_web did not return a provider."
    }
    Write-Host "Search provider: $($search.structuredContent.provider)" -ForegroundColor Green
}

Write-Host ""
Write-Host "SMOKE TEST PASSED" -ForegroundColor Green
