from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from office_app.server.conversation_planner import ConversationPlanner
from office_app.server.search_response_synthesis import (
    grounded_entity_followup_response,
    grounded_search_followup_response,
)


ModelRouteFn = Callable[..., Dict[str, Any]]
LocationExtractorFn = Callable[[str], Optional[str]]
GroundedSearchLoaderFn = Callable[[str, Optional[str]], Optional[Dict[str, Any]]]


RECENT_ENTITY_PATTERNS = (
    re.compile(
        r"\b(?:search|look(?:\s+through)?|check|scan)\s+(?:my\s+|the\s+)?(?:(?:other|all)\s+)?sessions\b(?:\s+(?:for|about)\s+\"?(.+?)\"?)?(?=[.?!](?:\s|$)|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bverified information about\s+\"?(.+?)\"?(?=[.?!](?:\s|$)|\s+if\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsearch(?:\s+the\s+(?:web|internet))?\s+for\s+(?:more information about\s+)?\"?(.+?)\"?(?=[.?!](?:\s|$)|\s+if\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat can you tell me about\s+\"?(.+?)\"?(?=[.?!](?:\s|$)|\s+if\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btell me about\s+\"?(.+?)\"?(?=[.?!](?:\s|$)|\s+if\b|$)",
        re.IGNORECASE,
    ),
)

SESSION_SEARCH_REQUEST_RE = re.compile(
    r"^(?:search|look(?:\s+through)?|check|scan)\s+(?:my\s+|the\s+)?(?:(other|all)\s+)?sessions\b(?:\s+(?:for|about)\s+(.+?))?\??$",
    re.IGNORECASE,
)
SESSION_SEARCH_DETAIL_RE = re.compile(
    r"^(?:can\s+you\s+)?(?:list|show|display|summarize|tell\s+me)\s+(?:the\s+)?"
    r"(?:information|details|results|responses|answers)"
    r"(?:\s+(?:it|you)\s+(?:gave|found|said))?"
    r"(?:\s+(?:from|in|for))?\s+(?:those|the)\s+sessions\b.*$"
    r"|^what\s+(?:information|details|results)\s+(?:did\s+)?(?:it|you)\s+(?:give|find|say)\s+in\s+(?:those|the)\s+sessions\b.*$"
    r"|^what\s+did\s+(?:it|you)\s+say\s+in\s+(?:those|the)\s+sessions\b.*$"
    r"|^(?:relook|look\s+again|recheck|check\s+again).*(?:sessions|results)\b.*$"
    r"|^(?:send|show|display)\s+me\s+(?:the\s+)?results\b.*$",
    re.IGNORECASE,
)
SESSION_SEARCH_GENERIC_RE = re.compile(
    r"^(?:search|look(?:\s+through)?|check|scan)\s+(?:the\s+)?sessions(?:\s+in\s+.+)?\??$",
    re.IGNORECASE,
)
SESSION_ITEM_FULL_RE = re.compile(
    r"^(?:can\s+you\s+)?(?:show|display|give|tell)(?:\s+me)?(?:\s+the)?\s+"
    r"(?:rest|full|whole|complete)(?:\s+(?:answer|response|info(?:rmation)?|details?|results?))?"
    r"(?:\s+(?:of|for|from))?\s*(?:number\s+|#)?(\d+)\b.*$",
    re.IGNORECASE,
)
SESSION_ITEM_DETAIL_RE = re.compile(
    r"^(?:can\s+you\s+)?(?:show|display|give|list|tell)(?:\s+me)?(?:\s+the)?(?:\s+rest\s+of)?"
    r"(?:\s+information|\s+info|\s+details|\s+results|\s+response|\s+answer)?(?:\s+from)?\s+(?:number\s+|#)(\d+)\b.*$",
    re.IGNORECASE,
)


