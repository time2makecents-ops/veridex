# office_app/server/app.py
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

# -----------------------------
# Paths (file-backed substrate)
# -----------------------------
SERVER_DIR = Path(__file__).resolve().parent            # .../office_app/server
PKG_DIR = SERVER_DIR.parent                             # .../office_app
APP_DIR = PKG_DIR.parent                                # .../Office-App

BACKEND_DIR = APP_DIR / "backend"                       # .../Office-App/backend
RUNTIME_DIR = PKG_DIR / "runtime"                       # .../Office-App/office_app/runtime
MEMOS_DIR = RUNTIME_DIR / "memos"

STATE_PATH = BACKEND_DIR / "state.json"
INCIDENT_LOG_PATH = BACKEND_DIR / "incident_log.csv"

# Optional: present but not required by this wrapper
REGISTRY_CSV_PATH = BACKEND_DIR / "registry.csv"
GOV_REGISTRY_JSON_PATH = BACKEND_DIR / "master_governance_registry_v1_0_0.json"

memo_store = MemoStore(MEMOS_DIR)

# -----------------------------
# Room registry (V1)
# -----------------------------
# External room ids (what tools accept)
ROOMS: List[Dict[str, Any]] = [
    {"id": "lobby", "title": "Lobby", "default_persona": "Receptionist", "is_active": True},
    {"id": "conference_room", "title": "Conference Room", "default_persona": "Facilitator", "is_active": True},
    {"id": "control_room", "title": "Control Room", "default_persona": "Navigator", "is_active": True},
    {"id": "infrastructure_room", "title": "Infrastructure Room", "default_persona": "Infrastructure Manager", "is_active": True},
    {"id": "sales_department", "title": "Sales Department", "default_persona": "Sales Director", "is_active": True},
    {"id": "marketing_room", "title": "Marketing & Advertising", "default_persona": "Marketing Director", "is_active": True},
    {"id": "hr_department", "title": "HR Department", "default_persona": "HR Manager", "is_active": True},
    {"id": "it_department", "title": "IT Department", "default_persona": "IT Administrator", "is_active": True},
    {"id": "art_department", "title": "Art Department", "default_persona": "Creative Director", "is_active": True},
    {"id": "law_office", "title": "Law Office", "default_persona": "Legal Counsel", "is_active": True},
    {"id": "finance_department", "title": "Finance Department", "default_persona": "Finance Director", "is_active": True},
    {"id": "my_office", "title": "My Office", "default_persona": "Nancy", "is_active": True},
    {"id": "vr_room", "title": "VR Room", "default_persona": "Simulation Guide", "is_active": True},
    {"id": "records_archive", "title": "Records Archive", "default_persona": "Archivist", "is_active": True},
    {"id": "rnd_room", "title": "Research & Development (R&D)", "default_persona": "R&D Director", "is_active": True},
    {"id": "security_room", "title": "Security Room", "default_persona": "Security Chief", "is_active": True},
    {"id": "break_room", "title": "Break Room", "default_persona": "Break Room Host", "is_active": True},
]

ROOM_INDEX = {r["id"]: r for r in ROOMS}

# Internal room ids (what state.json stores)
EXTERNAL_TO_INTERNAL_ROOM: Dict[str, str] = {
    "lobby": "LOBBY",
    "conference_room": "CONFERENCE_ROOM",
    "control_room": "CONTROL_ROOM",
    "infrastructure_room": "INFRASTRUCTURE_ROOM",
    "sales_department": "SALES_DEPARTMENT",
    "marketing_room": "MARKETING_ROOM",
    "hr_department": "HR_DEPARTMENT",
    "it_department": "IT_DEPARTMENT",
    "art_department": "ART_DEPARTMENT",
    "law_office": "LAW_OFFICE",
    "finance_department": "FINANCE_DEPARTMENT",
    "my_office": "MY_OFFICE",
    "vr_room": "VR_ROOM",
    "records_archive": "RECORDS_ARCHIVE",
    "rnd_room": "RND_ROOM",
    "security_room": "SECURITY_ROOM",
    "break_room": "BREAK_ROOM",
}
INTERNAL_TO_EXTERNAL_ROOM = {v: k for k, v in EXTERNAL_TO_INTERNAL_ROOM.items()}

# -----------------------------
# Navigator control layer
# -----------------------------
NAVIGATOR_CONTROL = {
    "id": "NAVIGATOR",
    "status": "ACTIVE",
    "visibility": "INVISIBLE",
}

# -----------------------------
# Helpers
# -----------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_state_sha(state: Dict[str, Any]) -> str:
    import hashlib
    b = json.dumps(state, sort_keys=True).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def normalize_external_room(room_id: str) -> str:
    rid = room_id.strip().lower()
    rid = rid.replace(" ", "_")
    return rid


