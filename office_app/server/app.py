from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from office_app.server.guards import ensure_single_target
from office_app.server.subject import generate_subject
from office_app.server.memo_store import MemoStore
from office_app.server.models import Memo
from office_app.server.room_router import (
    default_persona_for_external_room,
    normalize_external_room,
    validate_room,
)
from office_app.server.request_pipeline import RequestPipeline

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


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def build_workspace_state(workspace_id: str, active_room: str = "lobby") -> Dict[str, Any]:
    return {
        "schema_version": "1.1.7",
        "workspace_id": workspace_id,
        "active_room": active_room,
        "active_persona": default_persona_for_external_room(active_room),
        "active_mode": "STANDARD",
        "scope_lock": {"enabled": True, "max_rooms": 1},
        "engaged": {"CRE": False},
        "gates": {"SAVE_GATE": True, "PREFLIGHT": True, "VERIFICATION": True},
        "created_at": utc_now(),
        "vr_session": {},
    }


class WorkspaceStore:
    def __init__(self, workspaces_dir: Path):
        self.workspaces_dir = workspaces_dir
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.workspaces_dir / "index.json"

    def workspace_dir(self, workspace_id: str) -> Path:
        p = self.workspaces_dir / workspace_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def state_path(self, workspace_id: str) -> Path:
        return self.workspace_dir(workspace_id) / "state.json"

    def transcript_path(self, workspace_id: str) -> Path:
        return self.workspace_dir(workspace_id) / "transcript.ndjson"

    def memos_dir(self, workspace_id: str) -> Path:
        p = self.workspace_dir(workspace_id) / "memos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def load_state(self, workspace_id: str) -> Dict[str, Any]:
        return _read_json(self.state_path(workspace_id), {})

    def save_state(self, workspace_id: str, state: Dict[str, Any]) -> None:
        state["updated_at"] = utc_now()
        _write_json(self.state_path(workspace_id), state)

    def append_transcript(self, workspace_id: str, role: str, room_id: str, text: str) -> None:
        entry = {"ts": utc_now(), "role": role, "room": room_id, "text": text}
        tp = self.transcript_path(workspace_id)
        tp.parent.mkdir(parents=True, exist_ok=True)
        with tp.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def load_index(self) -> Dict[str, Any]:
        idx = _read_json(self.index_path, {"workspaces": []})
        if "workspaces" not in idx or not isinstance(idx["workspaces"], list):
            idx = {"workspaces": []}
        return idx

    def save_index(self, index: Dict[str, Any]) -> None:
        _write_json(self.index_path, index)

    def register_workspace(self, workspace_id: str, label: str) -> None:
        idx = self.load_index()
        rows = idx["workspaces"]
        for row in rows:
            if row.get("workspace_id") == workspace_id:
                row["label"] = label
                row["last_seen_utc"] = utc_now()
                self.save_index(idx)
                return
        rows.append(
            {
                "workspace_id": workspace_id,
                "label": label,
                "created_utc": utc_now(),
                "last_seen_utc": utc_now(),
                "last_room": "lobby",
            }
        )
        self.save_index(idx)

    def touch_workspace(self, workspace_id: str, room_id: Optional[str] = None) -> None:
        idx = self.load_index()
        changed = False
        for row in idx["workspaces"]:
            if row.get("workspace_id") == workspace_id:
                row["last_seen_utc"] = utc_now()
                if room_id:
                    row["last_room"] = room_id
                changed = True
                break
        if changed:
            self.save_index(idx)


store = WorkspaceStore(WORKSPACES_DIR)
pipeline = RequestPipeline(store=store, navigator_control=NAVIGATOR_CONTROL, utc_now_fn=utc_now)


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


def memo_store_for(workspace_id: str) -> MemoStore:
    if workspace_id == "default_workspace" and LEGACY_MEMOS_DIR.exists():
        return MemoStore(LEGACY_MEMOS_DIR)
    return MemoStore(store.memos_dir(workspace_id))


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


app = FastAPI(title="Veridex Office Server", version="1.1.7")


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
    return {"ok": True, "ts": utc_now()}


@app.get("/tools")
def tools() -> Dict[str, Any]:
    return {
        "tools": [
            "office.bootstrap",
            "office.state_get",
            "office.room_set",
            "office.workspaces_list",
            "office.workspace_new",
            "office.nancy_route",
            "mailroom.dispatch",
            "office.memos_list",
            "office.memo_get",
        ],
        "version": "1.1.7",
    }


@app.post("/call")
def call_tool(call: ToolCall) -> Dict[str, Any]:
    tool = call.tool.strip()
    args = dict(call.arguments or {})
    workspace_id = resolve_workspace_id(tool, args)
    if workspace_id:
        args["workspace_id"] = workspace_id

    if tool == "office.workspaces_list":
        return handle_workspaces_list(args)
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

    raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}")


def handle_workspaces_list(args: Dict[str, Any]) -> Dict[str, Any]:
    idx = store.load_index()
    return {
        "structuredContent": idx,
        "content": [{"type": "text", "text": f"Found {len(idx.get('workspaces', []))} workspace(s)."}],
    }


