from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from office_app.server.archive_service import ArchiveService
from office_app.server.command_router import CommandRouter
from office_app.server.errors import error_missing_required_field
from office_app.server.guards import ensure_single_target
from office_app.server.memo_service import MemoService
from office_app.server.nancy_service import NancyService
from office_app.server.request_pipeline import RequestPipeline
from office_app.server.tools_registry import register_tools
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_state_sha(state: Dict[str, Any]) -> str:
    import hashlib

    b = json.dumps(state, sort_keys=True).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


store = WorkspaceStore(WORKSPACES_DIR, utc_now_fn=utc_now)
kernel = WorkspaceKernel(store=store, utc_now_fn=utc_now)
memo_service = MemoService(store=store, legacy_memos_dir=LEGACY_MEMOS_DIR, utc_now_fn=utc_now)
archive_service = ArchiveService(workspaces_dir=WORKSPACES_DIR, utc_now_fn=utc_now)
nancy_service = NancyService(
    kernel=kernel,
    archive_service=archive_service,
    store=store,
    utc_now_fn=utc_now,
)
router = CommandRouter()
pipeline = RequestPipeline(
    kernel=kernel,
    navigator_control=NAVIGATOR_CONTROL,
    utc_now_fn=utc_now,
    tool_names=[],
    app_version="1.3.0",
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


class NaturalLanguageRequest(BaseModel):
    text: str = Field(..., description="Plain text request to route")
    workspace_id: Optional[str] = Field(default=None, description="Optional workspace id")


app = FastAPI(title="Veridex Office Server", version="1.3.0")


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
    return router.dispatch(tool, args)


def ensure_artifact_workspace(workspace_id: str) -> None:
    try:
        kernel.get_state(workspace_id)
    except HTTPException:
        kernel.bootstrap_workspace(workspace_id)


@app.post("/request")
def handle_natural_language_request(payload: NaturalLanguageRequest) -> Dict[str, Any]:
    workspace_id = str(payload.workspace_id or "default").strip() or "default"
    request_text = str(payload.text or "").strip()
    ensure_artifact_workspace(workspace_id)
    routed = pipeline.route_user_request(workspace_id, request_text)

    if routed["route_kind"] == "artifact":
        args = dict(routed["arguments"])
        args["workspace_id"] = workspace_id
        result = router.dispatch(routed["tool"], args)
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "artifact",
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                }
        return result

    return pipeline.nancy_route_response(workspace_id, request_text)


def handle_workspaces_list(_: Dict[str, Any]) -> Dict[str, Any]:
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
        raise HTTPException(status_code=400, detail="One memo may target only one room. Send separate memos.")

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
            "memo_id": memo_result["memo_id"],
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


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _require_artifact_workspace(workspace_id: str) -> Dict[str, Any]:
    return kernel.get_state(workspace_id)


def _artifact_summary_text(record: Dict[str, Any], action: str) -> str:
    return f"{action} artifact {record['artifact_id']} ({record.get('display_name') or record.get('title')})."


def handle_artifact_create(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)

    artifact_type = str(args.get("type") or args.get("artifact_type") or "").strip()
    title = str(args.get("title") or "").strip()
    content = str(args.get("content") or "")
    format_value = str(args.get("format") or "text/plain").strip() or "text/plain"
    status = str(args.get("status") or "active").strip() or "active"
    created_by = str(args.get("created_by") or "user").strip() or "user"
    metadata = args.get("metadata")
    source_refs = args.get("source_refs")

    record = archive_service.create_artifact(
        workspace_id=workspace_id,
        type=artifact_type,
        title=title,
        content=content,
        format=format_value,
        status=status,
        created_by=created_by,
        metadata=metadata,
        source_refs=source_refs,
    )
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": _artifact_summary_text(record, "Created")}],
    }


def handle_artifact_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")

    obj = archive_service.get_artifact(workspace_id, artifact_id)
    preview = obj.get("content_preview", "")
    return {
        "structuredContent": obj,
        "content": [{"type": "text", "text": f"Artifact {obj['artifact_id']} - {obj.get('display_name') or obj.get('title')}\n\n{preview}"}],
    }


def handle_artifact_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    include_archived = _parse_bool(args.get("include_archived"), False)
    rows = archive_service.list_artifacts(workspace_id, include_archived=include_archived)
    return {
        "structuredContent": {
            "workspace_id": workspace_id,
            "count": len(rows),
            "include_archived": include_archived,
            "artifacts": rows,
        },
        "content": [{"type": "text", "text": f"Found {len(rows)} artifact(s)."}],
    }