def validate_room(room_id_external: str) -> Dict[str, Any]:
    rid = normalize_external_room(room_id_external)
    room = ROOM_INDEX.get(rid)
    if not room or not room.get("is_active", False):
        valid = [r["id"] for r in ROOMS if r.get("is_active", False)]
        raise HTTPException(status_code=400, detail=f"Room not recognized. Valid rooms: {valid}")
    return room


def internal_room_from_external(room_id_external: str) -> str:
    rid = normalize_external_room(room_id_external)
    internal = EXTERNAL_TO_INTERNAL_ROOM.get(rid)
    if not internal:
        raise HTTPException(status_code=400, detail=f"Room not recognized: {room_id_external}")
    return internal


def external_room_from_internal(room_id_internal: str) -> str:
    return INTERNAL_TO_EXTERNAL_ROOM.get(room_id_internal, "lobby")


def default_persona_for_external_room(room_id_external: str) -> str:
    room = validate_room(room_id_external)
    return str(room.get("default_persona") or "Navigator")


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


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: Dict[str, Any]) -> None:
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def reject_multi_target(to_room: str) -> None:
    # V1: single target only.
    s = to_room.strip()
    if "," in s or " and " in s.lower() or "&" in s:
        raise HTTPException(status_code=400, detail="One memo may target only one room. Send separate memos.")


def _memo_dir() -> Path:
    MEMOS_DIR.mkdir(parents=True, exist_ok=True)
    return MEMOS_DIR


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# -----------------------------
# Pydantic models (tool calls)
# -----------------------------
class ToolCall(BaseModel):
    tool: str = Field(..., description="Tool name, e.g., 'office.bootstrap'")
    arguments: Dict[str, Any] = Field(default_factory=dict)


# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="Office App MCP Wrapper (V1)", version="1.0.0")


@app.on_event("startup")
def _startup_init() -> None:
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    MEMOS_DIR.mkdir(parents=True, exist_ok=True)
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
            "mailroom.dispatch",
            "office.memos_list",
            "office.memo_get",
        ],
        "version": "1.0.0",
    }


@app.post("/call")
def call_tool(call: ToolCall) -> Dict[str, Any]:
    tool = call.tool.strip()

    if tool == "office.bootstrap":
        return handle_office_bootstrap(call.arguments)

    if tool == "office.state_get":
        return handle_office_state_get(call.arguments)

    if tool == "office.room_set":
        return handle_office_room_set(call.arguments)

    if tool == "mailroom.dispatch":
        return handle_mailroom_dispatch(call.arguments)

    if tool == "office.memos_list":
        return handle_memos_list(call.arguments)

    if tool == "office.memo_get":
        return handle_memo_get(call.arguments)

    raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}")


