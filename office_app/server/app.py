from __future__ import annotations

import csv
import base64
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from office_app.server.archive_service import ArchiveService
from office_app.server.command_router import CommandRouter
from office_app.server.errors import error_missing_required_field
from office_app.server.guards import ensure_single_target
from office_app.server.model_router import ModelRouter, ModelRoutingError
from office_app.server.receptionist_context_service import ReceptionistContextService
from office_app.server.memo_service import MemoService
from office_app.server.nancy_service import NancyService
from office_app.server.ocr_service import OcrService
from office_app.server.request_pipeline import RequestPipeline
from office_app.server.search_service import SearchService
from office_app.server.handlers.ai_handlers import build_ai_handlers
from office_app.server.handlers.artifact_handlers import build_artifact_handlers
from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.file_handlers import build_file_handlers
from office_app.server.handlers.memo_handlers import build_memo_handlers
from office_app.server.handlers.workspace_handlers import build_workspace_handlers
from office_app.server.tool_context import ToolContext
from office_app.server.tool_definitions import VERIDEX_TOOL_DEFINITIONS, ToolDefinition
from office_app.server.user_service import UserService
from office_app.server.tools_registry import register_tools
from office_app.server.workspace_file_service import PrivateFileService, WorkspaceFileService
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
user_service = UserService(kernel=kernel, runtime_dir=RUNTIME_DIR, utc_now_fn=utc_now)
receptionist_context_service = ReceptionistContextService(kernel=kernel, runtime_dir=RUNTIME_DIR, utc_now_fn=utc_now)
workspace_file_service = WorkspaceFileService(kernel=kernel, runtime_dir=RUNTIME_DIR, utc_now_fn=utc_now)
private_file_service = PrivateFileService(kernel=kernel, runtime_dir=RUNTIME_DIR, utc_now_fn=utc_now)
search_service = SearchService()
ocr_service = OcrService()
model_router = ModelRouter.from_env()
nancy_service = NancyService(
    kernel=kernel,
    archive_service=archive_service,
    store=store,
    utc_now_fn=utc_now,
)


def build_tool_context(tool_name: str, args: Dict[str, Any], definition: ToolDefinition) -> ToolContext:
    workspace_id = str(args.get("workspace_id") or "").strip()
    session_id = str(args.get("session_id") or "").strip() or None
    user_id: Optional[str] = None
    if session_id:
        try:
            user = user_service.get_user_for_session(session_id)
            user_id = str(user.get("user_id") or "").strip() or None
        except HTTPException:
            user_id = None

    active_room: Optional[str] = None
    active_persona: Optional[str] = None
    if workspace_id:
        try:
            state = kernel.get_state(workspace_id)
            active_room = str(state.get("active_room") or "").strip() or None
            active_persona = str(state.get("active_persona") or "").strip() or None
        except HTTPException:
            active_room = None
            active_persona = None

    return ToolContext(
        tool_name=tool_name,
        capability=definition.capability,
        workspace_id=workspace_id,
        session_id=session_id,
        user_id=user_id,
        active_room=active_room,
        active_persona=active_persona,
        arguments=dict(args),
    )


router = CommandRouter(context_provider=build_tool_context)
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
    session_id = str(args.get("session_id", "")).strip()
    if session_id:
        session = user_service.get_session(session_id)
        resolved = str(session.get("active_workspace_id") or "").strip()
        if resolved:
            return resolved
        raise HTTPException(status_code=409, detail="Session is missing an active workspace.")
    if tool in WORKSPACE_TOOLS_NO_ID:
        return workspace_id
    if workspace_id:
        return workspace_id
    definition = VERIDEX_TOOL_DEFINITIONS.get(tool)
    if definition is not None and definition.requires_workspace:
        raise HTTPException(status_code=400, detail="Workspace ID required")
    return workspace_id


class ToolCall(BaseModel):
    tool: str = Field(..., description="Tool name, e.g. office.bootstrap")
    arguments: Dict[str, Any] = Field(default_factory=dict)


class NaturalLanguageRequest(BaseModel):
    text: str = Field(..., description="Plain text request to route")
    workspace_id: Optional[str] = Field(default=None, description="Optional workspace id")
    session_id: Optional[str] = Field(default=None, description="Optional session id")


class LobbyOnboardRequest(BaseModel):
    name: str = Field(..., description="User name")
    pin_code: str = Field(..., description="4-digit PIN code")
    display_name: Optional[str] = Field(default=None, description="Optional display name")
    face_photo_data: Optional[str] = Field(default=None, description="Optional face photo data URL")


class LobbyEnterRequest(BaseModel):
    pin_code: str = Field(..., description="4-digit PIN code")


class FileUploadRequest(BaseModel):
    name: str = Field(..., description="Original file name")
    content_text: Optional[str] = Field(default=None, description="Text content to upload")
    content_base64: Optional[str] = Field(default=None, description="Base64-encoded file content")
    data_url: Optional[str] = Field(default=None, description="Data URL content")
    mime_type: Optional[str] = Field(default=None, description="Optional mime type")
    kind: str = Field(default="generic", description="File kind")
    scope: str = Field(default="workspace", description="File scope: room, session, public, private")
    scope_ref: Optional[str] = Field(default=None, description="Scope reference, such as room id or session id")
    description: Optional[str] = Field(default=None, description="Optional description")
    workspace_id: Optional[str] = Field(default=None, description="Optional workspace id")
    session_id: Optional[str] = Field(default=None, description="Optional session id")
    uploaded_by_user_id: Optional[str] = Field(default=None, description="Optional uploader user id")


