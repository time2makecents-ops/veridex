from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from office_app.server.request_response_helpers import attach_request_context, request_text_from_response
from office_app.server.request_transcript import record_assistant_turn
from office_app.server.search_response_synthesis import handle_search_tool_result


def execute_tool_route(
    *,
    routed: Dict[str, Any],
    workspace_id: str,
    session_id: str,
    user_profile: Optional[Dict[str, Any]],
    kernel: Any,
    store: Any,
    router: Any,
    receptionist_context_service: Any,
    utc_now: Callable[[], str],
    apply_navigator_activation: Callable[..., Dict[str, Any]],
    set_pending_workspace_switch: Callable[[Dict[str, Any], str, str, str], Dict[str, Any]],
    response_speaker: Callable[[Dict[str, Any]], Optional[str]],
) -> Dict[str, Any]:
    args = dict(routed["arguments"])
    args["workspace_id"] = workspace_id
    if session_id:
        args["session_id"] = session_id
    result = handle_search_tool_result(
        routed=routed,
        dispatch_tool=lambda: router.dispatch_capability(
            routed["capability"],
            args,
            preferred_tool=routed.get("tool"),
        ),
        workspace_id=workspace_id,
        session_id=session_id,
        user_profile=user_profile,
        kernel=kernel,
        store=store,
        router=router,
        request_text_from_response=request_text_from_response,
        utc_now=utc_now,
        apply_navigator_activation=apply_navigator_activation,
    )
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and not isinstance(structured.get("routing"), dict):
            structured["routing"] = {
                "route_kind": "tool",
                "capability": routed["capability"],
                "tool": routed["tool"],
                "reason": routed["reason"],
            }
    enriched = attach_request_context(result, workspace_id=workspace_id, session_id=session_id)
    structured = (enriched or {}).get("structuredContent") if isinstance(enriched, dict) else None
    routing = (structured or {}).get("routing") if isinstance(structured, dict) else None
    if isinstance(routing, dict) and str(routing.get("route_kind") or "").strip().lower() == "clarify":
        response_text = request_text_from_response(enriched)
        record_assistant_turn(
            workspace_id=workspace_id,
            session_id=session_id,
            response_text=response_text,
            kernel=kernel,
            store=store,
            receptionist_context_service=receptionist_context_service,
            user_profile=user_profile,
            speaker=response_speaker(enriched),
        )
        return enriched
    if str(routed.get("capability") or "").strip() == "workspace.create":
        structured = (enriched or {}).get("structuredContent") if isinstance(enriched, dict) else None
        created_workspace_id = str((structured or {}).get("workspace_id") or "").strip()
        created_label = str((structured or {}).get("label") or created_workspace_id).strip() or created_workspace_id
        if created_workspace_id and session_id:
            current_state = kernel.get_state(workspace_id)
            current_state = set_pending_workspace_switch(
                current_state,
                session_id,
                created_workspace_id,
                created_label,
            )
            store.save_state(workspace_id, current_state)
            response_text = (
                f'Created workspace "{created_label}" ({created_workspace_id}). '
                "Do you want to switch to it now? I will start a new session there."
            )
            response = {
                "structuredContent": {
                    **(structured or {}),
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "created_workspace_id": created_workspace_id,
                    "created_workspace_label": created_label,
                    "pending_workspace_switch": {
                        "workspace_id": created_workspace_id,
                        "label": created_label,
                        "ts": utc_now(),
                    },
                    "response_text": response_text,
                    "routing": {
                        "route_kind": "clarify",
                        "capability": "workspace.switch.confirmation",
                        "tool": "office.capability_info",
                        "reason": "Created a workspace and requested switch confirmation.",
                    },
                },
                "content": [{"type": "text", "text": response_text}],
            }
            enriched = attach_request_context(response, workspace_id=workspace_id, session_id=session_id)
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
