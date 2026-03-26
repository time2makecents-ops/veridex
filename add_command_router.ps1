$ErrorActionPreference = "Stop"

$root = "C:\Office-App"
$server = Join-Path $root "office_app\server"
$appPath = Join-Path $server "app.py"
$routerPath = Join-Path $server "command_router.py"
$backupPath = Join-Path $server "app_backup_before_command_router.py"

if (-not (Test-Path $appPath)) {
    throw "app.py not found at $appPath"
}

Write-Host "Backing up app.py..." -ForegroundColor Yellow
Copy-Item $appPath $backupPath -Force

Write-Host "Writing command_router.py..." -ForegroundColor Yellow
@'
from __future__ import annotations

from typing import Any, Callable, Dict

from office_app.server.errors import error_unknown_tool

ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: Dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        self._handlers[tool_name] = handler

    def tool_names(self) -> list[str]:
        return sorted(self._handlers.keys())

    def dispatch(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise error_unknown_tool(tool_name)
        return handler(args)
'@ | Set-Content -Path $routerPath -Encoding UTF8

Write-Host "Patching app.py..." -ForegroundColor Yellow
$app = Get-Content $appPath -Raw

# 1) Add import
$importOld = "from office_app.server.archive_service import ArchiveService`r`nfrom office_app.server.errors import error_missing_required_field, error_unknown_tool"
$importNew = "from office_app.server.archive_service import ArchiveService`r`nfrom office_app.server.command_router import CommandRouter`r`nfrom office_app.server.errors import error_missing_required_field, error_unknown_tool"
if ($app -notmatch "from office_app\.server\.command_router import CommandRouter") {
    $app = $app.Replace($importOld, $importNew)
}

# 2) Replace TOOL_NAMES block with router = CommandRouter()
$toolBlock = @'
TOOL_NAMES = [
    "office.bootstrap",
    "office.state_get",
    "office.room_set",
    "office.workspaces_list",
    "office.workspace_new",
    "office.nancy_route",
    "mailroom.dispatch",
    "office.memos_list",
    "office.memo_get",
    "office.archive_store_text",
    "office.archive_list",
    "office.archive_get",
    "office.nancy_artifacts_list",
    "office.nancy_artifact_open",
    "office.nancy_workspace_briefing",
]
'@

if ($app -match [regex]::Escape($toolBlock.Trim())) {
    $app = $app.Replace($toolBlock, "router = CommandRouter()`r`n")
}

# 3) Replace pipeline construction
$pipelineOld = @'
pipeline = RequestPipeline(
    kernel=kernel,
    navigator_control=NAVIGATOR_CONTROL,
    utc_now_fn=utc_now,
    tool_names=TOOL_NAMES,
    app_version="1.3.0",
)
'@

$pipelineNew = @'
pipeline = RequestPipeline(
    kernel=kernel,
    navigator_control=NAVIGATOR_CONTROL,
    utc_now_fn=utc_now,
    tool_names=[],
    app_version="1.3.0",
)
'@

$app = $app.Replace($pipelineOld, $pipelineNew)

# 4) Replace call_tool function
$callOld = @'
@app.post("/call")
def call_tool(call: ToolCall) -> Dict[str, Any]:
    tool = call.tool.strip()
    args = dict(call.arguments or {})
    workspace_id = resolve_workspace_id(tool, args)
    if workspace_id:
        args["workspace_id"] = workspace_id

    if tool == "office.workspaces_list":
        return handle_workspaces_list()
    if tool == "office.workspace_new":
        return handle_workspace_new(args)
    if tool == "office.bootstrap":
        return handle_office_bootstrap(args)
    if tool == "office.state_get":
        return handle_office_state_get(args)
    if tool == "office.room_set":
        return handle_office_room_set(args)
    if tool == "office.nancy_route":
        return handle_office_nancy_route(args)
    if tool == "mailroom.dispatch":
        return handle_mailroom_dispatch(args)
    if tool == "office.memos_list":
        return handle_memos_list(args)
    if tool == "office.memo_get":
        return handle_memo_get(args)
    if tool == "office.archive_store_text":
        return handle_archive_store_text(args)
    if tool == "office.archive_list":
        return handle_archive_list(args)
    if tool == "office.archive_get":
        return handle_archive_get(args)
    if tool == "office.nancy_artifacts_list":
        return handle_nancy_artifacts_list(args)
    if tool == "office.nancy_artifact_open":
        return handle_nancy_artifact_open(args)
    if tool == "office.nancy_workspace_briefing":
        return handle_nancy_workspace_briefing(args)

    raise error_unknown_tool(tool)
'@

$callNew = @'
@app.post("/call")
def call_tool(call: ToolCall) -> Dict[str, Any]:
    tool = call.tool.strip()
    args = dict(call.arguments or {})
    workspace_id = resolve_workspace_id(tool, args)
    if workspace_id:
        args["workspace_id"] = workspace_id
    return router.dispatch(tool, args)
'@

$app = $app.Replace($callOld, $callNew)

# 5) Append registrations if not already present
if ($app -notmatch 'router\.register\("office\.workspaces_list"') {
    $registrationBlock = @'

router.register("office.workspaces_list", lambda args: handle_workspaces_list())
router.register("office.workspace_new", handle_workspace_new)
router.register("office.bootstrap", handle_office_bootstrap)
router.register("office.state_get", handle_office_state_get)
router.register("office.room_set", handle_office_room_set)
router.register("office.nancy_route", handle_office_nancy_route)
router.register("mailroom.dispatch", handle_mailroom_dispatch)
router.register("office.memos_list", handle_memos_list)
router.register("office.memo_get", handle_memo_get)
router.register("office.archive_store_text", handle_archive_store_text)
router.register("office.archive_list", handle_archive_list)
router.register("office.archive_get", handle_archive_get)
router.register("office.nancy_artifacts_list", handle_nancy_artifacts_list)
router.register("office.nancy_artifact_open", handle_nancy_artifact_open)
router.register("office.nancy_workspace_briefing", handle_nancy_workspace_briefing)

pipeline.tool_names = router.tool_names()
'@
    $app = $app.TrimEnd() + "`r`n" + $registrationBlock
}

Set-Content -Path $appPath -Value $app -Encoding UTF8

Write-Host "Done." -ForegroundColor Green
Write-Host "Created: $routerPath"
Write-Host "Backup:  $backupPath"
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "1) uvicorn office_app.server.app:app --reload"
Write-Host "2) Run /tools and confirm commands still appear"