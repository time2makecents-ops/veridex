from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict

from office_app.server.artifact_request_helpers import pending_break_room_joke, pending_room_navigation, pending_session_list, pending_session_rename
from office_app.server.errors import error_missing_required_field

from .dependencies import HandlerDeps


def build_workspace_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def _state_with_active_work_context(
        workspace_id: str,
        state: Dict[str, Any],
        *,
        session_id: str = "",
        source_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        enriched = dict(state or {})
        if deps.work_context_service is not None:
            enriched["active_work_context"] = deps.work_context_service.list_contexts(
                workspace_id,
                status="active",
                limit=8,
            )
        raw_state = source_state if isinstance(source_state, dict) else state
        if session_id and isinstance(raw_state, dict):
            pending_map = raw_state.get("pending_nancy_email_by_session")
            pending = pending_map.get(session_id) if isinstance(pending_map, dict) else None
            if isinstance(pending, dict):
                enriched["pending_nancy_email_compose"] = {
                    str(key): str(value or "") for key, value in pending.items()
                }
            pending_session_create_map = raw_state.get("pending_session_create_by_session")
            pending_session_create = pending_session_create_map.get(session_id) if isinstance(pending_session_create_map, dict) else None
            if isinstance(pending_session_create, dict):
                enriched["pending_session_create"] = {
                    str(key): str(value or "") for key, value in pending_session_create.items()
                }
            pending_rename = pending_session_rename(raw_state, session_id)
            if isinstance(pending_rename, dict):
                enriched["pending_session_rename"] = {
                    str(key): str(value or "") for key, value in pending_rename.items()
                }
            pending_list = pending_session_list(raw_state, session_id)
            if isinstance(pending_list, dict):
                enriched["pending_session_list"] = {
                    str(key): str(value or "") for key, value in pending_list.items()
                }
            pending_workspace_switch_map = raw_state.get("pending_workspace_switch_by_session")
            pending_workspace_switch = pending_workspace_switch_map.get(session_id) if isinstance(pending_workspace_switch_map, dict) else None
            if isinstance(pending_workspace_switch, dict):
                enriched["pending_workspace_switch"] = {
                    str(key): str(value or "") for key, value in pending_workspace_switch.items()
                }
            pending_navigation = pending_room_navigation(raw_state)
            if isinstance(pending_navigation, dict):
                enriched["pending_room_navigation"] = {
                    str(key): str(value or "") for key, value in pending_navigation.items()
                }
            pending_joke = pending_break_room_joke(raw_state, session_id)
            if isinstance(pending_joke, dict):
                enriched["pending_break_room_joke"] = {
                    str(key): str(value or "") for key, value in pending_joke.items()
                }
        return enriched

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
        description = str(args.get("description") or "").strip()
        label_key = label.strip().casefold()
        idx = deps.kernel.list_workspaces()
        for row in idx.get("workspaces", []):
            existing_label = str(row.get("label") or "").strip()
            if existing_label and existing_label.casefold() == label_key:
                workspace_id = str(row.get("workspace_id") or "").strip()
                if workspace_id:
                    if description and not str(row.get("description") or "").strip():
                        deps.kernel.store.update_workspace_metadata(workspace_id, description=description)
                    return deps.pipeline.workspace_new_response(
                        workspace_id,
                        existing_label,
                        description=str(row.get("description") or description or "").strip(),
                    )
        workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
        deps.kernel.create_workspace(workspace_id, label, description=description)
        return deps.pipeline.workspace_new_response(workspace_id, label, description=description)

    def handle_workspace_update(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not workspace_id:
            raise error_missing_required_field("workspace_id")
        label_value = args.get("label")
        description_value = args.get("description")
        label = None if label_value is None else str(label_value).strip()
        description = None if description_value is None else str(description_value).strip()
        if label is None and description is None:
            raise error_missing_required_field("label_or_description")
        row = deps.kernel.store.update_workspace_metadata(
            workspace_id,
            label=label,
            description=description,
        )
        response_label = str(row.get("label") or workspace_id).strip() or workspace_id
        response_description = str(row.get("description") or "").strip()
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "label": response_label,
                "description": response_description,
            },
            "content": [{"type": "text", "text": f"Updated workspace {workspace_id}."}],
        }

    def handle_workspace_activate(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        if not workspace_id:
            raise error_missing_required_field("workspace_id")
        user = deps.user_service.get_user_for_session(session_id)
        result = deps.user_service.activate_workspace(user_id=str(user["user_id"]), workspace_id=workspace_id)
        workspace_state = _state_with_active_work_context(
            workspace_id,
            result["workspace_state"],
            session_id=str(result["session"]["session_id"] or "").strip(),
            source_state=result["workspace_state"],
        )
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

    def handle_workspace_delete(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get("session_id") or "").strip()
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not session_id:
            raise error_missing_required_field("session_id")
        if not workspace_id:
            raise error_missing_required_field("workspace_id")
        user = deps.user_service.get_user_for_session(session_id)
        result = deps.user_service.archive_workspace_for_user(user_id=str(user["user_id"]), workspace_id=workspace_id)
        switched_workspace = bool(result.get("switched_workspace"))
        archived_workspace = result.get("archived_workspace") if isinstance(result, dict) else {}
        archived_label = str((archived_workspace or {}).get("label") or workspace_id).strip() or workspace_id
        response_text = f"Archived workspace {archived_label}."
        if switched_workspace:
            response_text = f"Archived workspace {archived_label}. Switched to {result.get('workspace_id')}."
        return {
            "structuredContent": {
                "workspace_id": result.get("workspace_id"),
                "session_id": result.get("session_id"),
                "archived_workspace": archived_workspace,
                "workspace_state": _state_with_active_work_context(
                    str(result.get("workspace_id") or workspace_id).strip() or workspace_id,
                    result.get("workspace_state") or {},
                    session_id=str(result.get("session_id") or "").strip(),
                    source_state=result.get("workspace_state") or {},
                ),
                "switched_workspace": switched_workspace,
            },
            "content": [{"type": "text", "text": response_text}],
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
        session_id = str(args.get("session_id") or "").strip()
        response = deps.pipeline.snapshot_response(workspace_id)
        structured = response.get("structuredContent")
        source_state = {}
        if deps.kernel is not None:
            try:
                source_state = deps.kernel.get_state(workspace_id)
            except Exception:
                source_state = {}
        if isinstance(structured, dict):
            structured.update(
                _state_with_active_work_context(
                    workspace_id,
                    structured,
                    session_id=session_id,
                    source_state=source_state,
                )
            )
        return response

    def handle_office_transcript_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        session_id = str(args.get("session_id") or "").strip() or None
        room_id = str(args.get("room_id") or "").strip()
        speaker_filter = str(args.get("speaker") or "").strip().casefold()
        role_filter = str(args.get("role") or "").strip().casefold()
        include_system = bool(args.get("include_system", True))
        limit_value = args.get("limit")
        try:
            limit = int(limit_value) if limit_value is not None else 100
        except (TypeError, ValueError):
            limit = 100
        rows = deps.store.load_transcript(workspace_id, limit=max(1, min(limit, 500)), session_id=session_id)
        filtered_rows = []
        for row in rows:
            row_room = str(row.get("room") or "").strip()
            row_role = str(row.get("role") or "").strip()
            row_speaker = str(row.get("speaker") or "").strip()
            if room_id and row_room != room_id:
                continue
            if speaker_filter and row_speaker.casefold() != speaker_filter:
                continue
            if role_filter and row_role.casefold() != role_filter:
                continue
            if not include_system and row_role.casefold() == "system":
                continue
            filtered_rows.append(row)
        if room_id:
            header = f"Transcript entries for {room_id} in this session:"
            empty_text = f"No transcript entries found for {room_id} in this session."
        else:
            header = "Current session thread:"
            empty_text = "Current session thread is empty."
        lines = [header]
        for row in filtered_rows:
            speaker = str(row.get("speaker") or row.get("role") or "Unknown").strip() or "Unknown"
            text = re.sub(r"\s+", " ", str(row.get("text") or "").strip())
            if not text:
                continue
            row_room = str(row.get("room") or "").strip() or "unknown_room"
            ts = str(row.get("ts") or "").strip()
            prefix = f"[{ts}] {row_room} | {speaker}" if ts else f"{row_room} | {speaker}"
            lines.append(f"{prefix}: {text}")
        response_text = "\n".join(lines) if len(lines) > 1 else empty_text
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "session_id": session_id,
                "room_id": room_id,
                "speaker": str(args.get("speaker") or "").strip(),
                "role": str(args.get("role") or "").strip(),
                "include_system": include_system,
                "count": len(filtered_rows),
                "entries": filtered_rows,
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

        response = deps.pipeline.enter_room_response(workspace_id, result)
        structured = response.get("structuredContent")
        if isinstance(structured, dict):
            structured.update(
                _state_with_active_work_context(
                    workspace_id,
                    structured,
                    session_id=str(session_id or "").strip(),
                    source_state=state,
                )
            )
        return response

    def handle_office_nancy_route(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        request_text = str(args.get("request", "")).strip()
        if not request_text:
            raise error_missing_required_field("request")
        return deps.pipeline.nancy_route_response(workspace_id, request_text)

    return {
        "office.workspaces_list": handle_workspaces_list,
        "office.workspace_new": handle_workspace_new,
        "office.workspace_update": handle_workspace_update,
        "office.workspace_activate": handle_workspace_activate,
        "office.workspace_delete": handle_workspace_delete,
        "office.bootstrap": handle_office_bootstrap,
        "office.state_get": handle_office_state_get,
        "office.transcript_get": handle_office_transcript_get,
        "office.commands_list": handle_commands_list,
        "office.room_set": handle_office_room_set,
        "office.nancy_route": handle_office_nancy_route,
    }
