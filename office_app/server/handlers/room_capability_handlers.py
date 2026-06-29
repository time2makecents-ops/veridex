from __future__ import annotations

from typing import Any, Dict

from .dependencies import HandlerDeps


def build_room_capability_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_room_capabilities(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.room_capabilities", args)
        state = deps.kernel.get_state(workspace_id)
        requested_room = str(args.get("room_id") or args.get("room") or "").strip()
        room_id = requested_room or str(state.get("active_room") or "lobby").strip() or "lobby"
        profile = deps.room_capability_registry.profile_for_room(room_id).as_dict()
        text = (
            f"{profile['room_id']} capabilities: {', '.join(profile['primary_capabilities']) or 'none listed'}. "
            f"Allowed tools: {len(profile['allowed_tools'])}. "
            f"Preferred collaborators: {', '.join(profile['preferred_collaborators']) or 'none'}. "
            f"Approval boundaries: {', '.join(profile['approval_required_for']) or 'none'}."
        )
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "profile": profile,
            },
            "content": [{"type": "text", "text": text}],
        }

    return {"office.room_capabilities": handle_room_capabilities}
