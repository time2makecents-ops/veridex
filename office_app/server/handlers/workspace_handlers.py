from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from office_app.server.errors import error_missing_required_field

from .dependencies import HandlerDeps


def build_workspace_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_workspaces_list(_: Dict[str, Any]) -> Dict[str, Any]:
        idx = deps.kernel.list_workspaces()
        return deps.pipeline.workspaces_list_response(idx)

    def handle_workspace_new(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
        label = str(args.get("label") or f"Workspace {deps.utc_now()}")
        deps.kernel.create_workspace(workspace_id, label)
        return deps.pipeline.workspace_new_response(workspace_id, label)

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
        room_id = str(args.get("room_id", "")).strip()
        if not room_id:
            raise error_missing_required_field("room_id")

        result = deps.kernel.enter_room(workspace_id, room_id)
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
        "office.bootstrap": handle_office_bootstrap,
        "office.state_get": handle_office_state_get,
        "office.commands_list": handle_commands_list,
        "office.room_set": handle_office_room_set,
        "office.nancy_route": handle_office_nancy_route,
    }