class FileLookupRequest(BaseModel):
    workspace_id: Optional[str] = Field(default=None, description="Optional workspace id")
    session_id: Optional[str] = Field(default=None, description="Optional session id")
    file_id: Optional[str] = Field(default=None, description="Optional file id")


class ReceptionistContextUpdateRequest(BaseModel):
    workspace_id: Optional[str] = Field(default=None, description="Optional workspace id")
    session_id: Optional[str] = Field(default=None, description="Optional session id")
    room_directory: Optional[list[dict[str, Any]]] = None
    persona_directory: Optional[list[dict[str, Any]]] = None
    receptionist_script: Optional[dict[str, Any]] = None
    policy_summary: Optional[dict[str, Any]] = None
    known_user_profile: Optional[dict[str, Any]] = None
    session_summary_text: Optional[str] = None
    recent_turns: Optional[list[dict[str, Any]]] = None
    current_prompt_state: Optional[dict[str, Any]] = None


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


def _workspace_label(workspace_id: str) -> str:
    idx = kernel.list_workspaces()
    for row in idx.get("workspaces", []):
        if row.get("workspace_id") == workspace_id:
            return str(row.get("label") or workspace_id)
    return workspace_id


def _request_text_from_response(response: Dict[str, Any]) -> str:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("response_text", "text", "message"):
            value = structured.get(key)
            if isinstance(value, str) and value.strip():
                return value
    content = response.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    return ""


