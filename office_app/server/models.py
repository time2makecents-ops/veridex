from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Memo(BaseModel):
    memo_id: str
    from_room: str
    to_room: str
    to_persona: str
    subject: str
    body: str
    created_utc: str
    thread_id: Optional[str] = None
    reply_text: Optional[str] = None
    replied_utc: Optional[str] = None
    reply_room: Optional[str] = None
    reply_persona: Optional[str] = None
    reply_is_refusal: bool = False
    reply_closure_appended: bool = False


class MeetingState(BaseModel):
    meeting_id: str
    room_id: str = "conference_room"
    title: str = ""
    agenda: List[str] = Field(default_factory=list)
    parking_lot: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    created_utc: str
    updated_utc: str


class PersonaResponse(BaseModel):
    persona: str
    room_id: str
    response_text: str
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
