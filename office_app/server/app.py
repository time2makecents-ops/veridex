from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from office_app.server.archive_service import ArchiveService
from office_app.server.command_router import CommandRouter
from office_app.server.errors import error_missing_required_field
from office_app.server.model_router import ModelRouter
from office_app.server.receptionist_context_service import ReceptionistContextService
from office_app.server.memo_service import MemoService
from office_app.server.nancy_service import NancyService
from office_app.server.ocr_service import OcrService
from office_app.server.artifact_request_helpers import pending_room_navigation
from office_app.server.request_pipeline import RequestPipeline
from office_app.server.request_transcript import record_assistant_turn, record_user_turn
from office_app.server.request_response_helpers import (
    attach_request_context,
    make_tool_text_conversational,
    request_text_from_response,
)
from office_app.server.search_service import SearchService
from office_app.server.search_response_synthesis import build_grounded_search_context, synthesize_search_response
from office_app.server.handlers.ai_handlers import build_ai_handlers
from office_app.server.handlers.artifact_handlers import build_artifact_handlers
from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.file_handlers import build_file_handlers
from office_app.server.handlers.memo_handlers import build_memo_handlers
from office_app.server.handlers.session_handlers import build_session_handlers
from office_app.server.handlers.workspace_handlers import build_workspace_handlers
from office_app.server.tool_context import ToolContext
from office_app.server.tool_definitions import VERIDEX_TOOL_DEFINITIONS, ToolDefinition
from office_app.server.user_service import UserService
from office_app.server.tools_registry import register_tools
from office_app.server.workspace_file_service import PrivateFileService, WorkspaceFileService
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore

SERVER_DIR = Path(__file__).resolve().parent
PKG_DIR = SERVER_DIR.parent

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
    if tool in WORKSPACE_TOOLS_NO_ID:
        return workspace_id
    if tool == "office.workspace_activate" and workspace_id:
        return workspace_id
    if session_id:
        session = user_service.get_session(session_id)
        resolved = str(session.get("active_workspace_id") or "").strip()
        if resolved:
            return resolved
        raise HTTPException(status_code=409, detail="Session is missing an active workspace.")
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


