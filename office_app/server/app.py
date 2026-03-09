from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from office_app.server.errors import error_missing_required_field, error_unknown_tool
from office_app.server.guards import ensure_single_target
from office_app.server.memo_service import MemoService
from office_app.server.request_pipeline import RequestPipeline
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore

SERVER_DIR = Path(__file__).resolve().parent
PKG_DIR = SERVER_DIR.parent
ROOT_DIR = PKG_DIR.parent

BACKEND_DIR = PKG_DIR / "backend"
DATA_DIR = PKG_DIR / "data"
RUNTIME_DIR = PKG_DIR / "runtime"
WORKSPACES_DIR = RUNTIME_DIR / "workspaces"
LEGACY_MEMOS_DIR = RUNTIME_DIR / "memos"

INCIDENT_LOG_PATH = BACKEND_DIR / "incident_log.csv"

NAVIGATOR_CONTROL = {
    "id": "NAVIGATOR",
    "status": "ACTIVE",
    "visibility": "INVISIBLE",
}

WORKSPACE_TOOLS_NO_ID = {
    "office.workspaces_list",
    "office.workspace_new",
}

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
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_state_sha(state: Dict[str, Any]) -> str:
    import hashlib

    b = json.dumps(state, sort_keys=True).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


store = WorkspaceStore(WORKSPACES_DIR, utc_now_fn=utc_now)
kernel = WorkspaceKernel(store=store, utc_now_fn=utc_now)
memo_service = MemoService(store=store, legacy_memos_dir=LEGACY_MEMOS_DIR, utc_now_fn=utc_now)
pipeline = RequestPipeline(
    kernel=kernel,
    navigator_control=NAVIGATOR_CONTROL,
    utc_now_fn=utc_now,
    tool_names=TOOL_NAMES,
    app_version="1.2.0",
)


def ensure_incident_log_header() -> None:
    if INCIDENT_LOG_PATH.exists() and INCIDENT_LOG_PATH.stat().st_size > 0:
        return
    INCIDENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    INCIDENT_LOG_PATH.write_text(
        "incident_id,utc_ts,severity,class,rule_or_gate,command,input_ref,output_ref,evidence_path,notes,state_sha256\n",
        encoding="utf-8",
    )


def append_incident(
    *,
    severity: str,
    clazz: str,
    rule_or_gate: str,
    command: str,
    input_ref: str,
    output_ref: str,
    evidence_path: str,
    notes: str,
    state_sha256: str,
    incident_id: Optional[str] = None,
) -> str:
    ensure_incident_log_header()
    inc_id = incident_id or f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    row = [
        inc_id,
        utc_now(),
        severity,
        clazz,
        rule_or_gate,
        command,
        input_ref,
        output_ref,
        evidence_path,
        notes,
        state_sha256,
    ]
    with INCIDENT_LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    return inc_id


def resolve_workspace_id(tool: str, args: Dict[str, Any]) -> str:
    workspace_id = str(args.get("workspace_id", "")).strip()
    if tool in WORKSPACE_TOOLS_NO_ID:
        return workspace_id
    if workspace_id:
        return workspace_id
    return "default_workspace"


class ToolCall(BaseModel):
    tool: str = Field(..., description="Tool name, e.g. office.bootstrap")
    arguments: Dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="Veridex Office Server", version="1.2.0")


@app.on_event("startup")
def startup_init() -> None:
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_MEMOS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_incident_log_header()


@app.get("/health")
def health() -> Dict[str, Any]:
    return pipeline.health_response()


@app.get("/tools")
def tools() -> Dict[str, Any]:
    return pipeline.tools_response()


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

    raise error_unknown_tool(tool)


def handle_workspaces_list() -> Dict[str, Any]:
    idx = kernel.list_workspaces()
    return pipeline.workspaces_list_response(idx)