def _session_user_profile(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    try:
        return user_service.get_user_for_session(session_id)
    except HTTPException:
        return None


def attach_request_context(response: Dict[str, Any], *, workspace_id: str, session_id: str) -> Dict[str, Any]:
    enriched = dict(response)
    structured = enriched.get("structuredContent")
    if isinstance(structured, dict):
        structured = dict(structured)
        structured["workspace_id"] = workspace_id
        structured["session_id"] = session_id
        enriched["structuredContent"] = structured
    else:
        enriched["structuredContent"] = {
            "workspace_id": workspace_id,
            "session_id": session_id,
        }
    enriched["workspace_id"] = workspace_id
    enriched["session_id"] = session_id
    return enriched


def _resolve_http_workspace_id(workspace_id: Optional[str], session_id: Optional[str]) -> str:
    workspace = str(workspace_id or "").strip()
    session = str(session_id or "").strip()
    if session:
        resolved = user_service.resolve_workspace_for_session(session)
        if not resolved:
            raise HTTPException(status_code=401, detail="Invalid session")
        return resolved
    if workspace:
        return workspace
    raise HTTPException(status_code=400, detail="Workspace ID required")


@app.post("/request")
def handle_natural_language_request(
    payload: NaturalLanguageRequest,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
) -> Dict[str, Any]:
    header_session_id = x_session_id if isinstance(x_session_id, str) else None
    session_id = str(header_session_id or payload.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID required")
    workspace_id = str(user_service.resolve_workspace_for_session(session_id) or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    request_text = str(payload.text or "").strip()
    ensure_artifact_workspace(workspace_id)
    user_profile = _session_user_profile(session_id)
    current_state = kernel.get_state(workspace_id)
    pending_navigation = _pending_room_navigation(current_state)
    if pending_navigation and request_text:
        if _is_confirmation_yes(request_text):
            current_state.pop("pending_room_navigation", None)
            store.save_state(workspace_id, current_state)
            target_room = str(pending_navigation.get("room_id") or "").strip()
            if not target_room:
                raise HTTPException(status_code=400, detail="Pending room navigation target missing.")
            result = router.dispatch_capability(
                "room.navigate",
                {
                    "workspace_id": workspace_id,
                    "room_id": target_room,
                    "session_id": session_id,
                },
                preferred_tool="office.room_set",
            )
            structured_result = result.get("structuredContent") if isinstance(result, dict) else None
            receptionist_context_service.record_turn(
                workspace_id=workspace_id,
                role="assistant",
                text=_request_text_from_response(result),
                room_id=str((structured_result or {}).get("active_room") or target_room),
                persona_name=str((structured_result or {}).get("active_persona") or ""),
                user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
                session_id=session_id,
            )
            store.append_transcript(
                workspace_id,
                "assistant",
                str((structured_result or {}).get("active_room") or target_room),
                _request_text_from_response(result),
                speaker="System",
            )
            response = result
            if isinstance(response, dict):
                structured = response.get("structuredContent")
                if isinstance(structured, dict):
                    structured["routing"] = {
                        "route_kind": "nancy",
                        "capability": "room.navigate",
                        "tool": "office.room_set",
                        "reason": "Confirmed pending room navigation.",
                        "auto_routed": True,
                    }
            return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

        if _is_confirmation_no(request_text):
            current_state.pop("pending_room_navigation", None)
            store.save_state(workspace_id, current_state)
            response_text = f"Okay. Staying in {current_state.get('active_room', 'lobby')}."
            response = {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "response_text": response_text,
                    "routing": {
                        "route_kind": "model",
                        "capability": "ai.respond",
                        "tool": "office.ai_generate",
                        "reason": "Cleared pending room navigation on negative confirmation.",
                    },
                },
                "content": [{"type": "text", "text": response_text}],
            }
            receptionist_context_service.record_turn(
                workspace_id=workspace_id,
                role="assistant",
                text=response_text,
                room_id=str(current_state.get("active_room") or "lobby"),
                persona_name=str(current_state.get("active_persona") or "Receptionist"),
                user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
                session_id=session_id,
            )
            store.append_transcript(
                workspace_id,
                "assistant",
                str(current_state.get("active_room") or "lobby"),
                response_text,
                speaker=str(current_state.get("active_persona") or "Receptionist"),
            )
            return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

    routed = pipeline.route_user_request(workspace_id, request_text)

    should_record = routed["route_kind"] in {"model", "nancy", "tool"}
    if should_record:
        current_state = kernel.get_state(workspace_id)
        active_room_for_user = str(current_state.get("active_room") or "lobby")
        receptionist_context_service.record_turn(
            workspace_id=workspace_id,
            role="user",
            text=request_text,
            room_id=active_room_for_user,
            persona_name=current_state.get("active_persona", "Receptionist"),
            user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
            session_id=session_id,
        )
        store.append_transcript(
            workspace_id,
            "user",
            active_room_for_user,
            request_text,
            speaker="You",
        )

    if routed["route_kind"] == "artifact":
        args = dict(routed["arguments"])
        args["workspace_id"] = workspace_id
        if session_id:
            args["session_id"] = session_id
        result = router.dispatch_capability(
            routed["capability"],
            args,
            preferred_tool=routed.get("tool"),
        )
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "artifact",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                }
            return attach_request_context(result, workspace_id=workspace_id, session_id=session_id)

    if routed["route_kind"] == "tool":
        args = dict(routed["arguments"])
        args["workspace_id"] = workspace_id
        if session_id:
            args["session_id"] = session_id
        result = router.dispatch_capability(
            routed["capability"],
            args,
            preferred_tool=routed.get("tool"),
        )
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "tool",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                }
        enriched = attach_request_context(result, workspace_id=workspace_id, session_id=session_id)
        receptionist_context_service.record_turn(
            workspace_id=workspace_id,
            role="assistant",
            text=_request_text_from_response(enriched),
            room_id=kernel.get_state(workspace_id).get("active_room", "lobby"),
            persona_name=kernel.get_state(workspace_id).get("active_persona", "Receptionist"),
            user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
            session_id=session_id,
        )
        current_state = kernel.get_state(workspace_id)
        store.append_transcript(
            workspace_id,
            "assistant",
            str(current_state.get("active_room") or "lobby"),
            _request_text_from_response(enriched),
            speaker=str(current_state.get("active_persona") or "Receptionist"),
        )
        return enriched

    if routed["route_kind"] == "nancy":
        if routed.get("requires_confirmation"):
            current_state = kernel.get_state(workspace_id)
            current_state["pending_room_navigation"] = {
                "room_id": routed.get("room_id"),
                "room_title": routed.get("room_title"),
                "persona": routed.get("persona"),
                "request_text": request_text,
                "ts": utc_now(),
            }
            store.save_state(workspace_id, current_state)
            response_text = f"Did you want me to move you to {routed.get('room_title')} ({routed.get('persona')})?"
            response = {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "response_text": response_text,
                    "requires_confirmation": True,
                    "pending_room_navigation": current_state["pending_room_navigation"],
                    "routing": {
                        "route_kind": "nancy",
                        "capability": routed["capability"],
                        "tool": routed["tool"],
                        "reason": routed["reason"],
                        "auto_routed": False,
                    },
                },
                "content": [{"type": "text", "text": response_text}],
            }
            receptionist_context_service.record_turn(
                workspace_id=workspace_id,
                role="assistant",
                text=response_text,
                room_id=str(current_state.get("active_room") or "lobby"),
                persona_name=str(current_state.get("active_persona") or "Receptionist"),
                user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
                session_id=session_id,
            )
            store.append_transcript(
                workspace_id,
                "assistant",
                str(current_state.get("active_room") or "lobby"),
                response_text,
                speaker=str(current_state.get("active_persona") or "Receptionist"),
            )
            return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

        target_room = str(routed.get("room_id") or "").strip()
        if not target_room:
            raise HTTPException(status_code=400, detail="Room navigation target missing.")
        result = router.dispatch_capability(
            routed["capability"],
            {
                "workspace_id": workspace_id,
                "room_id": target_room,
                "session_id": session_id,
            },
            preferred_tool="office.room_set",
        )
        structured_result = result.get("structuredContent") if isinstance(result, dict) else None
        receptionist_context_service.record_turn(
            workspace_id=workspace_id,
            role="assistant",
            text=_request_text_from_response(result),
            room_id=str((structured_result or {}).get("active_room") or target_room),
            persona_name=str((structured_result or {}).get("active_persona") or ""),
            user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
            session_id=session_id,
        )
        store.append_transcript(
            workspace_id,
            "assistant",
            str((structured_result or {}).get("active_room") or target_room),
            _request_text_from_response(result),
            speaker="System",
        )
        response = result
        if isinstance(response, dict):
            structured = response.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "nancy",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                    "auto_routed": True,
                }
        return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

    if routed["route_kind"] == "model":
        args = dict(routed["arguments"])
        args["workspace_id"] = workspace_id
        args["session_id"] = session_id
        if user_profile:
            args["user_profile"] = user_profile
        result = router.dispatch_capability(
            routed["capability"],
            args,
            preferred_tool=routed.get("tool"),
        )
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "model",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                }
        enriched = attach_request_context(result, workspace_id=workspace_id, session_id=session_id)
        receptionist_context_service.record_turn(
            workspace_id=workspace_id,
            role="assistant",
            text=_request_text_from_response(enriched),
            room_id=kernel.get_state(workspace_id).get("active_room", "lobby"),
            persona_name=kernel.get_state(workspace_id).get("active_persona", "Receptionist"),
            user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
            session_id=session_id,
        )
        current_state = kernel.get_state(workspace_id)
        store.append_transcript(
            workspace_id,
            "assistant",
            str(current_state.get("active_room") or "lobby"),
            _request_text_from_response(enriched),
            speaker=str(current_state.get("active_persona") or "Receptionist"),
        )
        return enriched

    response = pipeline.nancy_route_response(workspace_id, request_text)
    receptionist_context_service.record_turn(
        workspace_id=workspace_id,
        role="assistant",
        text=_request_text_from_response(response),
        room_id=kernel.get_state(workspace_id).get("active_room", "lobby"),
        persona_name=kernel.get_state(workspace_id).get("active_persona", "Receptionist"),
        user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
        session_id=session_id,
    )
    current_state = kernel.get_state(workspace_id)
    store.append_transcript(
        workspace_id,
        "assistant",
        str(current_state.get("active_room") or "lobby"),
        _request_text_from_response(response),
        speaker=str(current_state.get("active_persona") or "Receptionist"),
    )
    return attach_request_context(
        response,
        workspace_id=workspace_id,
        session_id=session_id,
    )