# -----------------------------
# Tool handlers
# -----------------------------
def handle_office_bootstrap(args: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()

    if not state:
        # Cold-start: lobby + lobby default persona (Receptionist)
        lobby_external = "lobby"
        state = {
            "schema_version": "1.0.0",
            "active_room": EXTERNAL_TO_INTERNAL_ROOM[lobby_external],
            "active_persona": default_persona_for_external_room(lobby_external),
            "active_mode": "STANDARD",
            "scope_lock": {"enabled": True, "max_rooms": 1},
            "engaged": {"CRE": False},
            "gates": {"SAVE_GATE": True, "PREFLIGHT": True, "VERIFICATION": True},
            "registry": {"path": str((BACKEND_DIR / "master_governance_registry_v1_0_0.csv").resolve()), "sha256": ""},
        }
        save_state(state)

        sid = stable_state_sha(state)
        append_incident(
            severity="LOW",
            clazz="BOOTSTRAP",
            rule_or_gate="",
            command="office.bootstrap",
            input_ref="{}",
            output_ref="state.json",
            evidence_path=str(STATE_PATH),
            notes="Initialized state.json (default lobby + receptionist).",
            state_sha256=sid,
        )
    else:
        # Normalize active room if it doesn't map
        internal = state.get("active_room", EXTERNAL_TO_INTERNAL_ROOM["lobby"])
        if internal not in INTERNAL_TO_EXTERNAL_ROOM:
            state["active_room"] = EXTERNAL_TO_INTERNAL_ROOM["lobby"]
        # Ensure persona exists; if missing, derive from room
        if not state.get("active_persona"):
            active_external = external_room_from_internal(state["active_room"])
            state["active_persona"] = default_persona_for_external_room(active_external)
        save_state(state)

    return _state_snapshot_response(load_state())


def handle_office_state_get(args: Dict[str, Any]) -> Dict[str, Any]:
    return _state_snapshot_response(load_state())


def handle_office_room_set(args: Dict[str, Any]) -> Dict[str, Any]:
    if "room_id" not in args:
        raise HTTPException(status_code=400, detail="Missing required field: room_id")

    target_external = normalize_external_room(str(args["room_id"]))
    validate_room(target_external)  # raises if invalid
    target_internal = internal_room_from_external(target_external)

    state = load_state()
    prev_internal = state.get("active_room", EXTERNAL_TO_INTERNAL_ROOM["lobby"])
    prev_external = external_room_from_internal(prev_internal)

    state["active_room"] = target_internal
    # Auto-derive persona from room to prevent drift
    state["active_persona"] = default_persona_for_external_room(target_external)
    save_state(state)

    sid = stable_state_sha(state)
    append_incident(
        severity="LOW",
        clazz="STATE_CHANGE",
        rule_or_gate="Room State Model v1.0.0",
        command="office.room_set",
        input_ref=json.dumps({"room_id": target_external}),
        output_ref="state.json",
        evidence_path=str(STATE_PATH),
        notes=f"active_room: {prev_external} -> {target_external}",
        state_sha256=sid,
    )

    room = ROOM_INDEX[target_external]
    return {
        "structuredContent": {
            "workspace_id": "default_workspace",
            "previous_room": prev_external,
            "active_room": target_external,
            "active_persona": state["active_persona"],
            "navigator": NAVIGATOR_CONTROL,
            "rooms": _rooms_payload(),
        },
        "content": [{"type": "text", "text": f"Active room set to {room['title']}."}],
    }


def handle_mailroom_dispatch(args: Dict[str, Any]) -> Dict[str, Any]:
    for field in ("to_room", "body"):
        if field not in args:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    to_room_raw = str(args["to_room"])
    ensure_single_target(to_room_raw)
    reject_multi_target(to_room_raw)

    to_room_external = normalize_external_room(to_room_raw)
    dest_room = validate_room(to_room_external)

    body = str(args["body"]).strip()
    explicit_persona = str(args.get("explicit_persona", "")).strip() or None

    state = load_state()
    from_internal = state.get("active_room", EXTERNAL_TO_INTERNAL_ROOM["lobby"])
    from_room_external = external_room_from_internal(from_internal)

    subject = generate_subject(body)
    memo_id = str(uuid.uuid4())

    to_persona = explicit_persona or str(dest_room.get("default_persona") or "Navigator")

    header = f"Memo filed to: {to_persona} ({dest_room['title']})\nSubject: {subject}\n"

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

    memo_store.append(memo)

    sid = stable_state_sha(state)
    append_incident(
        severity="LOW",
        clazz="MEMO_DISPATCH",
        rule_or_gate="Mailroom Dispatch Contract v1.0.0",
        command="mailroom.dispatch",
        input_ref=json.dumps({"from_room": from_room_external, "to_room": to_room_external, "memo_id": memo_id}),
        output_ref="(tool_response)",
        evidence_path=str(MEMOS_DIR),
        notes="Recorded memo dispatch (single-target).",
        state_sha256=sid,
    )

    return {
        "structuredContent": {
            "memo_id": memo_id,
            "from_room": from_room_external,
            "to_room": to_room_external,
            "to_persona": to_persona,
            "subject": subject,
            "is_refusal": False,
            "closure_appended": False,
            "response_text": header,
        },
        "content": [{"type": "text", "text": header}],
    }


def handle_memos_list(args: Dict[str, Any]) -> Dict[str, Any]:
    limit = int(args.get("limit", 25))
    limit = max(1, min(limit, 200))

    files = sorted(_memo_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

    rows: List[Dict[str, Any]] = []
    for p in files:
        obj = _read_json(p)
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
        "structuredContent": {"count": len(rows), "memos": rows},
        "content": [{"type": "text", "text": f"Found {len(rows)} memo(s)."}],
    }


def handle_memo_get(args: Dict[str, Any]) -> Dict[str, Any]:
    memo_id = str(args.get("memo_id", "")).strip()
    if not memo_id:
        raise HTTPException(status_code=400, detail="memo_id is required")

    path = _memo_dir() / f"{memo_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Memo not found: {memo_id}")

    obj = _read_json(path)
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


# -----------------------------
# Response helpers
# -----------------------------
def _rooms_payload() -> List[Dict[str, Any]]:
    return [
        {"id": r["id"], "title": r["title"], "default_persona": r["default_persona"], "is_active": bool(r["is_active"])}
        for r in ROOMS
    ]


def _state_snapshot_response(state: Dict[str, Any]) -> Dict[str, Any]:
    internal = state.get("active_room", EXTERNAL_TO_INTERNAL_ROOM["lobby"])
    active_external = external_room_from_internal(internal)
    active_persona = state.get("active_persona")

    return {
        "structuredContent": {
            "workspace_id": "default_workspace",
            "active_room": active_external,
            "active_persona": active_persona,
            "navigator": NAVIGATOR_CONTROL,
            "rooms": _rooms_payload(),
            "timestamp_utc": utc_now(),
        },
        "content": [{"type": "text", "text": f"Active room: {active_external}"}],
    }
