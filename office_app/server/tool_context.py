from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ToolContext:
    tool_name: str
    capability: str
    workspace_id: str = ""
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    active_room: Optional[str] = None
    active_persona: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