def handle_workspace_new(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
    label = str(args.get("label") or f"Workspace {utc_now()}")
    store.register_workspace(workspace_id, label)

    state = build_workspace_state(workspace_id)
    store.save_state(workspace_id, state)
    store.append_transcript(workspace_id, "system", "lobby", f"Workspace created: {label}")

    return {
        "structuredContent": {"workspace_id": workspace_id, "label": label},
        "content": [{"type": "text", "text": f"Created workspace {workspace_id}."}],
    }


def handle_office_bootstrap(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    state = store.load_state(workspace_id)

    if not state:
        state = build_workspace_state(workspace_id)
        store.save_state(workspace_id, state)
        store.register_workspace(workspace_id, workspace_id)
        store.append_transcript(workspace_id, "system", "lobby", "Initialized workspace in Lobby.")

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
    else:
        if not state.get("active_room"):
            state["active_room"] = "lobby"
        if not state.get("active_persona"):
            state["active_persona"] = default_persona_for_external_room(state["active_room"])
        store.save_state(workspace_id, state)
        store.touch_workspace(workspace_id, state.get("active_room", "lobby"))

    return pipeline.snapshot_response(workspace_id)


def handle_office_state_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    return pipeline.snapshot_response(workspace_id)


def handle_office_room_set(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    room_id = str(args.get("room_id", "")).strip()
    if not room_id:
        raise HTTPException(status_code=400, detail="Missing required field: room_id")

    result = pipeline.enter_room(workspace_id, room_id)
    state = store.load_state(workspace_id)

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
        raise HTTPException(status_code=400, detail="request is required")
    return pipeline.nancy_route_response(workspace_id, request_text)


def handle_mailroom_dispatch(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    for field in ("to_room", "body"):
        if field not in args:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    to_room_raw = str(args["to_room"])
    ensure_single_target(to_room_raw)
    if "," in to_room_raw or " and " in to_room_raw.lower() or "&" in to_room_raw:
        raise HTTPException(status_code=400, detail="One memo may target only one room. Send separate memos.")

    to_room_external = normalize_external_room(to_room_raw)
    dest_room = validate_room(to_room_external)
    body = str(args["body"]).strip()
    explicit_persona = str(args.get("explicit_persona", "")).strip() or None

    state = store.load_state(workspace_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workspace not initialized: {workspace_id}")

    from_room_external = state.get("active_room", "lobby")
    pipeline.assert_mailroom_allowed(from_room_external, to_room_external)

    subject = generate_subject(body)
    memo_id = str(uuid.uuid4())
    to_persona = explicit_persona or str(dest_room.get("default_persona") or "Navigator")

    memo = Memo(
        memo_id=memo_id,
        from_room=from_room_external,
        to_room=to_room_external,
        to_persona=to_persona,
        subject=subject,
        body=body,
        created_utc=utc_now(),
        thread_id=None,
    )
    memo_store_for(workspace_id).append(memo)

    store.append_transcript(workspace_id, "system", from_room_external, f"Memo dispatched to {to_room_external}: {subject}")

    append_incident(
        severity="LOW",
        clazz="MEMO_DISPATCH",
        rule_or_gate="Mailroom Dispatch Contract v1.1.0",
        command="mailroom.dispatch",
        input_ref=json.dumps({
            "workspace_id": workspace_id,
            "from_room": from_room_external,
            "to_room": to_room_external,
            "memo_id": memo_id
        }),
        output_ref="(tool_response)",
        evidence_path=str(store.memos_dir(workspace_id)),
        notes="Recorded memo dispatch (single-target).",
        state_sha256=stable_state_sha(state),
    )

    return pipeline.mailroom_response(
        workspace_id=workspace_id,
        memo_id=memo_id,
        from_room=from_room_external,
        to_room=to_room_external,
        to_persona=to_persona,
        subject=subject,
        dest_room_title=dest_room["title"],
    )


def handle_memos_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    limit = int(args.get("limit", 25))
    limit = max(1, min(limit, 200))

    mstore = memo_store_for(workspace_id)
    memos_dir = getattr(mstore, "dir", None) or store.memos_dir(workspace_id)
    files = sorted(Path(memos_dir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

    rows: List[Dict[str, Any]] = []
    for p in files:
        obj = _read_json(p, {})
        rows.append(
            {
                "memo_id": obj.get("memo_id"),
                "created_utc": obj.get("created_utc"),
                "from_room": obj.get("from_room"),
                "to_room": obj.get("to_room"),
                "to_persona": obj.get("to_persona"),
                "subject": obj.get("subject"),
            }
        )

    return {
        "structuredContent": {"workspace_id": workspace_id, "count": len(rows), "memos": rows},
        "content": [{"type": "text", "text": f"Found {len(rows)} memo(s)."}],
    }


def handle_memo_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    memo_id = str(args.get("memo_id", "")).strip()
    if not memo_id:
        raise HTTPException(status_code=400, detail="memo_id is required")

    mstore = memo_store_for(workspace_id)
    memos_dir = getattr(mstore, "dir", None) or store.memos_dir(workspace_id)
    path = Path(memos_dir) / f"{memo_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Memo not found: {memo_id}")

    obj = _read_json(path, {})
    body = obj.get("body", "")
    return {
        "structuredContent": obj,
        "content": [
            {
                "type": "text",
                "text": (
                    f"Memo {obj.get('memo_id')}\n"
                    f"From: {obj.get('from_room')}\n"
                    f"To: {obj.get('to_room')} ({obj.get('to_persona')})\n"
                    f"Subject: {obj.get('subject')}\n\n"
                    f"{body}"
                ),
            }
        ],
    }