class RequestFollowupRouter:
    def __init__(
        self,
        *,
        conversation_planner: ConversationPlanner,
        model_route: ModelRouteFn,
        extract_location: LocationExtractorFn,
        load_grounded_search_context: GroundedSearchLoaderFn,
    ) -> None:
        self.conversation_planner = conversation_planner
        self.model_route = model_route
        self.extract_location = extract_location
        self.load_grounded_search_context = load_grounded_search_context

    @staticmethod
    def _candidate_entity_subject(text: str) -> str:
        if not text:
            return ""
        for pattern in RECENT_ENTITY_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            subject = re.sub(r"\s+", " ", str(match.group(1) or "").strip(" .,:;?!\"'"))
            subject = re.split(r"[.?!](?:\s|$)", subject, maxsplit=1)[0].strip(" .,:;?!\"'")
            subject = re.sub(r"\s+(?:if you'd like.*|if you want.*|and give me information.*)$", "", subject, flags=re.IGNORECASE)
            subject = re.sub(r"\s+information$", "", subject, flags=re.IGNORECASE).strip(" .,:;?!\"'")
            subject = re.sub(r"\s+\d+$", "", subject).strip(" .,:;?!\"'")
            if subject:
                return subject
        return ""

    @staticmethod
    def _normalize_session_query(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "").strip(" .,:;?!"))
        text = re.sub(r"^(?:info(?:rmation)?|references?|mentions?)\s+(?:about|for|to)\s+", "", text, flags=re.IGNORECASE)
        if text.lower().endswith(" information"):
            text = text[:-12].rstrip(" .,:;?!")
        return text

    @classmethod
    def _recent_entity_subject(cls, recent_turns: List[Dict[str, Any]]) -> str:
        for turn in reversed(recent_turns[-12:]):
            if str(turn.get("role") or "").strip().lower() != "user":
                continue
            text = re.sub(r"\s+", " ", str(turn.get("text") or "").strip())
            if not text:
                continue
            subject = cls._candidate_entity_subject(text)
            if subject:
                return subject
        for turn in reversed(recent_turns[-12:]):
            if str(turn.get("role") or "").strip().lower() == "user":
                continue
            text = re.sub(r"\s+", " ", str(turn.get("text") or "").strip())
            if not text or "matching session(s)" in text.lower():
                continue
            subject = cls._candidate_entity_subject(text)
            if subject:
                return subject
        return ""

    @staticmethod
    def _recent_session_search_context(recent_turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        query_from_assistant = ""
        include_current = True
        matches: List[Dict[str, Any]] = []
        for turn in reversed(recent_turns[-12:]):
            role = str(turn.get("role") or "").strip().lower()
            text = re.sub(r"\s+", " ", str(turn.get("text") or "").strip())
            if not text:
                continue
            if role == "user":
                match = SESSION_SEARCH_REQUEST_RE.match(text)
                if not match:
                    continue
                include_current = str(match.group(1) or "").strip().lower() != "other"
                query = RequestFollowupRouter._normalize_session_query(str(match.group(2) or ""))
                if query:
                    return {
                        "query": query,
                        "include_current": include_current,
                        "matches": matches,
                    }
            if not query_from_assistant:
                assistant_match = re.search(r'matching session\(s\) for "([^"]+)"', text, re.IGNORECASE)
                if assistant_match:
                    query_from_assistant = RequestFollowupRouter._normalize_session_query(assistant_match.group(1))
            if not matches and "matching session(s) for" in text.lower():
                parsed_matches: List[Dict[str, Any]] = []
                for match_row in re.finditer(r"(?m)^\s*(\d+)\.\s+(?:Session:\s+)?(.+?)\s+\((sess_[^)]+)\)", str(turn.get("text") or "")):
                    parsed_matches.append(
                        {
                            "index": int(match_row.group(1)),
                            "title": re.sub(r"\s+", " ", match_row.group(2).strip()),
                            "session_id": match_row.group(3),
                        }
                    )
                matches = parsed_matches
        return {
            "query": query_from_assistant,
            "include_current": include_current,
            "matches": matches,
        }

    def route_contextual_followup(
        self,
        workspace_id: str,
        request_text: str,
        recent_turns: List[Dict[str, Any]],
        *,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        text = request_text.strip()
        lowered = text.lower()
        recent_session_search = self._recent_session_search_context(recent_turns)
        recent_entity_subject = self._recent_entity_subject(recent_turns)
        item_match = SESSION_ITEM_FULL_RE.match(text) or SESSION_ITEM_DETAIL_RE.match(text)
        if item_match:
            session_items = recent_session_search.get("matches") or []
            target = next(
                (
                    item for item in session_items
                    if int(item.get("index") or 0) == int(item_match.group(1))
                ),
                None,
            )
            query = re.sub(r"\s+", " ", str(recent_session_search.get("query") or "").strip(" .,:;?!")) or recent_entity_subject
            if target and query:
                expand_full = bool(SESSION_ITEM_FULL_RE.match(text))
                return {
                    "route_kind": "tool",
                    "workspace_id": workspace_id,
                    "request": request_text,
                    "capability": "session.search",
                    "tool": "office.sessions_search",
                    "arguments": {
                        "query": query,
                        "include_current": bool(recent_session_search.get("include_current")),
                        "detail": True,
                        "target_session_id": str(target.get("session_id") or "").strip(),
                        "expand_full": expand_full,
                    },
                    "reason": "Expanded a selected session-search result into its stored answer.",
                }
        if SESSION_SEARCH_DETAIL_RE.match(text):
            query = re.sub(r"\s+", " ", str(recent_session_search.get("query") or "").strip(" .,:;?!"))
            if not query:
                query = recent_entity_subject
            if query:
                return {
                    "route_kind": "tool",
                    "workspace_id": workspace_id,
                    "request": request_text,
                    "capability": "session.search",
                    "tool": "office.sessions_search",
                    "arguments": {
                        "query": query,
                        "include_current": bool(recent_session_search.get("include_current")),
                        "detail": True,
                    },
                    "reason": "Expanded the latest session-search result into detailed session excerpts.",
                }
        grounded_context = self.load_grounded_search_context(workspace_id, session_id)
        grounded_context_response = grounded_search_followup_response(request_text, grounded_context or {})
        if grounded_context_response is not None:
            return {
                "route_kind": "clarify",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "clarification.entity_followup",
                "tool": "office.capability_info",
                "arguments": {
                    "response_text": grounded_context_response,
                },
                "reason": "Answered a grounded search follow-up from preserved search result evidence.",
            }
        if lowered in {"search", "search it", "look it up", "look that up"} and recent_entity_subject:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "search.web",
                "tool": "office.search_web",
                "arguments": {
                    "query": recent_entity_subject,
                    "limit": 5,
                },
                "reason": "Resolved a bare search follow-up against the last discussed entity.",
                "grounding_required": True,
                "entity_subject": recent_entity_subject,
            }
        if lowered in {"yes", "yeah", "yep", "sure", "ok", "okay"} and recent_entity_subject:
            recent_assistant = "\n".join(
                str(turn.get("text") or "") for turn in recent_turns[-4:] if str(turn.get("role") or "").strip().lower() == "assistant"
            ).lower()
            if "search the web" in recent_assistant or "search the internet" in recent_assistant or "search for more information" in recent_assistant:
                return {
                    "route_kind": "tool",
                    "workspace_id": workspace_id,
                    "request": request_text,
                    "capability": "search.web",
                    "tool": "office.search_web",
                    "arguments": {
                        "query": recent_entity_subject,
                        "limit": 5,
                    },
                    "reason": "Confirmed a recent offer to search the web for the last discussed entity.",
                    "grounding_required": True,
                    "entity_subject": recent_entity_subject,
                }
        session_search_match = SESSION_SEARCH_REQUEST_RE.match(text)
        if session_search_match and recent_entity_subject:
            query = self._normalize_session_query(str(session_search_match.group(2) or ""))
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "session.search",
                "tool": "office.sessions_search",
                "arguments": {
                    "query": query or recent_entity_subject,
                    "include_current": str(session_search_match.group(1) or "").strip().lower() != "other",
                },
                "reason": "Resolved a session-search follow-up against the last discussed entity.",
            }
        if SESSION_SEARCH_GENERIC_RE.match(text) and recent_entity_subject:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "session.search",
                "tool": "office.sessions_search",
                "arguments": {
                    "query": recent_entity_subject,
                    "include_current": True,
                    "detail": True,
                },
                "reason": "Resolved a generic session-search follow-up against the last discussed entity.",
            }
        web_search_match = re.match(
            r"^(?:search|look\s+up|check)\s+(?:the\s+)?(?:web|internet|online)\b(?:\s+(?:for|about)\s+(.+?))?\??$",
            text,
            re.IGNORECASE,
        )
        if web_search_match and recent_entity_subject:
            query = re.sub(r"\s+", " ", str(web_search_match.group(1) or "").strip(" .,:;?!"))
            if query.lower().endswith(" information"):
                query = query[:-12].rstrip(" .,:;?!")
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "search.web",
                "tool": "office.search_web",
                "arguments": {
                    "query": query or recent_entity_subject,
                    "limit": 5,
                },
                "reason": "Resolved a web-search follow-up against the last discussed entity.",
                "grounding_required": True,
                "entity_subject": query or recent_entity_subject,
            }
        match = re.match(r"^(?:what|how)\s+about\s+(.+?)\??$", text, re.IGNORECASE)
        recent_text = "\n".join(str(turn.get("text") or "") for turn in recent_turns[-8:])
        recent_lower = recent_text.lower()
        followup_response = grounded_entity_followup_response(request_text, recent_text)
        if followup_response is not None and "search results" in recent_lower:
            return {
                "route_kind": "clarify",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "clarification.entity_followup",
                "tool": "office.capability_info",
                "arguments": {
                    "response_text": followup_response,
                },
                "reason": "Answered an entity follow-up from the latest grounded search evidence.",
            }

        if match:
            subject = re.sub(r"\s+", " ", match.group(1).strip(" .?!")).strip()
            if len(subject) >= 3 and any(
                marker in recent_lower for marker in ("restaurant", "restaurants", "review-oriented results", "place results")
            ):
                location = None
                for turn in reversed(recent_turns[-8:]):
                    location = self.extract_location(str(turn.get("text") or ""))
                    if location:
                        break
                if location:
                    category = "restaurant"
                    if "italian" in recent_lower:
                        category = "italian restaurant"
                    elif "thai" in recent_lower:
                        category = "thai restaurant"

                    return {
                        "route_kind": "tool",
                        "workspace_id": workspace_id,
                        "request": request_text,
                        "capability": "search.reviews",
                        "tool": "office.search_reviews",
                        "arguments": {
                            "query": f"{subject} {category}",
                            "location": location,
                            "time_window": None,
                            "limit": 5,
                        },
                        "reason": "Resolved a short follow-up against the recent restaurant search context.",
                    }

        plan = self.conversation_planner.rewrite_followup(request_text, recent_turns)
        if plan is None:
            return None
        return self.model_route(
            workspace_id,
            plan.user_prompt,
            reason=f"Resolved a short follow-up against the recent session thread: {request_text}",
            apply_conversation_plan=False,
        )
