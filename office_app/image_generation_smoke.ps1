param(
    [string]$BackendUrl = "http://127.0.0.1:8078",
    [string]$Prompt = "simple red square logo test"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Invoke-VeridexTool {
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

$BackendUrl = $BackendUrl.TrimEnd("/")

Write-Host "VERIDEX IMAGE GENERATION SMOKE" -ForegroundColor Green
Write-Host "Backend: $BackendUrl"

Write-Step "Backend Health"
$health = Invoke-RestMethod "$BackendUrl/health" -Method Get
if (-not $health.ok) {
    throw "Backend health check did not return ok=true."
}
Write-Host "Backend healthy." -ForegroundColor Green

Write-Step "Workspace Setup"
$label = "Image Smoke " + (Get-Date -Format "yyyyMMdd-HHmmss")
$workspace = Invoke-VeridexTool -Tool "office.workspace_new" -Arguments @{ label = $label }
$workspaceId = [string]$workspace.structuredContent.workspace_id
if (-not $workspaceId) {
    throw "office.workspace_new did not return workspace_id."
}
Write-Host "Workspace created: $workspaceId" -ForegroundColor Green

$room = Invoke-VeridexTool -Tool "office.room_set" -Arguments @{
    workspace_id = $workspaceId
    room_id = "art_department"
}
if ($room.structuredContent.active_room -ne "art_department") {
    throw "office.room_set did not enter art_department."
}
Write-Host "Room change OK: art_department" -ForegroundColor Green

Write-Step "Image Generation"
$generated = Invoke-VeridexTool -Tool "office.image_generate" -Arguments @{
    workspace_id = $workspaceId
    prompt = $Prompt
}

$file = $generated.structuredContent.file
if (-not $file) {
    throw "office.image_generate did not return a file record."
}
if ($file.kind -ne "generated_image") {
    throw "Expected generated_image kind, got: $($file.kind)"
}
if ($file.scope -ne "room") {
    throw "Expected room scope, got: $($file.scope)"
}
if ($file.scope_ref -ne "art_department") {
    throw "Expected scope_ref art_department, got: $($file.scope_ref)"
}
Write-Host "Generated file: $($file.file_id) ($($file.original_name))" -ForegroundColor Green
Write-Host "kind=$($file.kind) scope=$($file.scope) scope_ref=$($file.scope_ref)" -ForegroundColor Green

Write-Host ""
Write-Host "IMAGE GENERATION SMOKE PASSED" -ForegroundColor Green
