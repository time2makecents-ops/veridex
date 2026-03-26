$base = "http://127.0.0.1:8000"

Write-Host ""
Write-Host "VERIDEX SERVER SMOKE TEST" -ForegroundColor Cyan
Write-Host "-------------------------" 

Write-Host "`n== HEALTH ==" -ForegroundColor Cyan
Invoke-RestMethod "$base/health" -Method Get | ConvertTo-Json -Depth 5

Write-Host "`n== TOOLS ==" -ForegroundColor Cyan
$tools = Invoke-RestMethod "$base/tools" -Method Get
$tools | ConvertTo-Json -Depth 10

$required = @(
    "office.workspace_new",
    "office.workspaces_list",
    "office.bootstrap",
    "office.state_get",
    "office.room_set",
    "mailroom.dispatch",
    "office.memos_list",
    "office.memo_get"
)

$missing = @()
foreach ($r in $required) {
    if (-not ($tools.tools -contains $r)) {
        $missing += $r
    }
}

if ($missing.Count -gt 0) {
    Write-Host "`nMissing expected tools:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow }
} else {
    Write-Host "`nAll expected tools detected." -ForegroundColor Green
}

Write-Host "`n== CREATE WORKSPACE ==" -ForegroundColor Cyan
$ws = Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body '{"tool":"office.workspace_new","arguments":{"label":"Smoke Test"}}'

$ws | ConvertTo-Json -Depth 10

$wid = $ws.structuredContent.workspace_id
if (-not $wid) {
    Write-Host "`nWorkspace creation failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nWorkspace ID: $wid" -ForegroundColor Green

Write-Host "`n== LIST WORKSPACES ==" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body '{"tool":"office.workspaces_list","arguments":{}}' | ConvertTo-Json -Depth 10

Write-Host "`n== BOOTSTRAP ==" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"office.bootstrap`",`"arguments`":{`"workspace_id`":`"$wid`"}} " | ConvertTo-Json -Depth 10

Write-Host "`n== STATE GET ==" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"office.state_get`",`"arguments`":{`"workspace_id`":`"$wid`"}} " | ConvertTo-Json -Depth 10

Write-Host "`n== ROOM SET: control_room ==" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"office.room_set`",`"arguments`":{`"workspace_id`":`"$wid`",`"room_id`":`"control_room`"}} " | ConvertTo-Json -Depth 10

Write-Host "`n== STATE GET AFTER ROOM SET ==" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"office.state_get`",`"arguments`":{`"workspace_id`":`"$wid`"}} " | ConvertTo-Json -Depth 10

Write-Host "`n== MAILROOM DISPATCH ==" -ForegroundColor Cyan
$mail = Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"mailroom.dispatch`",`"arguments`":{`"workspace_id`":`"$wid`",`"to_room`":`"it_department`",`"subject`":`"Smoke test`",`"body`":`"Testing mailroom dispatch.`"}}"

$mail | ConvertTo-Json -Depth 10

$memos = $null
Write-Host "`n== MEMOS LIST ==" -ForegroundColor Cyan
$memos = Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"office.memos_list`",`"arguments`":{`"workspace_id`":`"$wid`"}}"

$memos | ConvertTo-Json -Depth 10

$memoId = $null
if ($memos.structuredContent -and $memos.structuredContent.memos -and $memos.structuredContent.memos.Count -gt 0) {
    $memoId = $memos.structuredContent.memos[0].memo_id
}

if ($memoId) {
    Write-Host "`n== MEMO GET ==" -ForegroundColor Cyan
    Invoke-RestMethod `
        -Uri "$base/call" `
        -Method Post `
        -ContentType "application/json" `
        -Body "{`"tool`":`"office.memo_get`",`"arguments`":{`"workspace_id`":`"$wid`",`"memo_id`":`"$memoId`"}} " | ConvertTo-Json -Depth 10
} else {
    Write-Host "`nNo memo_id found to test office.memo_get." -ForegroundColor Yellow
}

Write-Host "`n== NANCY ROUTE TEST ==" -ForegroundColor Cyan
$nancy = Invoke-RestMethod `
    -Uri "$base/call" `
    -Method Post `
    -ContentType "application/json" `
    -Body "{`"tool`":`"office.nancy_route`",`"arguments`":{`"workspace_id`":`"$wid`",`"request`":`"I need help reviewing a contract`"}}"

$nancy | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "SMOKE TEST COMPLETE" -ForegroundColor Green