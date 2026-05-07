from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict

from office_app.server.errors import error_missing_required_field

from .dependencies import HandlerDeps


def build_workspace_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_workspaces_list(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        if session_id:
            try:
                user = deps.user_service.get_user_for_session(session_id)
                current_workspace_id = str(deps.user_service.resolve_workspace_for_session(session_id) or "").strip()
                workspaces = deps.user_service.list_user_workspaces(str(user["user_id"]))
                if current_workspace_id:
                    workspaces = sorted(
                        workspaces,
                        key=lambda row: (
                            0 if str(row.get("workspace_id") or "").strip() == current_workspace_id else 1,
                            str(row.get("last_active_at") or ""),
                            str(row.get("workspace_id") or ""),
                        ),
                    )
                idx = {
                    "workspaces": workspaces,
                    "current_workspace_id": current_workspace_id,
                }
            except Exception:
                idx = deps.kernel.list_workspaces()
        else:
            idx = deps.kernel.list_workspaces()
        return deps.pipeline.workspaces_list_response(idx)

    def handle_workspace_new(args: Dict[str, Any]) -> Dict[str, Any]:
        label = str(args.get("label") or f"Workspace {deps.utc_now()}")
        label_key = label.strip().casefold()
        idx = deps.kernel.list_workspaces()
        for row in idx.get("workspaces", []):
            existing_label = str(row.get("label") or "").strip()
            if existing_label and existing_label.casefold() == label_key:
                workspace_id = str(row.get("workspace_id") or "").strip()
                if workspace_id:
                    return deps.pipeline.workspace_new_response(workspace_id, existing_label)
        workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
        deps.kernel.create_workspace(workspace_id, label)
        return deps.pipeline.workspace_new_response(workspace_id, label)

    def handle_workspace_activate(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        if not workspace_id:
            raise error_missing_required_field("workspace_id")
        user = deps.user_service.get_user_for_session(session_id)
        result = deps.user_service.activate_workspace(user_id=str(user["user_id"]), workspace_id=workspace_id)
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

    def handle_office_bootstrap(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        state, created = deps.kernel.bootstrap_workspace(workspace_id)

        if created:
            deps.append_incident(
                severity="LOW",
                clazz="BOOTSTRAP",
                rule_or_gate="",
                command="office.bootstrap",
                input_ref=json.dumps({"workspace_id": workspace_id}),
                output_ref="state.json",
                evidence_path=str(deps.store.state_path(workspace_id)),
                notes="Initialized workspace state (default lobby + receptionist).",
                state_sha256=deps.stable_state_sha(state),
            )

        return deps.pipeline.snapshot_response(workspace_id)

    def handle_office_state_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        return deps.pipeline.snapshot_response(workspace_id)

    def handle_office_transcript_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        session_id = str(args.get("session_id") or "").strip() or None
        limit_value = args.get("limit")
        try:
            limit = int(limit_value) if limit_value is not None else 100
        except (TypeError, ValueError):
            limit = 100
        rows = deps.store.load_transcript(workspace_id, limit=max(1, min(limit, 500)), session_id=session_id)
        lines = ["Current session thread:"]
        for row in rows:
            speaker = str(row.get("speaker") or row.get("role") or "Unknown").strip() or "Unknown"
            text = re.sub(r"\s+", " ", str(row.get("text") or "").strip())
            if not text:
                continue
            lines.append(f"{speaker}: {text}")
        response_text = "\n".join(lines) if len(lines) > 1 else "Current session thread is empty."
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "session_id": session_id,
                "count": len(rows),
                "entries": rows,
                "response_text": response_text,
            },
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_commands_list(args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "structuredContent": deps.pipeline.tools_response(),
            "content": [
                {
                    "type": "text",
                    "text": "Available Veridex commands: Start Veridex, Install Watchdog, Remove Watchdog.",
                }
            ],
        }

    def handle_office_room_set(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        session_id = str(args.get("session_id") or "").strip() or None
        room_id = str(args.get("room_id", "")).strip()
        if not room_id:
            raise error_missing_required_field("room_id")

        result = deps.kernel.enter_room(workspace_id, room_id, session_id=session_id)
        deps.user_service.remember_session_room(
            session_id,
            active_room=str(result["active_room"]),
            active_persona=str(result["active_persona"]),
        )
        state = deps.kernel.get_state(workspace_id)

        deps.append_incident(
            severity="LOW",
            clazz="STATE_CHANGE",
            rule_or_gate="Room State Model v1.1.0",
            command="office.room_set",
            input_ref=json.dumps({"workspace_id": workspace_id, "room_id": result["active_room"]}),
            output_ref="state.json",
            evidence_path=str(deps.store.state_path(workspace_id)),
            notes=f"active_room: {result['previous_room']} -> {result['active_room']}",
            state_sha256=deps.stable_state_sha(state),
        )

        return deps.pipeline.enter_room_response(workspace_id, result)

    def handle_office_nancy_route(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        request_text = str(args.get("request", "")).strip()
        if not request_text:
            raise error_missing_required_field("request")
        return deps.pipeline.nancy_route_response(workspace_id, request_text)

    return {
        "office.workspaces_list": handle_workspaces_list,
        "office.workspace_new": handle_workspace_new,
        "office.workspace_activate": handle_workspace_activate,
        "office.bootstrap": handle_office_bootstrap,
        "office.state_get": handle_office_state_get,
        "office.transcript_get": handle_office_transcript_get,
        "office.commands_list": handle_commands_list,
        "office.room_set": handle_office_room_set,
        "office.nancy_route": handle_office_nancy_route,
    }
