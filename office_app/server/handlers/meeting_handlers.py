from __future__ import annotations

from typing import Any, Dict, Optional

from office_app.server.meeting_state import MeetingStateStore
from office_app.server.models import MeetingState

from .dependencies import HandlerDeps


ACTIVE_MEETING_BY_SESSION_KEY = "active_meeting_by_session"


def build_meeting_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def meeting_store(workspace_id: str) -> MeetingStateStore:
        return MeetingStateStore(deps.store.workspace_dir(workspace_id) / "meetings")

    def session_key(args: Dict[str, Any]) -> str:
        return str(args.get("session_id") or "").strip() or "__default__"

    def serialize(st: MeetingState) -> Dict[str, Any]:
        return st.model_dump()

    def set_active_meeting(workspace_id: str, args: Dict[str, Any], meeting_id: str) -> None:
        state = deps.store.load_state(workspace_id)
        active_map = dict(state.get(ACTIVE_MEETING_BY_SESSION_KEY) or {})
        active_map[session_key(args)] = meeting_id
        state[ACTIVE_MEETING_BY_SESSION_KEY] = active_map
        deps.store.save_state(workspace_id, state)

    def active_meeting_id(workspace_id: str, args: Dict[str, Any]) -> str:
        explicit = str(args.get("meeting_id") or "").strip()
        if explicit:
            return explicit
        state = deps.store.load_state(workspace_id)
        active_map = state.get(ACTIVE_MEETING_BY_SESSION_KEY) or {}
        if isinstance(active_map, dict):
            return str(active_map.get(session_key(args)) or "").strip()
        return ""

    def start_required_response(workspace_id: str) -> Dict[str, Any]:
        structured = {
            "workspace_id": workspace_id,
            "needs_meeting": True,
            "response_text": "Start a meeting first, then add agenda items, decisions, action items, or parking-lot items.",
        }
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": structured["response_text"]}],
        }

    def load_active_meeting(workspace_id: str, args: Dict[str, Any]) -> Optional[MeetingState]:
        meeting_id = active_meeting_id(workspace_id, args)
        if not meeting_id:
            return None
        return meeting_store(workspace_id).load(meeting_id)

    def response(workspace_id: str, st: MeetingState, response_text: str) -> Dict[str, Any]:
        structured = {
            **serialize(st),
            "workspace_id": workspace_id,
            "response_text": response_text,
        }
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_start(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.meeting_state_start", args)
        title = str(args.get("title") or "").strip()
        st = meeting_store(workspace_id).create(room_id="conference_room", title=title)
        set_active_meeting(workspace_id, args, st.meeting_id)
        label = f" for {st.title}" if st.title else ""
        return response(
            workspace_id,
            st,
            f"Started internal meeting state{label}. No calendar event was created.",
        )

    def append_item(tool_name: str, args: Dict[str, Any], field: str, label: str) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id(tool_name, args)
        item = str(args.get("item") or "").strip()
        if not item:
            raise deps.error_missing_required_field("item")
        st = load_active_meeting(workspace_id, args)
        if st is None:
            return start_required_response(workspace_id)
        values = list(getattr(st, field))
        values.append(item)
        setattr(st, field, values)
        meeting_store(workspace_id).save(st)
        return response(workspace_id, st, f"Added {label}: {item}")

    def handle_add_agenda(args: Dict[str, Any]) -> Dict[str, Any]:
        return append_item("office.meeting_state_add_agenda", args, "agenda", "agenda item")

    def handle_record_decision(args: Dict[str, Any]) -> Dict[str, Any]:
        return append_item("office.meeting_state_record_decision", args, "decisions", "decision")

    def handle_add_action_item(args: Dict[str, Any]) -> Dict[str, Any]:
        return append_item("office.meeting_state_add_action_item", args, "action_items", "action item")

    def handle_add_parking_lot(args: Dict[str, Any]) -> Dict[str, Any]:
        return append_item("office.meeting_state_add_parking_lot", args, "parking_lot", "parking-lot item")

    def handle_show(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.meeting_state_show", args)
        st = load_active_meeting(workspace_id, args)
        if st is None:
            return start_required_response(workspace_id)
        counts = (
            f"{len(st.agenda)} agenda, {len(st.decisions)} decision, "
            f"{len(st.action_items)} action, {len(st.parking_lot)} parking-lot item(s)"
        )
        return response(workspace_id, st, f"Current meeting state: {counts}.")

    return {
        "office.meeting_state_start": handle_start,
        "office.meeting_state_add_agenda": handle_add_agenda,
        "office.meeting_state_record_decision": handle_record_decision,
        "office.meeting_state_add_action_item": handle_add_action_item,
        "office.meeting_state_add_parking_lot": handle_add_parking_lot,
        "office.meeting_state_show": handle_show,
    }
