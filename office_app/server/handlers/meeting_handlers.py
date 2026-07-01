from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from office_app.server.meeting_state import MeetingStateStore
from office_app.server.model_router import ModelRoutingError
from office_app.server.models import MeetingState

from .dependencies import HandlerDeps


ACTIVE_MEETING_BY_SESSION_KEY = "active_meeting_by_session"
MEETING_SECTIONS = {
    "agenda": ("agenda", "Agenda"),
    "decisions": ("decisions", "Decisions"),
    "action_items": ("action_items", "Action Items"),
    "parking_lot": ("parking_lot", "Parking Lot"),
}


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

    def require_active_meeting(workspace_id: str, args: Dict[str, Any]) -> MeetingState:
        st = load_active_meeting(workspace_id, args)
        if st is None:
            raise HTTPException(status_code=404, detail="Start a meeting first.")
        return st

    def section_field(section: Any) -> str:
        normalized = str(section or "").strip().lower()
        if normalized not in MEETING_SECTIONS:
            raise HTTPException(status_code=400, detail=f"Unknown meeting section: {section}")
        return MEETING_SECTIONS[normalized][0]

    def item_index(args: Dict[str, Any], values: List[str]) -> int:
        raw_index = args.get("index")
        if raw_index is None:
            raise deps.error_missing_required_field("index")
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Meeting item index must be a number.") from exc
        if index < 0 or index >= len(values):
            raise HTTPException(status_code=404, detail=f"Meeting item not found at index {index}.")
        return index

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

    def handle_update_title(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.meeting_state_update_title", args)
        title = str(args.get("title") or "").strip()
        if not title:
            raise deps.error_missing_required_field("title")
        st = require_active_meeting(workspace_id, args)
        st.title = title
        meeting_store(workspace_id).save(st)
        return response(workspace_id, st, f"Updated meeting title: {title}")

    def handle_update_item(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.meeting_state_update_item", args)
        item = str(args.get("item") or "").strip()
        if not item:
            raise deps.error_missing_required_field("item")
        st = require_active_meeting(workspace_id, args)
        field = section_field(args.get("section"))
        values = list(getattr(st, field))
        index = item_index(args, values)
        values[index] = item
        setattr(st, field, values)
        meeting_store(workspace_id).save(st)
        return response(workspace_id, st, f"Updated {field} item {index + 1}: {item}")

    def handle_delete_item(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.meeting_state_delete_item", args)
        st = require_active_meeting(workspace_id, args)
        field = section_field(args.get("section"))
        values = list(getattr(st, field))
        index = item_index(args, values)
        removed = values.pop(index)
        setattr(st, field, values)
        meeting_store(workspace_id).save(st)
        return response(workspace_id, st, f"Deleted {field} item {index + 1}: {removed}")

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

    def deterministic_brief(st: MeetingState) -> str:
        title = st.title or "Untitled Meeting"
        lines = [
            f"# Meeting Brief: {title}",
            "",
            f"Meeting ID: {st.meeting_id}",
            f"Room: {st.room_id}",
            f"Created: {st.created_utc}",
            f"Updated: {st.updated_utc}",
            "",
        ]
        for field, heading in [
            ("agenda", "Agenda"),
            ("decisions", "Decisions"),
            ("action_items", "Action Items"),
            ("parking_lot", "Parking Lot"),
        ]:
            lines.append(f"## {heading}")
            values = [str(item).strip() for item in getattr(st, field) if str(item).strip()]
            if values:
                lines.extend(f"- {item}" for item in values)
            else:
                lines.append("- None")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def create_brief_artifact(
        *,
        workspace_id: str,
        st: MeetingState,
        content: str,
        artifact_type: str,
        mode: str,
        source_artifact_id: str = "",
    ) -> Dict[str, Any]:
        title = st.title or "Untitled Meeting"
        metadata = {
            "meeting_id": st.meeting_id,
            "brief_mode": mode,
            "room_id": st.room_id,
        }
        source_refs: List[Dict[str, str]] = [{"kind": "meeting_state", "meeting_id": st.meeting_id}]
        if source_artifact_id:
            metadata["source_artifact_id"] = source_artifact_id
            source_refs.append({"kind": "artifact", "artifact_id": source_artifact_id})
        return deps.archive_service.create_artifact(
            workspace_id=workspace_id,
            type=artifact_type,
            title=f"{title} {'Polished ' if mode == 'polished' else ''}Meeting Brief".replace("  ", " ").strip(),
            content=content,
            format="text/markdown",
            status="active",
            created_by="conference_room",
            metadata=metadata,
            source_refs=source_refs,
        )

    def polished_brief(workspace_id: str, st: MeetingState, deterministic_text: str, args: Dict[str, Any]) -> str:
        try:
            result = deps.model_router.generate_response(
                system_prompt=(
                    "You are Veridex's Conference Room brief composer. "
                    "Rewrite meeting notes into concise, polished Markdown. "
                    "Preserve factual content, do not invent attendees, dates, owners, or decisions, "
                    "and keep clear sections for agenda, decisions, action items, and parking lot."
                ),
                user_prompt=f"Polish this meeting brief without adding facts:\n\n{deterministic_text}",
                context={
                    "workspace_id": workspace_id,
                    "meeting_id": st.meeting_id,
                    "active_room": "conference_room",
                    "session_id": str(args.get("session_id") or "").strip(),
                },
                settings={"provider_by_task_type": {"composition": "gemini"}},
                task_type="composition",
            )
        except ModelRoutingError as exc:
            attempts = "; ".join(str(item).strip() for item in exc.attempts if str(item).strip())
            detail = f"{exc} Attempts: {attempts}" if attempts else str(exc)
            raise HTTPException(status_code=503, detail=detail) from exc
        return str(result.text or "").strip()

    def handle_brief_save(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.meeting_brief_save", args)
        st = require_active_meeting(workspace_id, args)
        mode = str(args.get("mode") or "deterministic").strip().lower() or "deterministic"
        deterministic_text = deterministic_brief(st)
        if mode == "deterministic":
            artifact = create_brief_artifact(
                workspace_id=workspace_id,
                st=st,
                content=deterministic_text,
                artifact_type="meeting_brief",
                mode="deterministic",
            )
        elif mode == "polished":
            content = polished_brief(workspace_id, st, deterministic_text, args)
            if not content:
                raise HTTPException(status_code=502, detail="AI polish returned an empty meeting brief.")
            artifact = create_brief_artifact(
                workspace_id=workspace_id,
                st=st,
                content=content,
                artifact_type="meeting_brief_polished",
                mode="polished",
                source_artifact_id=str(args.get("source_artifact_id") or "").strip(),
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown meeting brief mode: {mode}")
        structured = {
            "workspace_id": workspace_id,
            "meeting": serialize(st),
            "artifact": artifact,
            "mode": mode,
            "response_text": f"Saved {mode} meeting brief: {artifact.get('display_name') or artifact.get('title')}.",
        }
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": structured["response_text"]}],
        }

    return {
        "office.meeting_state_start": handle_start,
        "office.meeting_state_add_agenda": handle_add_agenda,
        "office.meeting_state_record_decision": handle_record_decision,
        "office.meeting_state_add_action_item": handle_add_action_item,
        "office.meeting_state_add_parking_lot": handle_add_parking_lot,
        "office.meeting_state_update_title": handle_update_title,
        "office.meeting_state_update_item": handle_update_item,
        "office.meeting_state_delete_item": handle_delete_item,
        "office.meeting_state_show": handle_show,
        "office.meeting_brief_save": handle_brief_save,
    }
