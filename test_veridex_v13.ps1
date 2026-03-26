$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:8000"

function Call-Tool {
    param(
        [string]$Tool,
        [hashtable]$Arguments
    )

    $body = @{
        tool = $Tool
        arguments = $Arguments
    } | ConvertTo-Json -Depth 10

    Write-Host "`n=== CALL $Tool ===" -ForegroundColor Cyan
    $response = Invoke-RestMethod -Uri "$base/call" -Method Post -ContentType "application/json" -Body $body
    $response | ConvertTo-Json -Depth 10
    return $response
}

Write-Host "=== VERIDEX V1.3 TEST START ===" -ForegroundColor Green

Write-Host "`n=== GET /health ===" -ForegroundColor Yellow
$health = Invoke-RestMethod -Uri "$base/health" -Method Get
$health | ConvertTo-Json -Depth 10

Write-Host "`n=== GET /tools ===" -ForegroundColor Yellow
$tools = Invoke-RestMethod -Uri "$base/tools" -Method Get
$tools | ConvertTo-Json -Depth 10

# 1) Create workspace
$workspaceNew = Call-Tool -Tool "office.workspace_new" -Arguments @{
    label = "V13 Test Workspace"
}

$workspaceId = $workspaceNew.structuredContent.workspace_id
if (-not $workspaceId) {
    throw "workspace_id was not returned from office.workspace_new"
}

Write-Host "`nWorkspace ID: $workspaceId" -ForegroundColor Green

# 2) Bootstrap
$bootstrap = Call-Tool -Tool "office.bootstrap" -Arguments @{
    workspace_id = $workspaceId
}

# 3) State get
$stateGet = Call-Tool -Tool "office.state_get" -Arguments @{
    workspace_id = $workspaceId
}

# 4) Room set to my_office
$roomSet = Call-Tool -Tool "office.room_set" -Arguments @{
    workspace_id = $workspaceId
    room_id = "my_office"
}

# 5) Archive store text
$archiveStore = Call-Tool -Tool "office.archive_store_text" -Arguments @{
    workspace_id = $workspaceId
    name = "Test Artifact"
    content = "This is a test artifact stored by the Veridex v1.3 validation script."
    artifact_type = "document"
}

$artifactId = $archiveStore.structuredContent.artifact_id
if (-not $artifactId) {
    throw "artifact_id was not returned from office.archive_store_text"
}

Write-Host "`nArtifact ID: $artifactId" -ForegroundColor Green

# 6) Archive list
$archiveList = Call-Tool -Tool "office.archive_list" -Arguments @{
    workspace_id = $workspaceId
}

# 7) Archive get
$archiveGet = Call-Tool -Tool "office.archive_get" -Arguments @{
    workspace_id = $workspaceId
    artifact_id = $artifactId
}

# 8) Nancy artifacts list
$nancyList = Call-Tool -Tool "office.nancy_artifacts_list" -Arguments @{
    workspace_id = $workspaceId
}

# 9) Nancy artifact open
$nancyOpen = Call-Tool -Tool "office.nancy_artifact_open" -Arguments @{
    workspace_id = $workspaceId
    artifact_id = $artifactId
}

# 10) Nancy workspace briefing
$nancyBrief = Call-Tool -Tool "office.nancy_workspace_briefing" -Arguments @{
    workspace_id = $workspaceId
}

# 11) Optional memo dispatch test
$memoDispatch = Call-Tool -Tool "mailroom.dispatch" -Arguments @{
    workspace_id = $workspaceId
    to_room = "records_archive"
    body = "Please note that the test artifact was successfully stored."
}

# 12) Memo list
$memosList = Call-Tool -Tool "office.memos_list" -Arguments @{
    workspace_id = $workspaceId
}

Write-Host "`n=== VERIDEX V1.3 TEST COMPLETE ===" -ForegroundColor Green