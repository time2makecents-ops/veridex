from __future__ import annotations

import re
from typing import Any, Dict

from fastapi import HTTPException

from office_app.server.errors import error_missing_required_field

from .dependencies import HandlerDeps


SESSION_START_RE = re.compile(
    r"^(?:new|start|create)(?:\s+a|\s+an|\s+the)?\s+session(?:\s+for|\s+about|\s+called|\s+named)?\s*(.*)$",
    re.IGNORECASE,
)


def _normalize_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return "New Session"
    if len(text) > 48:
        text = text[:48].rstrip()
    return text[:1].upper() + text[1:] if text else "New Session"


def _extract_topic(request_text: str) -> str:
    text = str(request_text or "").strip()
    if not text:
        return ""
    match = SESSION_START_RE.match(text)
    if not match:
        return ""
    remainder = str(match.group(1) or "").strip(" .,:;")
    if remainder.lower().startswith("for "):
        remainder = remainder[4:].strip(" .,:;")
    if remainder.lower().startswith("about "):
        remainder = remainder[6:].strip(" .,:;")
    return remainder


def build_session_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def _sorted_sessions(*, current_session_id: str, workspace_id: str, user_id: str) -> list[Dict[str, Any]]:
        rows = deps.user_service.list_sessions(user_id, workspace_id=workspace_id)
        sessions = []
        for row in rows:
            sessions.append(
                {
                    **row,
                    "active_room": row.get("active_room") or "lobby",
                    "active_persona": row.get("active_persona") or "Receptionist",
                    "is_current": row.get("session_id") == current_session_id,
                }
            )
        sessions.sort(
            key=lambda item: (
                1 if item.get("is_current") else 0,
                str(item.get("last_active_at") or ""),
                str(item.get("updated_at") or ""),
                str(item.get("created_at") or ""),
                str(item.get("session_id") or ""),
            ),
            reverse=True,
        )
        return sessions

    def _resolve_session_ref(*, current_session_id: str, workspace_id: str, user_id: str, session_ref: str) -> Dict[str, Any]:
        sessions = _sorted_sessions(current_session_id=current_session_id, workspace_id=workspace_id, user_id=user_id)
        ref = re.sub(r"\s+", " ", str(session_ref or "").strip())
        if not ref:
            raise HTTPException(status_code=400, detail="Session reference required.")
        numeric_match = re.fullmatch(r"#?(\d{1,3})", ref)
        if numeric_match:
            index = int(numeric_match.group(1))
            if 1 <= index <= len(sessions):
                return sessions[index - 1]
            raise HTTPException(status_code=404, detail=f"Session {index} was not found.")
        lowered_ref = ref.casefold()
        for session in sessions:
            title = str(session.get("title") or "").strip()
            session_id_value = str(session.get("session_id") or "").strip()
            if title.casefold() == lowered_ref or session_id_value.casefold() == lowered_ref:
                return session
        for session in sessions:
            title = str(session.get("title") or "").strip()
            session_id_value = str(session.get("session_id") or "").strip()
            if title.casefold().startswith(lowered_ref) or session_id_value.casefold().startswith(lowered_ref):
                return session
        raise HTTPException(status_code=404, detail=f"Session '{ref}' was not found.")

    def handle_sessions_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.sessions_list", args)
        user = deps.user_service.get_user_for_session(str(args.get("session_id") or "").strip())
        current_session_id = str(user.get("last_active_session_id") or "").strip()
        current_workspace = deps.kernel.get_state(workspace_id)
        sessions = _sorted_sessions(
            current_session_id=current_session_id,
            workspace_id=workspace_id,
            user_id=str(user["user_id"]),
        )
        lines = ["Here are the sessions:"]
        items = []
        for index, item in enumerate(sessions, start=1):
            title = str(item.get("title") or item.get("session_id") or f"Session {index}").strip()
            session_id = str(item.get("session_id") or "").strip()
            description = title
            if session_id and session_id != title:
                description = f"{title} ({session_id})"
            if item.get("is_current"):
                description += " [Active]"
            lines.append(f"{index}. {description}")
            items.append({"index": index, "description": description})
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "current_session_id": current_session_id,
                "current_workspace_id": current_workspace.get("workspace_id", workspace_id),
                "count": len(sessions),
                "sessions": sessions,
                "items": items,
                "response_text": "\n".join(lines),
            },
            "content": [{"type": "text", "text": "\n".join(lines)}],
        }

    def handle_session_create(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        current_user = deps.user_service.get_user_for_session(session_id)
        workspace_id = deps.resolve_workspace_id("office.session_create", args)
        request_text = str(args.get("request_text") or "").strip()
        title = str(args.get("title") or "").strip()
        description = str(args.get("description") or "").strip()
        if not title and request_text:
            topic = _extract_topic(request_text)
            title = _normalize_title(topic or "New Session")
            description = topic or description
        title = _normalize_title(title or "New Session")
        description = description or title
        session = deps.user_service.create_session(
            user_id=str(current_user["user_id"]),
            title=title,
            description=description,
            workspace_id=workspace_id,
            workspace_label=title,
        )
        workspace_state = deps.kernel.get_state(session["active_workspace_id"])
        return {
            "structuredContent": {
                "session_id": session["session_id"],
                "workspace_id": session["active_workspace_id"],
                "title": session["title"],
                "description": session["description"],
                "workspace_state": workspace_state,
            },
            "content": [{"type": "text", "text": f"Started new session {session['title']}."}],
        }

    def handle_session_activate(args: Dict[str, Any]) -> Dict[str, Any]:
        current_session_id = str(args.get("session_id") or "").strip()
        session_ref = re.sub(r"\s+", " ", str(args.get("session_ref") or "").strip(" .,:;"))
        target_session_id = current_session_id
        if session_ref:
            if not current_session_id:
                raise error_missing_required_field("session_id")
            current_user = deps.user_service.get_user_for_session(current_session_id)
            workspace_id = deps.resolve_workspace_id("office.session_activate", args)
            target = _resolve_session_ref(
                current_session_id=current_session_id,
                workspace_id=workspace_id,
                user_id=str(current_user["user_id"]),
                session_ref=session_ref,
            )
            target_session_id = str(target.get("session_id") or "").strip()
        if not target_session_id:
            raise error_missing_required_field("session_id")
        session = deps.user_service.select_session_for_user(target_session_id)
        workspace_state = deps.kernel.get_state(session["active_workspace_id"])
        return {
            "structuredContent": {
                "session_id": session["session_id"],
                "workspace_id": session["active_workspace_id"],
                "title": session["title"],
                "description": session["description"],
                "workspace_state": workspace_state,
            },
            "content": [{"type": "text", "text": f"You are now in session {session['title']} ({session['session_id']})."}],
        }

    def handle_workspace_activate(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not workspace_id:
            raise error_missing_required_field("workspace_id")
        current_user = deps.user_service.get_user_for_session(session_id)
        result = deps.user_service.activate_workspace(user_id=str(current_user["user_id"]), workspace_id=workspace_id)
        workspace_state = result["workspace_state"]
        session = result["session"]
        return {
            "structuredContent": {
                "workspace_id": result["workspace_id"],
                "session_id": session["session_id"],
                "title": session["title"],
                "description": session["description"],
                "workspace_state": workspace_state,
            },
            "content": [{"type": "text", "text": f"Activated workspace {workspace_id}."}],
        }

    return {
        "office.sessions_list": handle_sessions_list,
        "office.session_create": handle_session_create,
        "office.session_activate": handle_session_activate,
        "office.workspace_activate": handle_workspace_activate,
    }