@app.post("/lobby/onboard")
def lobby_onboard(payload: LobbyOnboardRequest) -> Dict[str, Any]:
    result = user_service.onboard_user(
        name=payload.name,
        pin_code=payload.pin_code,
        display_name=payload.display_name,
        face_photo_data=payload.face_photo_data,
    )
    return {
        "structuredContent": result,
        "content": [
            {
                "type": "text",
                "text": (
                    f"Onboarding complete for {result['user']['display_name']}.\n"
                    f"Workspace ready: {result['workspace_id']}.\n"
                    f"Session ready: {result['session_id']}."
                ),
            }
        ],
    }


@app.post("/lobby/enter")
def lobby_enter(payload: LobbyEnterRequest) -> Dict[str, Any]:
    result = user_service.enter_lobby(pin_code=payload.pin_code)
    user = result["user"]
    return {
        "structuredContent": result,
        "content": [
            {
                "type": "text",
                "text": (
                    f"Welcome back, {user['display_name']}.\n"
                    f"Restored workspace: {result['workspace_id']}.\n"
                    f"Session: {result['session_id']}."
                ),
            }
        ],
    }


@app.get("/receptionist/context")
def receptionist_context(
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    context = receptionist_context_service.get_context(resolved_workspace_id)
    return {
        "structuredContent": context,
        "content": [{"type": "text", "text": f"Loaded receptionist context for {resolved_workspace_id}."}],
    }


@app.post("/receptionist/context")
def receptionist_context_update(payload: ReceptionistContextUpdateRequest) -> Dict[str, Any]:
    resolved_workspace_id = _resolve_http_workspace_id(payload.workspace_id, payload.session_id)
    updates = {
        "room_directory": payload.room_directory,
        "persona_directory": payload.persona_directory,
        "receptionist_script": payload.receptionist_script,
        "policy_summary": payload.policy_summary,
        "known_user_profile": payload.known_user_profile,
        "session_summary_text": payload.session_summary_text,
        "recent_turns": payload.recent_turns,
        "current_prompt_state": payload.current_prompt_state,
    }
    context = receptionist_context_service.update_context(resolved_workspace_id, updates)
    return {
        "structuredContent": context,
        "content": [{"type": "text", "text": f"Updated receptionist context for {resolved_workspace_id}."}],
    }


@app.get("/files")
def list_files(
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
    scope_ref: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    selected_scope = str(scope or "workspace").strip().lower() or "workspace"
    service = private_file_service if selected_scope == "private" else workspace_file_service
    rows = service.list_files(resolved_workspace_id, scope=selected_scope if selected_scope != "workspace" else None, scope_ref=scope_ref)
    return {
        "structuredContent": {
            "workspace_id": resolved_workspace_id,
            "count": len(rows),
            "files": rows,
        },
        "content": [{"type": "text", "text": f"Found {len(rows)} file(s)."}],
    }


@app.post("/files/upload")
def upload_file(payload: FileUploadRequest) -> Dict[str, Any]:
    resolved_workspace_id = _resolve_http_workspace_id(payload.workspace_id, payload.session_id)
    scope = str(payload.scope or "workspace").strip().lower() or "workspace"
    service = private_file_service if scope == "private" else workspace_file_service
    record = service.upload_file(
        workspace_id=resolved_workspace_id,
        original_name=payload.name,
        content_text=payload.content_text,
        content_base64=payload.content_base64,
        data_url=payload.data_url,
        mime_type=payload.mime_type,
        kind=payload.kind,
        scope=scope,
        scope_ref=str(payload.scope_ref or "").strip() or scope,
        description=payload.description,
        uploaded_by_user_id=payload.uploaded_by_user_id,
        uploaded_by_session_id=payload.session_id,
    )
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": f"Uploaded file {record['original_name']} as {record['file_id']}."}],
    }


@app.get("/files/{file_id}")
def get_file_metadata(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    selected_scope = str(scope or "workspace").strip().lower() or "workspace"
    service = private_file_service if selected_scope == "private" else workspace_file_service
    record = service.get_file(resolved_workspace_id, file_id)
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": f"File {record['file_id']} - {record['original_name']}."}],
    }


@app.get("/files/{file_id}/download")
def download_file(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
):
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    selected_scope = str(scope or "workspace").strip().lower() or "workspace"
    service = private_file_service if selected_scope == "private" else workspace_file_service
    record, _ = service.file_bytes(resolved_workspace_id, file_id)
    return FileResponse(
        path=record["storage_path"],
        filename=record["original_name"],
        media_type=record["mime_type"] or "application/octet-stream",
    )


@app.get("/private-files/{file_id}")
def get_private_file_metadata(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    record = private_file_service.get_file(resolved_workspace_id, file_id)
    return {
        "structuredContent": record,
        "content": [{"type": "text", "text": f"Private file {record['file_id']} - {record['original_name']}."}],
    }


@app.get("/private-files/{file_id}/download")
def download_private_file(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    record, _ = private_file_service.file_bytes(resolved_workspace_id, file_id)
    return FileResponse(
        path=record["storage_path"],
        filename=record["original_name"],
        media_type=record["mime_type"] or "application/octet-stream",
    )


@app.post("/dev/reset-test-data")
def reset_test_data() -> Dict[str, Any]:
    import shutil

    with sqlite3.connect(user_service.db_path) as conn:
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM receptionist_contexts")
        conn.execute("DELETE FROM workspace_files")
        conn.commit()
    private_db = RUNTIME_DIR / "private_files.db"
    if private_db.exists():
        private_db.unlink()
    for path in [RUNTIME_DIR / "users", RUNTIME_DIR / "workspaces", RUNTIME_DIR / "private_files"]:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    (RUNTIME_DIR / "users").mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "workspaces").mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "private_files").mkdir(parents=True, exist_ok=True)
    return {"ok": True}


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


def handle_commands_list(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "structuredContent": pipeline.tools_response(),
        "content": [
            {
                "type": "text",
                "text": "Available Veridex commands: Start Veridex, Install Watchdog, Remove Watchdog.",
            }
        ],
    }


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


def handle_ai_generate(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = str(args.get("workspace_id", "")).strip()
    if not workspace_id:
        raise error_missing_required_field("workspace_id")

    try:
        state = kernel.get_state(workspace_id)
    except HTTPException:
        kernel.bootstrap_workspace(workspace_id)
        state = kernel.get_state(workspace_id)

    user_prompt = str(args.get("user_prompt") or args.get("request") or args.get("text") or "").strip()
    if not user_prompt:
        raise error_missing_required_field("user_prompt")

    system_prompt = str(args.get("system_prompt") or "").strip()
    if not system_prompt:
        system_prompt = (
            f"You are Veridex. The active workspace is {workspace_id}. "
            f"The active room is {state.get('active_room', 'lobby')}. "
            f"The active persona is {state.get('active_persona', 'Receptionist')}. "
            "If the user asks about uploading or downloading files or images, answer with the Veridex file workflow and do not redirect them to IT unless they explicitly ask for troubleshooting. "
            "Never expose raw JSON, internal tool names, hidden schemas, or backend metadata in your response. "
            "Respond clearly, concisely, and stay within Veridex governance."
        )

    context = args.get("context")
    if not isinstance(context, dict):
        context = {
            "workspace_id": workspace_id,
            "active_room": state.get("active_room", "lobby"),
            "active_persona": state.get("active_persona", "Receptionist"),
        }
    receptionist_context = receptionist_context_service.build_model_context(
        workspace_id=workspace_id,
        user_profile=args.get("user_profile") if isinstance(args.get("user_profile"), dict) else None,
        session_id=str(args.get("session_id") or "").strip() or None,
    )
    if isinstance(args.get("user_profile"), dict):
        receptionist_context_service.update_context(
            workspace_id,
            {"known_user_profile": args.get("user_profile")},
        )
    context = {
        **context,
        "receptionist_context": receptionist_context,
        "room_directory_text": receptionist_context.get("room_directory_text", ""),
        "known_user_profile_text": receptionist_context.get("known_user_profile_text", ""),
        "session_summary_text": receptionist_context.get("session_summary_text", ""),
        "recent_turns_text": receptionist_context.get("recent_turns_text", []),
        "prompt_state_text": receptionist_context.get("prompt_state_text", ""),
        "behavior_rules": receptionist_context.get("behavior_rules", []),
    }

    settings = args.get("settings")
    if not isinstance(settings, dict):
        settings = {}

    task_type = str(args.get("task_type") or "conversation").strip() or "conversation"

    try:
        result = model_router.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context=context,
            settings=settings,
            task_type=task_type,
        )
    except ModelRoutingError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "attempts": exc.attempts,
                "workspace_id": workspace_id,
                "task_type": task_type,
            },
        ) from exc

    structured = {
        "workspace_id": workspace_id,
        "provider": result.provider,
        "model": result.model,
        "task_type": result.task_type,
        "fallback_used": result.fallback_used,
        "attempts": result.attempts,
        "response_text": result.text,
    }
    return {
        "structuredContent": structured,
        "content": [{"type": "text", "text": result.text}],
    }


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


