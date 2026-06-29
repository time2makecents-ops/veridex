param(
    [Parameter(Mandatory = $true)]
    [string]$SessionId,

    [string]$BackendUrl = "http://127.0.0.1:8078",
    [string]$GmailQuery = "newer_than:30d",
    [int]$CalendarWindowDays = 14,
    [int]$MaxGmailResults = 1
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

    $blockedTools = @(
        "office.gmail_send",
        "office.integration_confirm",
        "office.calendar_create",
        "office.calendar_update",
        "office.calendar_cancel"
    )
    if ($blockedTools -contains $Tool) {
        throw "Integration smoke refuses to call write-capable tool: $Tool"
    }

    $body = @{
        tool = $Tool
        arguments = $Arguments
    } | ConvertTo-Json -Depth 10

    Invoke-RestMethod -Uri "$BackendUrl/call" -Method Post -ContentType "application/json" -Body $body
}

if (-not $SessionId.Trim()) {
    throw "SessionId is required."
}

$BackendUrl = $BackendUrl.TrimEnd("/")

Write-Host "VERIDEX INTEGRATION SMOKE" -ForegroundColor Green
Write-Host "Backend: $BackendUrl"

Write-Step "Backend Health"
$health = Invoke-RestMethod "$BackendUrl/health" -Method Get
if (-not $health.ok) {
    throw "Backend health check did not return ok=true."
}
Write-Host "Backend healthy." -ForegroundColor Green

Write-Step "Google Connection"
$integrationsUrl = "$BackendUrl/integrations?session_id=$([uri]::EscapeDataString($SessionId))"
$integrations = Invoke-RestMethod $integrationsUrl -Method Get
$connections = @($integrations.structuredContent.connections)
$google = $connections | Where-Object { $_.provider -eq "google" } | Select-Object -First 1
if (-not $google) {
    throw "Google provider was not returned by /integrations."
}
if (-not $google.configured) {
    throw "Google integration is not configured on this server."
}
if (-not $google.connected) {
    throw "Google integration is configured but not connected for this session."
}
Write-Host "Google connected as $($google.account_email)." -ForegroundColor Green
if ($google.scopes) {
    Write-Host "Scopes: $($google.scopes -join ', ')"
}

Write-Step "Gmail Search"
$gmail = Invoke-VeridexTool -Tool "office.gmail_search" -Arguments @{
    session_id = $SessionId
    query = $GmailQuery
    max_results = $MaxGmailResults
}
$gmailMessages = @($gmail.structuredContent.messages)
Write-Host "Gmail search succeeded. Count returned: $($gmailMessages.Count)" -ForegroundColor Green

Write-Step "Calendar List"
$now = [DateTimeOffset]::UtcNow
$timeMin = $now.ToString("yyyy-MM-ddTHH:mm:ssZ")
$timeMax = $now.AddDays($CalendarWindowDays).ToString("yyyy-MM-ddTHH:mm:ssZ")
$calendar = Invoke-VeridexTool -Tool "office.calendar_list" -Arguments @{
    session_id = $SessionId
    time_min = $timeMin
    time_max = $timeMax
}
$events = @($calendar.structuredContent.events)
Write-Host "Calendar list succeeded. Count returned: $($events.Count)" -ForegroundColor Green

Write-Host ""
Write-Host "INTEGRATION SMOKE PASSED" -ForegroundColor Green
