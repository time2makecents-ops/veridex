from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from office_app.server.persona_registry import PersonaRegistry, build_default_registry


@dataclass(frozen=True)
class RouteResult:
    to_room: str
    to_persona: str


class RoomRouter:
    """Phase-2: routing only.
    - Determines destination persona for a room.
    - Does not generate responses.
    """

    def __init__(self, registry: Optional[PersonaRegistry] = None) -> None:
        self.registry = registry or build_default_registry()

    def resolve_persona(self, room_id: str) -> RouteResult:
        spec = self.registry.get_for_room(room_id)
        if not spec:
            # Fail-closed: unknown room => no routing decision
            raise ValueError(f"No persona registered for room_id: {room_id}")
        return RouteResult(to_room=room_id, to_persona=spec.name)
