param(
    [string]$BackendUrl = "http://127.0.0.1:8078",
    [switch]$RestartBackend
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
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
    Invoke-RestMethod -Uri "$BackendUrl/call" -Method Post -ContentType "application/json" -Body $body
}

function Assert-ActiveContext {
    param(
        [object]$Response,
        [string]$ExpectedTitle,
        [string]$Label
    )
    $contexts = @($Response.structuredContent.active_work_context)
    if ($contexts.Count -lt 1) {
        throw "$Label did not return any active work context."
    }
    $title = [string]$contexts[0].title
    if ($title -ne $ExpectedTitle) {
        throw "$Label returned active work title '$title', expected '$ExpectedTitle'."
    }
    Write-Host "$Label returned active work context: $title" -ForegroundColor Green
}

function Restart-ManagedBackend {
    param([string]$RootPath)

    Write-Step "Managed Backend Restart"
    $restartScript = Join-Path $RootPath "veridex.ps1"
    if (-not (Test-Path $restartScript)) {
        throw "Could not find managed restart script at $restartScript."
    }

    Write-Host "Restarting Veridex through $restartScript restart" -ForegroundColor Yellow
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restartScript -Action restart

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod "$BackendUrl/health" -Method Get -TimeoutSec 3
            if ($health.ok) {
                Write-Host "Backend healthy after restart." -ForegroundColor Green
                return
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }

    throw "Backend did not become healthy after managed restart."
}

Write-Host "VERIDEX WORK CONTEXT SMOKE" -ForegroundColor Green
Write-Host "Backend: $BackendUrl"

Write-Step "Backend Health"
$health = Invoke-RestMethod "$BackendUrl/health" -Method Get
if (-not $health.ok) {
    throw "Backend health check did not return ok=true."
}
Write-Host "Backend healthy." -ForegroundColor Green

Write-Step "Create Test User And Workspace"
$suffix = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$pin = [string](Get-Random -Minimum 1000 -Maximum 9999)
$onboardBody = @{
    name = "Work Context Smoke $suffix"
    display_name = "Work Context Smoke $suffix"
    pin_code = $pin
} | ConvertTo-Json -Depth 10
$onboard = Invoke-RestMethod -Uri "$BackendUrl/lobby/onboard" -Method Post -ContentType "application/json" -Body $onboardBody
$sessionId = [string]$onboard.structuredContent.session_id
if (-not $sessionId) {
    throw "Onboarding did not return a session id."
}

$created = Invoke-Tool -Tool "office.workspace_new" -Arguments @{
    session_id = $sessionId
    label = "Work Context Smoke $suffix"
}
$workspaceId = [string]$created.structuredContent.workspace_id
if (-not $workspaceId) {
    throw "Workspace creation did not return a workspace id."
}
Write-Host "Session: $sessionId"
Write-Host "Workspace: $workspaceId"

Write-Step "Save Active Work Context"
$expectedTitle = "Smoke continuity $suffix"
$saved = Invoke-Tool -Tool "office.work_context_save" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
    title = $expectedTitle
    summary = "Verify active work survives state, room, and workspace transitions."
}
$contextId = [string]$saved.structuredContent.context.context_id
if (-not $contextId) {
    throw "Work context save did not return context_id."
}
Write-Host "Context: $contextId" -ForegroundColor Green

Write-Step "State Hydration"
$state = Invoke-Tool -Tool "office.state_get" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
}
Assert-ActiveContext -Response $state -ExpectedTitle $expectedTitle -Label "state_get"

if ($RestartBackend) {
    Restart-ManagedBackend -RootPath (Split-Path -Parent $PSScriptRoot)
    Write-Step "State Hydration After Restart"
    $stateAfterRestart = Invoke-Tool -Tool "office.state_get" -Arguments @{
        workspace_id = $workspaceId
        session_id = $sessionId
    }
    Assert-ActiveContext -Response $stateAfterRestart -ExpectedTitle $expectedTitle -Label "state_get after restart"
}

Write-Step "Room Switch Hydration"
$room = Invoke-Tool -Tool "office.room_set" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
    room_id = "marketing_room"
}
if ([string]$room.structuredContent.active_room -ne "marketing_room") {
    throw "room_set did not switch to marketing_room."
}
Assert-ActiveContext -Response $room -ExpectedTitle $expectedTitle -Label "room_set"

Write-Step "Workspace Activation Hydration"
$activated = Invoke-Tool -Tool "office.workspace_activate" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
}
$activatedContexts = @($activated.structuredContent.workspace_state.active_work_context)
if ($activatedContexts.Count -lt 1) {
    throw "workspace_activate did not return active work context."
}
if ([string]$activatedContexts[0].title -ne $expectedTitle) {
    throw "workspace_activate returned '$($activatedContexts[0].title)', expected '$expectedTitle'."
}
Write-Host "workspace_activate returned active work context: $($activatedContexts[0].title)" -ForegroundColor Green

Write-Step "Session Activation Hydration"
$createdSession = Invoke-Tool -Tool "office.session_create" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
    title = "Work context smoke follow-up"
    description = "Verify active work context survives session activation."
}
$nextSessionId = [string]$createdSession.structuredContent.session_id
if (-not $nextSessionId) {
    throw "session_create did not return a session id."
}
$activatedSession = Invoke-Tool -Tool "office.session_activate" -Arguments @{
    workspace_id = $workspaceId
    session_id = $nextSessionId
}
$sessionContexts = @($activatedSession.structuredContent.workspace_state.active_work_context)
if ($sessionContexts.Count -lt 1) {
    throw "session_activate did not return active work context."
}
if ([string]$sessionContexts[0].title -ne $expectedTitle) {
    throw "session_activate returned '$($sessionContexts[0].title)', expected '$expectedTitle'."
}
Write-Host "session_activate returned active work context: $($sessionContexts[0].title)" -ForegroundColor Green

Write-Step "Complete Active Work Context"
$completed = Invoke-Tool -Tool "office.work_context_complete" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
    context_id = $contextId
}
if ([int]$completed.structuredContent.completed_count -ne 1) {
    throw "Expected completed_count=1."
}
Write-Host "Completed context $contextId." -ForegroundColor Green

Write-Step "Verify No Active Context Remains"
$after = Invoke-Tool -Tool "office.work_context_list" -Arguments @{
    workspace_id = $workspaceId
    session_id = $sessionId
    status = "active"
    limit = 8
}
$remaining = @($after.structuredContent.contexts)
if ($remaining.Count -ne 0) {
    throw "Expected no active work contexts after completion, found $($remaining.Count)."
}
Write-Host "Active work context cleared." -ForegroundColor Green

Write-Host ""
Write-Host "WORK CONTEXT SMOKE PASSED" -ForegroundColor Green
