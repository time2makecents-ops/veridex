from __future__ import annotations

from typing import Any, Optional


def record_user_turn(
    *,
    workspace_id: str,
    session_id: str,
    request_text: str,
    kernel: Any,
    store: Any,
    receptionist_context_service: Any,
    user_profile: Optional[dict[str, Any]],
) -> None:
    current_state = kernel.get_state(workspace_id)
    active_room = str(current_state.get("active_room") or "lobby")
    active_persona = current_state.get("active_persona", "Receptionist")
    receptionist_context_service.record_turn(
        workspace_id=workspace_id,
        role="user",
        text=request_text,
        room_id=active_room,
        persona_name=active_persona,
        user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
        session_id=session_id,
    )
    store.append_transcript(
        workspace_id,
        "user",
        active_room,
        request_text,
        speaker="You",
        session_id=session_id,
    )


def record_assistant_turn(
    *,
    workspace_id: str,
    session_id: str,
    response_text: str,
    kernel: Any,
    store: Any,
    receptionist_context_service: Any,
    user_profile: Optional[dict[str, Any]],
    speaker: Optional[str] = None,
    room_id: Optional[str] = None,
    persona_name: Optional[str] = None,
) -> None:
    current_state = kernel.get_state(workspace_id)
    active_room = str(room_id or current_state.get("active_room") or "lobby")
    active_persona = str(persona_name or current_state.get("active_persona") or "Receptionist")
    active_speaker = str(speaker or active_persona or "Receptionist")
    receptionist_context_service.record_turn(
        workspace_id=workspace_id,
        role="assistant",
        text=response_text,
        room_id=active_room,
        persona_name=active_persona,
        user_id=str((user_profile or {}).get("user_id") or "").strip() or None,
        session_id=session_id,
    )
    store.append_transcript(
        workspace_id,
        "assistant",
        active_room,
        response_text,
        speaker=active_speaker,
        session_id=session_id,
    )