def handle_artifact_update(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")

    updated_fields = {
        "title": args.get("title"),
        "content": args.get("content"),
        "format": args.get("format"),
        "status": args.get("status"),
        "metadata": args.get("metadata"),
        "source_refs": args.get("source_refs"),
    }
    if all(value is None for value in updated_fields.values()):
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")

    record = archive_service.update_artifact(workspace_id=workspace_id, artifact_id=artifact_id, **updated_fields)
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": _artifact_summary_text(record, "Updated")}],
    }


def handle_artifact_append(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")

    content = args.get("content")
    if content is None:
        content = args.get("append_text")
    if content is None:
        raise error_missing_required_field("content")

    separator_value = args.get("separator")
    separator = "\n" if separator_value in (None, "") else str(separator_value)
    record = archive_service.append_to_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        content=content,
        separator=separator,
        metadata=args.get("metadata"),
        source_refs=args.get("source_refs"),
    )
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": _artifact_summary_text(record, "Appended to")}],
    }


def handle_artifact_archive(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")

    record = archive_service.archive_artifact(workspace_id=workspace_id, artifact_id=artifact_id)
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": _artifact_summary_text(record, "Archived")}],
    }


def handle_archive_store_text(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)

    name = str(args.get("name", "")).strip()
    if not name:
        raise error_missing_required_field("name")

    content = str(args.get("content", ""))
    artifact_type = str(args.get("artifact_type", "document")).strip() or "document"

    state = kernel.get_state(workspace_id)
    source_room = str(args.get("source_room") or state.get("active_room", "lobby"))
    source_persona = str(args.get("source_persona") or state.get("active_persona", "Receptionist"))

    record = archive_service.store_text_artifact(
        workspace_id=workspace_id,
        name=name,
        content=content,
        artifact_type=artifact_type,
        source_room=source_room,
        source_persona=source_persona,
    )

    append_incident(
        severity="LOW",
        clazz="ARCHIVE_STORE",
        rule_or_gate="Records Archive",
        command="office.archive_store_text",
        input_ref=json.dumps({"workspace_id": workspace_id, "name": name}),
        output_ref=record["artifact_id"],
        evidence_path=str(archive_service.db_path),
        notes=f"Stored artifact {record['artifact_id']}.",
        state_sha256=stable_state_sha(state),
    )

    try:
        store.append_transcript(
            workspace_id,
            "system",
            state.get("active_room", "records_archive"),
            f"Artifact stored: {record.get('display_name') or record.get('title')} ({record['artifact_id']})",
        )
    except Exception:
        pass

    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": f"Records Archive stored {record.get('display_name') or record.get('title')} as {record['artifact_id']}."}],
    }


def handle_archive_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    rows = archive_service.list_artifacts(workspace_id, include_archived=True)
    return {
        "structuredContent": {"workspace_id": workspace_id, "count": len(rows), "artifacts": rows},
        "content": [{"type": "text", "text": f"Found {len(rows)} artifact(s)."}],
    }


def handle_archive_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")

    obj = archive_service.get_artifact(workspace_id, artifact_id)
    preview = obj.get("content_preview", "")
    return {
        "structuredContent": obj,
        "content": [{"type": "text", "text": f"Artifact {obj['artifact_id']} - {obj['display_name']}\n\n{preview}"}],
    }


def handle_nancy_artifacts_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    return nancy_service.artifacts_list_response(workspace_id)


def handle_nancy_artifact_open(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")
    return nancy_service.artifact_open_response(workspace_id, artifact_id)


def handle_nancy_workspace_briefing(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    return nancy_service.workspace_briefing_response(workspace_id)


register_tools(
    router,
    {
        "office.workspaces_list": handle_workspaces_list,
        "office.workspace_new": handle_workspace_new,
        "office.bootstrap": handle_office_bootstrap,
        "office.state_get": handle_office_state_get,
        "office.room_set": handle_office_room_set,
        "office.nancy_route": handle_office_nancy_route,
        "mailroom.dispatch": handle_mailroom_dispatch,
        "office.artifact_create": handle_artifact_create,
        "office.artifact_get": handle_artifact_get,
        "office.artifact_list": handle_artifact_list,
        "office.artifact_update": handle_artifact_update,
        "office.artifact_append": handle_artifact_append,
        "office.artifact_archive": handle_artifact_archive,
        "office.memos_list": handle_memos_list,
        "office.memo_get": handle_memo_get,
        "office.archive_store_text": handle_archive_store_text,
        "office.archive_list": handle_archive_list,
        "office.archive_get": handle_archive_get,
        "office.nancy_artifacts_list": handle_nancy_artifacts_list,
        "office.nancy_artifact_open": handle_nancy_artifact_open,
        "office.nancy_workspace_briefing": handle_nancy_workspace_briefing,
    },
)

pipeline.tool_names = router.tool_names()
