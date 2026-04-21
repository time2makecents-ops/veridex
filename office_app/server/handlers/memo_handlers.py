from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException

from office_app.server.guards import ensure_single_target

from .dependencies import HandlerDeps


def build_memo_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_mailroom_dispatch(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        for field in ("to_room", "body"):
            if field not in args:
                raise deps.error_missing_required_field(field)

        to_room_raw = str(args["to_room"])
        ensure_single_target(to_room_raw)
        if "," in to_room_raw or " and " in to_room_raw.lower() or "&" in to_room_raw:
            raise HTTPException(status_code=400, detail="One memo may target only one room. Send separate memos.")

        body = str(args["body"]).strip()
        explicit_persona = str(args.get("explicit_persona", "")).strip() or None

        state = deps.kernel.get_state(workspace_id)
        from_room_external = state.get("active_room", "lobby")
        memo_result = deps.memo_service.dispatch_memo(
            workspace_id=workspace_id,
            from_room=from_room_external,
            to_room=to_room_raw,
            body=body,
            explicit_persona=explicit_persona,
            policy_check_fn=deps.pipeline.assert_mailroom_allowed,
        )

        deps.append_incident(
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
            evidence_path=str(deps.store.memos_dir(workspace_id)),
            notes="Recorded memo dispatch (single-target).",
            state_sha256=deps.stable_state_sha(state),
        )

        return deps.pipeline.mailroom_response(
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
        rows = deps.memo_service.list_memos(workspace_id, limit=limit)
        return deps.pipeline.memos_list_response(workspace_id, rows)

    def handle_memo_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        memo_id = str(args.get("memo_id", "")).strip()
        if not memo_id:
            raise deps.error_missing_required_field("memo_id")

        obj, body = deps.memo_service.get_memo(workspace_id, memo_id)
        return deps.pipeline.memo_get_response(obj, body)

    return {
        "mailroom.dispatch": handle_mailroom_dispatch,
        "office.memos_list": handle_memos_list,
        "office.memo_get": handle_memo_get,
    }
