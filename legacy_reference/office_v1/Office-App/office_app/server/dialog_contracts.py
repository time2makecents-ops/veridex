from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DialogContract:
    """
    Phase-2 scaffolding contract.

    This file defines constraints and return-shapes, not dialog content.
    """

    # Common constraints (enforced later)
    no_questions_default: bool = True
    allow_questions_when_flagged: bool = True
    single_target_memos_only: bool = True

    # Optional standardized closure behavior
    allow_closure_line: bool = True
    closure_line: str = "If further review is needed, see me in my office, or send a detailed memo."

    # Lobby onboarding suggestion (no script here)
    lobby_suggest_onboarding: bool = True
    onboarding_room_id: str = "conference_room"


DEFAULT_CONTRACT = DialogContract()
