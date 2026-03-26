from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from office_app.server.models import MeetingState


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MeetingStateStore:
    """
    Phase-2: file-backed meeting state (optional use).
    This is scaffolding; not wired into app.py yet.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create(self, room_id: str = "conference_room") -> MeetingState:
        mid = f"MEET-{uuid.uuid4()}"
        now = utc_now()
        st = MeetingState(
            meeting_id=mid,
            room_id=room_id,
            agenda=[],
            parking_lot=[],
            decisions=[],
            action_items=[],
            created_utc=now,
            updated_utc=now,
        )
        self.save(st)
        return st

    def load(self, meeting_id: str) -> Optional[MeetingState]:
        path = self.base_dir / f"{meeting_id}.json"
        if not path.exists():
            return None
        return MeetingState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, st: MeetingState) -> None:
        st.updated_utc = utc_now()
        path = self.base_dir / f"{st.meeting_id}.json"
        path.write_text(st.model_dump_json(indent=2), encoding="utf-8")