def _session_user_profile(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    try:
        return user_service.get_user_for_session(session_id)
    except HTTPException:
        return None


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
    user_service.restore_session_room(session_id)
    user_profile = _session_user_profile(session_id)
    current_state = kernel.get_state(workspace_id)
    pending_navigation = pending_room_navigation(current_state)
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
            record_assistant_turn(
                workspace_id=workspace_id,
                session_id=session_id,
                response_text=request_text_from_response(result),
                kernel=kernel,
                store=store,
                receptionist_context_service=receptionist_context_service,
                user_profile=user_profile,
                speaker="System",
                room_id=str((structured_result or {}).get("active_room") or target_room),
                persona_name=str((structured_result or {}).get("active_persona") or ""),
            )
            response = result
            if isinstance(response, dict):
                structured = response.get("structuredContent")
                if isinstance(structured, dict):
                    structured["routing"] = {
                        "route_kind": "navigation",
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
            record_assistant_turn(
                workspace_id=workspace_id,
                session_id=session_id,
                response_text=response_text,
                kernel=kernel,
                store=store,
                receptionist_context_service=receptionist_context_service,
                user_profile=user_profile,
            )
            return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

    current_state = kernel.get_state(workspace_id)
    pending_session_create = _pending_session_create(current_state, session_id)
    if pending_session_create and request_text:
        record_user_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            request_text=request_text,
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
        )
        if _is_cancel_text(request_text) or _is_confirmation_no(request_text):
            current_state = _clear_pending_session_create(current_state, session_id)
            store.save_state(workspace_id, current_state)
            response_text = "Okay. I did not create a new session."
            response = {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "response_text": response_text,
                    "routing": {
                        "route_kind": "clarify",
                        "capability": "session.create.name_required",
                        "tool": "office.session_create",
                        "reason": "Cancelled pending session creation.",
                    },
                },
                "content": [{"type": "text", "text": response_text}],
            }
            record_assistant_turn(
                workspace_id=workspace_id,
                session_id=session_id,
                response_text=response_text,
                kernel=kernel,
                store=store,
                receptionist_context_service=receptionist_context_service,
                user_profile=user_profile,
            )
            return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

        current_state = _clear_pending_session_create(current_state, session_id)
        store.save_state(workspace_id, current_state)
        title_text = str(request_text or "").strip(" .,:;") or "New Session"
        result = router.dispatch_capability(
            "session.create",
            {
                "workspace_id": workspace_id,
                "session_id": session_id,
                "title": title_text,
                "description": title_text,
                "request_text": f"start new session named {title_text}",
            },
            preferred_tool="office.session_create",
        )
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "tool",
                    "capability": "session.create",
                    "tool": "office.session_create",
                    "reason": "Created a new session from the pending session-name prompt.",
                }
        enriched = attach_request_context(result, workspace_id=workspace_id, session_id=session_id)
        record_assistant_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            response_text=request_text_from_response(enriched),
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
        )
        return enriched

    routed = _resolve_routed_request(
        workspace_id=workspace_id,
        session_id=session_id,
        request_text=request_text,
    )
    _record_routed_user_turn(
        routed=routed,
        workspace_id=workspace_id,
        session_id=session_id,
        request_text=request_text,
        user_profile=user_profile,
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
        result = make_tool_text_conversational(result, str(routed.get("capability") or ""))
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "artifact",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                }
            enriched = attach_request_context(result, workspace_id=workspace_id, session_id=session_id)
            response_text = request_text_from_response(enriched)
            current_state = kernel.get_state(workspace_id)
            record_assistant_turn(
                workspace_id=workspace_id,
                session_id=session_id,
                response_text=response_text,
                kernel=kernel,
                store=store,
                receptionist_context_service=receptionist_context_service,
                user_profile=user_profile,
            )
            return enriched

    if routed["route_kind"] == "tool":
        args = dict(routed["arguments"])
        args["workspace_id"] = workspace_id
        if session_id:
            args["session_id"] = session_id
        try:
            result = router.dispatch_capability(
                routed["capability"],
                args,
                preferred_tool=routed.get("tool"),
            )
        except HTTPException:
            if routed.get("grounding_required") and str(routed.get("capability") or "").startswith("search."):
                entity_subject = str(routed.get("entity_subject") or "that entity").strip() or "that entity"
                response_text = f"I could not verify information about {entity_subject} because the search failed. I should not guess."
                response = {
                    "structuredContent": {
                        "workspace_id": workspace_id,
                        "session_id": session_id,
                        "response_text": response_text,
                        "routing": {
                            "route_kind": "clarify",
                            "capability": "clarification.entity_grounding",
                            "tool": routed.get("tool"),
                            "reason": "Grounded factual search failed closed.",
                        },
                    },
                    "content": [{"type": "text", "text": response_text}],
                }
                response = _apply_navigator_activation(
                    response,
                    capability="clarification.entity_grounding",
                    reason="Grounded factual search failed closed.",
                )
                enriched = attach_request_context(response, workspace_id=workspace_id, session_id=session_id)
                record_assistant_turn(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    response_text=response_text,
                    kernel=kernel,
                    store=store,
                    receptionist_context_service=receptionist_context_service,
                    user_profile=user_profile,
                    speaker=_response_speaker(enriched),
                )
                return enriched
            raise
        result = synthesize_search_response(
            routed=routed,
            result=result,
            workspace_id=workspace_id,
            session_id=session_id,
            user_profile=user_profile,
            kernel=kernel,
            router=router,
            request_text_from_response=request_text_from_response,
        )
        _remember_grounded_search_context(
            workspace_id=workspace_id,
            session_id=session_id,
            routed=routed,
            result=result,
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
        record_assistant_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            response_text=request_text_from_response(enriched),
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
        )
        return enriched

    if routed["route_kind"] == "navigation":
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
                        "route_kind": "navigation",
                        "capability": routed["capability"],
                        "tool": routed["tool"],
                        "reason": routed["reason"],
                        "auto_routed": False,
                    },
                },
                "content": [{"type": "text", "text": response_text}],
            }
            record_assistant_turn(
                workspace_id=workspace_id,
                session_id=session_id,
                response_text=response_text,
                kernel=kernel,
                store=store,
                receptionist_context_service=receptionist_context_service,
                user_profile=user_profile,
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
        record_assistant_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            response_text=request_text_from_response(result),
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
            speaker="System",
            room_id=str((structured_result or {}).get("active_room") or target_room),
            persona_name=str((structured_result or {}).get("active_persona") or ""),
        )
        response = result
        if isinstance(response, dict):
            structured = response.get("structuredContent")
            if isinstance(structured, dict):
                structured["routing"] = {
                    "route_kind": "navigation",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                    "auto_routed": True,
                }
        return attach_request_context(response, workspace_id=workspace_id, session_id=session_id)

    if routed["route_kind"] == "clarify":
        if str(routed.get("capability") or "") == "session.create.name_required":
            current_state = kernel.get_state(workspace_id)
            current_state = _set_pending_session_create(current_state, session_id, request_text)
            store.save_state(workspace_id, current_state)
        response_text = str(routed.get("arguments", {}).get("response_text") or "Did you mean something else?")
        if str(routed.get("capability") or "") == "clarification.entity_grounding":
            entity_subject = str(routed.get("arguments", {}).get("entity_subject") or "").strip()
            if entity_subject:
                response_text = _entity_grounding_response_text(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    entity_subject=entity_subject,
                )
        response = {
            "structuredContent": {
                "workspace_id": workspace_id,
                "session_id": session_id,
                "response_text": response_text,
                "routing": {
                    "route_kind": "clarify",
                    "capability": routed["capability"],
                    "tool": routed["tool"],
                    "reason": routed["reason"],
                },
            },
            "content": [{"type": "text", "text": response_text}],
        }
        response = _apply_navigator_activation(
            response,
            capability=str(routed.get("capability") or ""),
            reason=str(routed.get("reason") or ""),
        )
        enriched = attach_request_context(response, workspace_id=workspace_id, session_id=session_id)
        record_assistant_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            response_text=response_text,
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
            speaker=_response_speaker(enriched),
        )
        return enriched

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
        enriched = _normalize_model_governance_response(
            enriched,
            workspace_id=workspace_id,
            session_id=session_id,
            request_text=request_text,
        )
        record_assistant_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            response_text=request_text_from_response(enriched),
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
            speaker=_response_speaker(enriched),
        )
        return enriched

    response = pipeline.nancy_route_response(workspace_id, request_text)
    record_assistant_turn(
        workspace_id=workspace_id,
        session_id=session_id,
        response_text=request_text_from_response(response),
        kernel=kernel,
        store=store,
        receptionist_context_service=receptionist_context_service,
        user_profile=user_profile,
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
    args = {"workspace_id": workspace_id, "session_id": session_id}
    return handle_receptionist_context_get(args)


@app.get("/sessions")
def list_sessions(
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    args = {"workspace_id": workspace_id, "session_id": session_id}
    return handle_sessions_list(args)


@app.get("/workspaces")
def list_workspaces(
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    return handle_workspaces_list({"session_id": session_id})


@app.post("/sessions")
def create_session(payload: dict[str, Any]) -> Dict[str, Any]:
    return handle_session_create(dict(payload or {}))


@app.post("/sessions/select")
def select_session(payload: dict[str, Any]) -> Dict[str, Any]:
    return handle_session_activate(dict(payload or {}))


@app.post("/workspaces/select")
def select_workspace(payload: dict[str, Any]) -> Dict[str, Any]:
    return handle_workspace_activate(dict(payload or {}))


@app.post("/receptionist/context")
def receptionist_context_update(payload: ReceptionistContextUpdateRequest) -> Dict[str, Any]:
    return handle_receptionist_context_update(payload.model_dump())


@app.get("/files")
def list_files(
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
    scope_ref: Optional[str] = None,
) -> Dict[str, Any]:
    args = {
        "workspace_id": workspace_id,
        "session_id": session_id,
        "scope": scope,
        "scope_ref": scope_ref,
    }
    return handle_file_list(args)


@app.post("/files/upload")
def upload_file(payload: FileUploadRequest) -> Dict[str, Any]:
    return handle_file_upload(payload.model_dump())


@app.get("/files/{file_id}")
def get_file_metadata(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    args = {
        "file_id": file_id,
        "workspace_id": workspace_id,
        "session_id": session_id,
        "scope": scope,
    }
    return handle_file_get(args)


@app.get("/files/{file_id}/download")
def download_file(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None,
):
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    selected_scope = str(scope or "workspace").strip().lower() or "workspace"
    return handle_file_download_response(resolved_workspace_id, file_id, selected_scope)


@app.get("/private-files/{file_id}")
def get_private_file_metadata(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    return handle_private_file_get(
        {
            "file_id": file_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
        }
    )


@app.get("/private-files/{file_id}/download")
def download_private_file(
    file_id: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    resolved_workspace_id = _resolve_http_workspace_id(workspace_id, session_id)
    return handle_file_download_response(resolved_workspace_id, file_id, "private")


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


def _is_cancel_text(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return normalized in {"cancel", "never mind", "nevermind", "stop", "abort"}


def _pending_session_create(state: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
    pending_map = state.get("pending_session_create_by_session")
    if not isinstance(pending_map, dict):
        return None
    pending = pending_map.get(session_id)
    return pending if isinstance(pending, dict) else None


def _set_pending_session_create(state: Dict[str, Any], session_id: str, request_text: str) -> Dict[str, Any]:
    pending_map = dict(state.get("pending_session_create_by_session") or {})
    pending_map[session_id] = {
        "request_text": request_text,
        "ts": utc_now(),
    }
    state["pending_session_create_by_session"] = pending_map
    return state


def _clear_pending_session_create(state: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    pending_map = state.get("pending_session_create_by_session")
    if not isinstance(pending_map, dict):
        return state
    next_map = dict(pending_map)
    next_map.pop(session_id, None)
    if next_map:
        state["pending_session_create_by_session"] = next_map
    else:
        state.pop("pending_session_create_by_session", None)
    return state


def _resolve_routed_request(*, workspace_id: str, session_id: str, request_text: str) -> Dict[str, Any]:
    routed = pipeline.route_user_request(workspace_id, request_text, session_id=session_id)
    if routed["route_kind"] != "model":
        return routed
    followup_route = pipeline.route_contextual_followup(
        workspace_id,
        request_text,
        store.load_transcript(workspace_id, limit=16, session_id=session_id),
        session_id=session_id,
    )
    return followup_route or routed


def _record_routed_user_turn(
    *,
    routed: Dict[str, Any],
    workspace_id: str,
    session_id: str,
    request_text: str,
    user_profile: Dict[str, Any] | None,
) -> None:
    if routed["route_kind"] not in {"artifact", "model", "navigation", "tool", "clarify"}:
        return
    record_user_turn(
        workspace_id=workspace_id,
        session_id=session_id,
        request_text=request_text,
        kernel=kernel,
        store=store,
        receptionist_context_service=receptionist_context_service,
        user_profile=user_profile,
    )


def _navigator_activation_for_capability(capability: str, *, reason: str = "") -> Dict[str, Any] | None:
    normalized = str(capability or "").strip().lower()
    if normalized.startswith("clarification."):
        activation = {
            **NAVIGATOR_CONTROL,
            "visibility": "VISIBLE",
            "activated": True,
            "mode": "intervention",
            "reason": reason or "Navigator intervened to keep the response grounded and on track.",
        }
        if normalized == "clarification.entity_grounding":
            activation["mode"] = "verification"
            activation["reason"] = reason or "Verification required before stating unsupported facts."
        elif normalized == "clarification.entity_followup":
            activation["mode"] = "grounded_followup"
            activation["reason"] = reason or "Grounded search evidence required for this follow-up."
        return activation
    return None


def _session_room_title(*, workspace_id: str, session_id: str) -> str:
    room_id = ""
    try:
        session = user_service.get_session(session_id)
        room_id = str(session.get("active_room") or "").strip()
    except Exception:
        room_id = ""
    if not room_id:
        try:
            room_id = str(kernel.get_state(workspace_id).get("active_room") or "").strip()
        except Exception:
            room_id = ""
    if not room_id:
        return "current department"
    return pipeline.room_title_for_id(room_id)


def _entity_grounding_response_text(*, workspace_id: str, session_id: str, entity_subject: str) -> str:
    room_title = str(_session_room_title(workspace_id=workspace_id, session_id=session_id) or "").strip()
    room_phrase = room_title if room_title.lower().startswith("the ") else f"the {room_title}" if room_title else "the current department"
    return (
        f"Veridex doesn't have any verified information about {entity_subject}. "
        f"Have {room_phrase} do an internet search or search your other sessions if you want to know more."
    )


def _apply_navigator_activation(response: Dict[str, Any], *, capability: str, reason: str = "") -> Dict[str, Any]:
    activation = _navigator_activation_for_capability(capability, reason=reason)
    if activation is None:
        structured = response.get("structuredContent")
        if isinstance(structured, dict):
            routing = structured.get("routing")
            if isinstance(routing, dict) and str(routing.get("route_kind") or "").strip().lower() == "clarify":
                activation = {
                    **NAVIGATOR_CONTROL,
                    "visibility": "VISIBLE",
                    "activated": True,
                    "mode": "intervention",
                    "reason": reason or "Navigator intervened to resolve an issue before continuing.",
                }
    if activation is None:
        return response
    enriched = dict(response)
    structured = dict(enriched.get("structuredContent") or {})
    structured["navigator_activation"] = activation
    structured["speaker"] = "Navigator"
    enriched["structuredContent"] = structured
    return enriched


def _normalize_model_governance_response(
    response: Dict[str, Any],
    *,
    workspace_id: str,
    session_id: str,
    request_text: str,
) -> Dict[str, Any]:
    entity_request = pipeline.extract_factual_entity_request(request_text)
    if entity_request is None or entity_request.get("search_requested"):
        return response
    response_text = request_text_from_response(response)
    lowered = response_text.lower()
    if "verified information" not in lowered and "i should not guess" not in lowered:
        return response
    entity_subject = str(entity_request.get("entity_subject") or "").strip()
    if not entity_subject:
        return response
    normalized_text = _entity_grounding_response_text(
        workspace_id=workspace_id,
        session_id=session_id,
        entity_subject=entity_subject,
    )
    enriched = dict(response)
    structured = dict(enriched.get("structuredContent") or {})
    structured["response_text"] = normalized_text
    structured["routing"] = {
        "route_kind": "clarify",
        "capability": "clarification.entity_grounding",
        "tool": "office.capability_info",
        "reason": "Normalized a model-side unsupported entity answer into a Navigator governance response.",
    }
    enriched["structuredContent"] = structured
    enriched["content"] = [{"type": "text", "text": normalized_text}]
    return _apply_navigator_activation(
        enriched,
        capability="clarification.entity_grounding",
        reason="Normalized a model-side unsupported entity answer into a Navigator governance response.",
    )


def _response_speaker(response: Dict[str, Any]) -> Optional[str]:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        routing = structured.get("routing")
        if isinstance(routing, dict) and str(routing.get("route_kind") or "").strip().lower() == "clarify":
            return "Navigator"
        speaker = str(structured.get("speaker") or "").strip()
        if speaker:
            return speaker
        activation = structured.get("navigator_activation")
        if isinstance(activation, dict) and activation.get("activated"):
            return "Navigator"
    return None


def _remember_grounded_search_context(
    *,
    workspace_id: str,
    session_id: str,
    routed: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    if not session_id or not routed.get("grounding_required"):
        return
    grounded_context = build_grounded_search_context(routed=routed, result=result)
    if not grounded_context.get("results"):
        return
    state = kernel.get_state(workspace_id)
    session_map = dict(state.get("grounded_search_by_session") or {})
    grounded_context["ts"] = utc_now()
    session_map[session_id] = grounded_context
    state["grounded_search_by_session"] = session_map
    store.save_state(workspace_id, state)


def refresh_handler_bindings() -> None:
    global handle_workspaces_list
    global handle_workspace_new
    global handle_workspace_activate
    global handle_office_bootstrap
    global handle_office_state_get
    global handle_office_transcript_get
    global handle_commands_list
    global handle_sessions_list
    global handle_sessions_search
    global handle_session_create
    global handle_session_activate
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
    global handle_room_memory_remember
    global handle_room_memory_list
    global handle_room_memory_forget
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
    session_handlers = build_session_handlers(handler_deps)
    artifact_handlers = build_artifact_handlers(handler_deps)
    file_handlers = build_file_handlers(handler_deps)
    ai_handlers = build_ai_handlers(handler_deps)

    handle_workspaces_list = workspace_handlers["office.workspaces_list"]
    handle_workspace_new = workspace_handlers["office.workspace_new"]
    handle_workspace_activate = workspace_handlers["office.workspace_activate"]
    handle_office_bootstrap = workspace_handlers["office.bootstrap"]
    handle_office_state_get = workspace_handlers["office.state_get"]
    handle_office_transcript_get = workspace_handlers["office.transcript_get"]
    handle_commands_list = workspace_handlers["office.commands_list"]
    handle_sessions_list = session_handlers["office.sessions_list"]
    handle_sessions_search = session_handlers["office.sessions_search"]
    handle_session_create = session_handlers["office.session_create"]
    handle_session_activate = session_handlers["office.session_activate"]
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
    handle_room_memory_remember = file_handlers["office.room_memory_remember"]
    handle_room_memory_list = file_handlers["office.room_memory_list"]
    handle_room_memory_forget = file_handlers["office.room_memory_forget"]

    handle_ai_generate = ai_handlers["office.ai_generate"]
    handle_search_web = ai_handlers["office.search_web"]
    handle_search_reviews = ai_handlers["office.search_reviews"]
    handle_search_places = ai_handlers["office.search_places"]
    handle_ocr_extract = ai_handlers["office.ocr_extract"]

    register_tools(
        router,
        {
            "office.workspaces_list": handle_workspaces_list,
            "office.workspace_new": handle_workspace_new,
            "office.workspace_activate": handle_workspace_activate,
            "office.bootstrap": handle_office_bootstrap,
            "office.state_get": handle_office_state_get,
            "office.transcript_get": handle_office_transcript_get,
            "office.commands_list": handle_commands_list,
            "office.sessions_list": handle_sessions_list,
            "office.sessions_search": handle_sessions_search,
            "office.session_create": handle_session_create,
            "office.session_activate": handle_session_activate,
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
            "office.file_upload": handle_file_upload,
            "office.file_list": handle_file_list,
            "office.file_get": handle_file_get,
            "office.file_download": handle_file_download_response,
            "office.private_file_upload": handle_private_file_upload,
            "office.private_file_list": handle_private_file_list,
            "office.private_file_get": handle_private_file_get,
            "office.receptionist_context_get": handle_receptionist_context_get,
            "office.receptionist_context_update": handle_receptionist_context_update,
            "office.room_memory_remember": handle_room_memory_remember,
            "office.room_memory_list": handle_room_memory_list,
            "office.room_memory_forget": handle_room_memory_forget,
        },
    )


refresh_handler_bindings()


register_tools(
    router,
    {
        "office.workspaces_list": handle_workspaces_list,
        "office.workspace_new": handle_workspace_new,
        "office.workspace_activate": handle_workspace_activate,
        "office.bootstrap": handle_office_bootstrap,
        "office.state_get": handle_office_state_get,
        "office.transcript_get": handle_office_transcript_get,
        "office.commands_list": handle_commands_list,
        "office.sessions_list": handle_sessions_list,
        "office.sessions_search": handle_sessions_search,
        "office.session_create": handle_session_create,
        "office.session_activate": handle_session_activate,
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
        "office.room_memory_remember": handle_room_memory_remember,
        "office.room_memory_list": handle_room_memory_list,
        "office.room_memory_forget": handle_room_memory_forget,
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