def _is_confirmation_yes(text: str) -> bool:
    return _parse_bool(text, default=False)


def _is_confirmation_no(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return normalized in {"0", "false", "no", "n", "off"}


def _pending_room_navigation(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pending = state.get("pending_room_navigation")
    return pending if isinstance(pending, dict) else None


def _normalize_artifact_scope(args: Dict[str, Any], workspace_id: str) -> str:
    scope = str(args.get("retrieval_scope") or args.get("scope") or "workspace").strip().lower()
    scope = scope.replace("-", "_")
    if scope in {"global", "archive", "archive_global", "all", "all_project", "all_projects"}:
        return "archive_global"

    state = kernel.get_state(workspace_id)
    active_room = str(state.get("active_room") or "").strip().lower()
    if active_room == "records_archive":
        return "archive_global"
    return "workspace"


def _artifact_workspace_ids(workspace_id: str) -> list[str]:
    idx = kernel.list_workspaces()
    workspace_ids: list[str] = []
    for row in idx.get("workspaces", []):
        candidate = str(row.get("workspace_id") or "").strip()
        if candidate and candidate not in workspace_ids:
            workspace_ids.append(candidate)
    if workspace_id and workspace_id not in workspace_ids:
        workspace_ids.insert(0, workspace_id)
    return workspace_ids


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

    retrieval_scope = _normalize_artifact_scope(args, workspace_id)
    if retrieval_scope == "archive_global":
        obj = archive_service.get_artifact_across_workspaces(_artifact_workspace_ids(workspace_id), artifact_id)
    else:
        obj = archive_service.get_artifact(workspace_id, artifact_id)
    preview = obj.get("content_preview", "")
    return {
        "structuredContent": {
            **obj,
            "retrieval_scope": retrieval_scope,
        },
        "content": [
            {
                "type": "text",
                "text": (
                    f"Artifact {obj['artifact_id']} - {obj.get('display_name') or obj.get('title')}\n"
                    f"Workspace: {obj.get('workspace_id')}\n\n{preview}"
                ),
            }
        ],
    }


def handle_artifact_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    include_archived = _parse_bool(args.get("include_archived"), False)
    retrieval_scope = _normalize_artifact_scope(args, workspace_id)
    if retrieval_scope == "archive_global":
        rows = archive_service.list_artifacts_across_workspaces(
            _artifact_workspace_ids(workspace_id),
            include_archived=True,
        )
    else:
        rows = archive_service.list_artifacts(workspace_id, include_archived=include_archived)
    return {
        "structuredContent": {
            "workspace_id": workspace_id,
            "count": len(rows),
            "retrieval_scope": retrieval_scope,
            "include_archived": include_archived,
            "artifacts": rows,
        },
        "content": [
            {
                "type": "text",
                "text": (
                    f"Found {len(rows)} artifact(s) "
                    f"({'all workspaces' if retrieval_scope == 'archive_global' else 'this workspace'})."
                ),
            }
        ],
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
    retrieval_scope = _normalize_artifact_scope(args, workspace_id)
    if retrieval_scope == "archive_global":
        rows = archive_service.list_artifacts_across_workspaces(_artifact_workspace_ids(workspace_id), include_archived=True)
    else:
        rows = archive_service.list_artifacts(workspace_id, include_archived=True)
    return {
        "structuredContent": {
            "workspace_id": workspace_id,
            "count": len(rows),
            "retrieval_scope": retrieval_scope,
            "artifacts": rows,
        },
        "content": [
            {
                "type": "text",
                "text": (
                    f"Found {len(rows)} artifact(s) "
                    f"({'all workspaces' if retrieval_scope == 'archive_global' else 'this workspace'})."
                ),
            }
        ],
    }


def handle_archive_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    _require_artifact_workspace(workspace_id)
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")

    retrieval_scope = _normalize_artifact_scope(args, workspace_id)
    if retrieval_scope == "archive_global":
        obj = archive_service.get_artifact_across_workspaces(_artifact_workspace_ids(workspace_id), artifact_id)
    else:
        obj = archive_service.get_artifact(workspace_id, artifact_id)
    preview = obj.get("content_preview", "")
    return {
        "structuredContent": {
            **obj,
            "retrieval_scope": retrieval_scope,
        },
        "content": [
            {
                "type": "text",
                "text": (
                    f"Artifact {obj['artifact_id']} - {obj['display_name']}\n"
                    f"Workspace: {obj.get('workspace_id')}\n\n{preview}"
                ),
            }
        ],
    }


def handle_nancy_artifacts_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    retrieval_scope = _normalize_artifact_scope(args, workspace_id)
    return nancy_service.artifacts_list_response(workspace_id, retrieval_scope=retrieval_scope)


def handle_nancy_artifact_open(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not artifact_id:
        raise error_missing_required_field("artifact_id")
    retrieval_scope = _normalize_artifact_scope(args, workspace_id)
    return nancy_service.artifact_open_response(workspace_id, artifact_id, retrieval_scope=retrieval_scope)


def handle_nancy_workspace_briefing(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = args["workspace_id"]
    return nancy_service.workspace_briefing_response(workspace_id)


def _resolve_file_workspace(args: Dict[str, Any]) -> str:
    tool = "office.file_upload"
    workspace_id = str(args.get("workspace_id", "")).strip()
    session_id = str(args.get("session_id", "")).strip()
    if session_id:
        return resolve_workspace_id(tool, {"session_id": session_id, "workspace_id": workspace_id})
    if workspace_id:
        return workspace_id
    return resolve_workspace_id(tool, args)


def handle_file_upload(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = _resolve_file_workspace(args)
    original_name = str(args.get("name") or args.get("filename") or args.get("file_name") or "").strip()
    if not original_name:
        raise error_missing_required_field("name")
    scope = str(args.get("scope") or "workspace").strip().lower() or "workspace"
    scope_ref = str(args.get("scope_ref") or "").strip()
    service = private_file_service if scope == "private" else workspace_file_service
    record = service.upload_file(
        workspace_id=workspace_id,
        original_name=original_name,
        content_text=args.get("content_text"),
        content_base64=args.get("content_base64"),
        data_url=args.get("data_url"),
        mime_type=str(args.get("mime_type") or "").strip() or None,
        kind=str(args.get("kind") or "generic").strip() or "generic",
        scope=scope,
        scope_ref=scope_ref or scope,
        description=args.get("description"),
        uploaded_by_user_id=str(args.get("uploaded_by_user_id") or "").strip() or None,
        uploaded_by_session_id=str(args.get("session_id") or "").strip() or None,
    )
    return {
        **record,
        "structuredContent": record,
        "content": [{"type": "text", "text": f"Uploaded file {record['original_name']} as {record['file_id']}."}],
    }


def handle_file_list(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = _resolve_file_workspace(args)
    scope = str(args.get("scope") or "").strip().lower() or None
    scope_ref = str(args.get("scope_ref") or "").strip() or None
    service = private_file_service if scope == "private" else workspace_file_service
    rows = service.list_files(workspace_id, scope=scope, scope_ref=scope_ref)
    return {
        "workspace_id": workspace_id,
        "count": len(rows),
        "files": rows,
        "structuredContent": {
            "workspace_id": workspace_id,
            "count": len(rows),
            "files": rows,
        },
        "content": [{"type": "text", "text": f"Found {len(rows)} file(s)."}],
    }


def handle_file_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = _resolve_file_workspace(args)
    file_id = str(args.get("file_id") or "").strip()
    if not file_id:
        raise error_missing_required_field("file_id")
    scope = str(args.get("scope") or "").strip().lower() or "workspace"
    service = private_file_service if scope == "private" else workspace_file_service
    record = service.get_file(workspace_id, file_id)
    return {
        **record,
        "structuredContent": record,
        "content": [{"type": "text", "text": f"File {record['file_id']} - {record['original_name']}."}],
    }


def handle_file_download_response(workspace_id: str, file_id: str, scope: str = "workspace"):
    service = private_file_service if scope == "private" else workspace_file_service
    record = service.get_file(workspace_id, file_id)
    return FileResponse(
        path=record["storage_path"],
        filename=record["original_name"],
        media_type=record["mime_type"] or "application/octet-stream",
    )


def handle_receptionist_context_get(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = resolve_workspace_id("office.receptionist_context_get", args)
    context = receptionist_context_service.get_context(workspace_id)
    return {
        "structuredContent": context,
        "content": [{"type": "text", "text": f"Loaded receptionist context for {workspace_id}."}],
    }


def handle_private_file_upload(args: Dict[str, Any]) -> Dict[str, Any]:
    args = dict(args)
    args["scope"] = "private"
    return handle_file_upload(args)


def handle_private_file_list(args: Dict[str, Any]) -> Dict[str, Any]:
    args = dict(args)
    args["scope"] = "private"
    return handle_file_list(args)


def handle_private_file_get(args: Dict[str, Any]) -> Dict[str, Any]:
    args = dict(args)
    args["scope"] = "private"
    return handle_file_get(args)


def handle_receptionist_context_update(args: Dict[str, Any]) -> Dict[str, Any]:
    workspace_id = resolve_workspace_id("office.receptionist_context_update", args)
    updates = {
        "room_directory": args.get("room_directory"),
        "persona_directory": args.get("persona_directory"),
        "receptionist_script": args.get("receptionist_script"),
        "policy_summary": args.get("policy_summary"),
        "known_user_profile": args.get("known_user_profile"),
        "session_summary_text": args.get("session_summary_text"),
        "recent_turns": args.get("recent_turns"),
        "current_prompt_state": args.get("current_prompt_state"),
    }
    context = receptionist_context_service.update_context(workspace_id, updates)
    return {
        "structuredContent": context,
        "content": [{"type": "text", "text": f"Updated receptionist context for {workspace_id}."}],
    }


def refresh_handler_bindings() -> None:
    global handle_workspaces_list
    global handle_workspace_new
    global handle_office_bootstrap
    global handle_office_state_get
    global handle_office_transcript_get
    global handle_commands_list
    global handle_office_room_set
    global handle_office_nancy_route
    global handle_mailroom_dispatch
    global handle_memos_list
    global handle_memo_get
    global handle_artifact_create
    global handle_artifact_get
    global handle_artifact_list
    global handle_artifact_update
    global handle_artifact_append
    global handle_artifact_archive
    global handle_archive_store_text
    global handle_archive_list
    global handle_archive_get
    global handle_nancy_artifacts_list
    global handle_nancy_artifact_open
    global handle_nancy_workspace_briefing
    global handle_file_upload
    global handle_file_list
    global handle_file_get
    global handle_file_download_response
    global handle_private_file_upload
    global handle_private_file_list
    global handle_private_file_get
    global handle_receptionist_context_get
    global handle_receptionist_context_update
    global handle_ai_generate
    global handle_search_web
    global handle_search_reviews
    global handle_search_places
    global handle_ocr_extract

    handler_deps = HandlerDeps(
        kernel=kernel,
        store=store,
        pipeline=pipeline,
        archive_service=archive_service,
        memo_service=memo_service,
        nancy_service=nancy_service,
        receptionist_context_service=receptionist_context_service,
        workspace_file_service=workspace_file_service,
        private_file_service=private_file_service,
        search_service=search_service,
        ocr_service=ocr_service,
        model_router=model_router,
        user_service=user_service,
        utc_now=utc_now,
        stable_state_sha=stable_state_sha,
        append_incident=append_incident,
        error_missing_required_field=error_missing_required_field,
        resolve_workspace_id=resolve_workspace_id,
    )

    workspace_handlers = build_workspace_handlers(handler_deps)
    memo_handlers = build_memo_handlers(handler_deps)
    artifact_handlers = build_artifact_handlers(handler_deps)
    file_handlers = build_file_handlers(handler_deps)
    ai_handlers = build_ai_handlers(handler_deps)

    handle_workspaces_list = workspace_handlers["office.workspaces_list"]
    handle_workspace_new = workspace_handlers["office.workspace_new"]
    handle_office_bootstrap = workspace_handlers["office.bootstrap"]
    handle_office_state_get = workspace_handlers["office.state_get"]
    handle_office_transcript_get = workspace_handlers["office.transcript_get"]
    handle_commands_list = workspace_handlers["office.commands_list"]
    handle_office_room_set = workspace_handlers["office.room_set"]
    handle_office_nancy_route = workspace_handlers["office.nancy_route"]

    handle_mailroom_dispatch = memo_handlers["mailroom.dispatch"]
    handle_memos_list = memo_handlers["office.memos_list"]
    handle_memo_get = memo_handlers["office.memo_get"]

    handle_artifact_create = artifact_handlers["office.artifact_create"]
    handle_artifact_get = artifact_handlers["office.artifact_get"]
    handle_artifact_list = artifact_handlers["office.artifact_list"]
    handle_artifact_update = artifact_handlers["office.artifact_update"]
    handle_artifact_append = artifact_handlers["office.artifact_append"]
    handle_artifact_archive = artifact_handlers["office.artifact_archive"]
    handle_archive_store_text = artifact_handlers["office.archive_store_text"]
    handle_archive_list = artifact_handlers["office.archive_list"]
    handle_archive_get = artifact_handlers["office.archive_get"]
    handle_nancy_artifacts_list = artifact_handlers["office.nancy_artifacts_list"]
    handle_nancy_artifact_open = artifact_handlers["office.nancy_artifact_open"]
    handle_nancy_workspace_briefing = artifact_handlers["office.nancy_workspace_briefing"]

    handle_file_upload = file_handlers["office.file_upload"]
    handle_file_list = file_handlers["office.file_list"]
    handle_file_get = file_handlers["office.file_get"]
    handle_file_download_response = file_handlers["__file_download_response__"]
    handle_private_file_upload = file_handlers["office.private_file_upload"]
    handle_private_file_list = file_handlers["office.private_file_list"]
    handle_private_file_get = file_handlers["office.private_file_get"]
    handle_receptionist_context_get = file_handlers["office.receptionist_context_get"]
    handle_receptionist_context_update = file_handlers["office.receptionist_context_update"]

    handle_ai_generate = ai_handlers["office.ai_generate"]
    handle_search_web = ai_handlers["office.search_web"]
    handle_search_reviews = ai_handlers["office.search_reviews"]
    handle_search_places = ai_handlers["office.search_places"]
    handle_ocr_extract = ai_handlers["office.ocr_extract"]


refresh_handler_bindings()


register_tools(
    router,
    {
        "office.workspaces_list": handle_workspaces_list,
        "office.workspace_new": handle_workspace_new,
        "office.bootstrap": handle_office_bootstrap,
        "office.state_get": handle_office_state_get,
        "office.transcript_get": handle_office_transcript_get,
        "office.commands_list": handle_commands_list,
        "office.room_set": handle_office_room_set,
        "office.nancy_route": handle_office_nancy_route,
        "office.ai_generate": handle_ai_generate,
        "office.search_web": handle_search_web,
        "office.search_reviews": handle_search_reviews,
        "office.search_places": handle_search_places,
        "office.ocr_extract": handle_ocr_extract,
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
        "office.receptionist_context_get": handle_receptionist_context_get,
        "office.receptionist_context_update": handle_receptionist_context_update,
        "office.file_upload": handle_file_upload,
        "office.file_list": handle_file_list,
        "office.file_get": handle_file_get,
        "office.file_download": handle_file_get,
        "office.private_file_upload": handle_private_file_upload,
        "office.private_file_list": handle_private_file_list,
        "office.private_file_get": handle_private_file_get,
    },
    definitions=VERIDEX_TOOL_DEFINITIONS,
)

pipeline.tool_names = router.tool_names()
pipeline.tool_catalog = [
    {
        "tool_name": definition.tool_name,
        "capability": definition.capability,
        "visibility": definition.visibility,
        "description": definition.description,
    }
    for definition in router.definitions()
]