def handle_workspace_new(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
    label = str(args.get("label") or f"Workspace {utc_now()}")
    kernel.create_workspace(workspace_id, label)
    return pipeline.workspace_new_response(workspace_id, label)


def handle_office_bootstrap(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    state, created = kernel.bootstrap_workspace(workspace_id)

    if created:
        append_incident(
            severity="LOW",
            clazz="BOOTSTRAP",
            rule_or_gate="",
            command="office.bootstrap",
            input_ref=json.dumps({"workspace_id": workspace_id}),
            output_ref="state.json",
            evidence_path=str(store.state_path(workspace_id)),
            notes="Initialized workspace state (default lobby + receptionist).",
            state_sha256=stable_state_sha(state),
        )

    return pipeline.snapshot_response(workspace_id)


def handle_office_state_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    return pipeline.snapshot_response(workspace_id)


def handle_office_room_set(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    room_id = str(args.get("room_id", "")).strip()
    if not room_id:
        raise error_missing_required_field("room_id")

    result = kernel.enter_room(workspace_id, room_id)
    state = kernel.get_state(workspace_id)

    append_incident(
        severity="LOW",
        clazz="STATE_CHANGE",
        rule_or_gate="Room State Model v1.1.0",
        command="office.room_set",
        input_ref=json.dumps({"workspace_id": workspace_id, "room_id": result["active_room"]}),
        output_ref="state.json",
        evidence_path=str(store.state_path(workspace_id)),
        notes=f"active_room: {result['previous_room']} -> {result['active_room']}",
        state_sha256=stable_state_sha(state),
    )

    return pipeline.enter_room_response(workspace_id, result)


def handle_office_nancy_route(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    request_text = str(args.get("request", "")).strip()
    if not request_text:
        raise error_missing_required_field("request")
    return pipeline.nancy_route_response(workspace_id, request_text)


def handle_mailroom_dispatch(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    for field in ("to_room", "body"):
        if field not in args:
            raise error_missing_required_field(field)

    to_room_raw = str(args["to_room"])
    ensure_single_target(to_room_raw)
    if "," in to_room_raw or " and " in to_room_raw.lower() or "&" in to_room_raw:
        raise error_missing_required_field("single to_room target")

    body = str(args["body"]).strip()
    explicit_persona = str(args.get("explicit_persona", "")).strip() or None

    state = kernel.get_state(workspace_id)
    from_room_external = state.get("active_room", "lobby")
    memo_result = memo_service.dispatch_memo(
        workspace_id=workspace_id,
        from_room=from_room_external,
        to_room=to_room_raw,
        body=body,
        explicit_persona=explicit_persona,
        policy_check_fn=pipeline.assert_mailroom_allowed,
    )

    append_incident(
        severity="LOW",
        clazz="MEMO_DISPATCH",
        rule_or_gate="Mailroom Dispatch Contract v1.1.0",
        command="mailroom.dispatch",
        input_ref=json.dumps({
            "workspace_id": workspace_id,
            "from_room": from_room_external,
            "to_room": memo_result["to_room"],
            "memo_id": memo_result["memo_id"]
        }),
        output_ref="(tool_response)",
        evidence_path=str(store.memos_dir(workspace_id)),
        notes="Recorded memo dispatch (single-target).",
        state_sha256=stable_state_sha(state),
    )

    return pipeline.mailroom_response(
        workspace_id=workspace_id,
        memo_id=memo_result["memo_id"],
        from_room=from_room_external,
        to_room=memo_result["to_room"],
        to_persona=memo_result["to_persona"],
        subject=memo_result["subject"],
        dest_room_title=memo_result["dest_room_title"],
    )


def handle_memos_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    limit = int(args.get("limit", 25))
    rows = memo_service.list_memos(workspace_id, limit=limit)
    return pipeline.memos_list_response(workspace_id, rows)


def handle_memo_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    memo_id = str(args.get("memo_id", "")).strip()
    if not memo_id:
        raise error_missing_required_field("memo_id")

    obj, body = memo_service.get_memo(workspace_id, memo_id)
    return pipeline.memo_get_response(obj, body)
