from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


EntityRequestExtractor = Callable[[str], Optional[Dict[str, Any]]]
TranscriptTurnLoader = Callable[[str, Optional[str]], List[Dict[str, Any]]]
ActiveRoomTitleResolver = Callable[[str], str]


class EntityGroundingRouter:
    def __init__(
        self,
        *,
        extract_factual_entity_request: EntityRequestExtractor,
        load_recent_transcript_turns: TranscriptTurnLoader,
        resolve_active_room_title: Optional[ActiveRoomTitleResolver] = None,
    ) -> None:
        self.extract_factual_entity_request = extract_factual_entity_request
        self.load_recent_transcript_turns = load_recent_transcript_turns
        self.resolve_active_room_title = resolve_active_room_title or (lambda _workspace_id: "current department")

    def _room_phrase(self, workspace_id: str) -> str:
        room_title = re.sub(r"\s+", " ", str(self.resolve_active_room_title(workspace_id) or "").strip())
        if not room_title:
            return "the current department"
        if room_title.lower().startswith("the "):
            return room_title
        return f"the {room_title}"

    def unknown_entity_response_text(self, workspace_id: str, entity_subject: str) -> str:
        room_phrase = self._room_phrase(workspace_id)
        return (
            f"Veridex doesn't have any verified information about {entity_subject}. "
            f"Have {room_phrase} do an internet search or search your other sessions if you want to know more."
        )

    def entity_has_verified_grounding(
        self,
        workspace_id: str,
        entity_subject: str,
        *,
        session_id: Optional[str] = None,
    ) -> bool:
        turns = self.load_recent_transcript_turns(workspace_id, session_id)
        if not turns:
            return False
        subject = str(entity_subject or "").strip()
        if not subject:
            return False
        subject_lower = subject.lower()
        tokens = [token for token in re.findall(r"[a-z0-9]{3,}", subject_lower) if token not in {"the", "and"}]
        if not tokens:
            tokens = [subject_lower]
        for turn in turns[-24:]:
            role = str(turn.get("role") or "").strip().lower()
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if subject_lower not in lowered and not all(token in lowered for token in tokens):
                continue
            if role == "user":
                if "?" not in text or re.search(
                    r"\b(is|was|are|were|sold|located|based|founded|operate|operated|started|start|had|have|work|live)\b",
                    lowered,
                ):
                    return True
                continue
            if role in {"assistant", "system"} and any(
                marker in text for marker in ("URL:", "Source:", "Address:", "Web results for", "Review-oriented results", "Place results")
            ):
                return True
        return False

    def route_factual_entity_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        entity_request = self.extract_factual_entity_request(request_text)
        if entity_request is None:
            return None
        entity_subject = str(entity_request["entity_subject"])
        if entity_request["search_requested"]:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "search.web",
                "tool": "office.search_web",
                "arguments": {
                    "query": entity_subject,
                    "limit": 5,
                },
                "reason": "Explicit search requested for a specific entity.",
                "grounding_required": True,
                "entity_subject": entity_subject,
            }
        if self.entity_has_verified_grounding(workspace_id, entity_subject, session_id=session_id):
            return None
        return {
            "route_kind": "clarify",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": "clarification.entity_grounding",
            "tool": "office.capability_info",
            "arguments": {
                "response_text": self.unknown_entity_response_text(workspace_id, entity_subject),
                "entity_subject": entity_subject,
            },
            "reason": "Specific entity lookup has no verified grounding in the current workspace/session context.",
        }
