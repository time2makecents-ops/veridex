from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from office_app.server.conversation_planner import ConversationPlanner
from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.room_policy_registry import load_room_policies
from office_app.server.room_router import rooms_payload, validate_room


def normalize_room_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class RequestPipeline:
    ARTIFACT_CREATE_TRIGGERS = (
        "save this",
        "save artifact",
        "save note",
        "store this",
        "store artifact",
        "store note",
        "create artifact",
    )
    ARTIFACT_LIST_TRIGGERS = (
        "show artifacts",
        "list artifacts",
        "what have we saved so far",
        "what's saved so far",
        "what is saved so far",
        "what did we save",
        "show artifact list",
        "show saved artifacts",
        "list saved artifacts",
    )
    ARTIFACT_OPEN_TRIGGERS = (
        "open artifact",
        "open the artifact",
        "view artifact",
        "read artifact",
    )
    ARTIFACT_GLOBAL_TRIGGERS = (
        "archive room",
        "archive artifacts",
        "global artifacts",
        "global search",
        "global retrieval",
        "all-project search",
        "all project search",
        "all projects",
        "all workspaces",
        "across workspaces",
        "workspace-wide",
        "cross workspace",
        "cross-workspace",
        "archive/global",
    )
    ARTIFACT_ARCHIVE_ROOM = "records_archive"
    ARTIFACT_ID_RE = re.compile(r"\bart_[A-Za-z0-9]+\b", re.IGNORECASE)
    FILE_ID_RE = re.compile(r"\bfile_[A-Za-z0-9]+\b", re.IGNORECASE)
    FILE_NAME_RE = re.compile(
        r"(?P<name>[A-Za-z0-9_().-]{1,120}\.(?:txt|rtf|pdf|png|jpg|jpeg|webp|gif|bmp|tif|tiff|md|csv|json|xml|html|htm|doc|docx))",
        re.IGNORECASE,
    )
    ROOM_MEMORY_PATTERNS = (
        re.compile(r"^(?:i\s+want\s+you\s+to\s+)?(?P<instruction>answer\s+my\s+(?P<domain>[a-z0-9 '&-]{2,40})\s+questions\s+from\s+now\s+on\s+.+)$", re.IGNORECASE),
        re.compile(r"^(?:i\s+want\s+you\s+to\s+)?remember\s+to\s+(?P<instruction>.+)$", re.IGNORECASE),
        re.compile(r"^(?:please\s+)?remember\s+(?:in|for)\s+(?P<room>.+?)\s+that\s+(?P<instruction>.+)$", re.IGNORECASE),
        re.compile(r"^(?:please\s+)?(?:in|for)\s+(?P<room>.+?)[, ]+remember\s+that\s+(?P<instruction>.+)$", re.IGNORECASE),
        re.compile(r"^(?:please\s+)?remember\s+that\s+(?P<instruction>.+)$", re.IGNORECASE),
    )
    ROOM_MEMORY_FORGET_PATTERNS = (
        re.compile(r"^(?:please\s+)?(?:forget|stop remembering|remove)\s+(?:in|for)\s+(?P<room>.+?)\s+that\s+(?P<match>.+)$", re.IGNORECASE),
        re.compile(r"^(?:please\s+)?(?:forget|stop remembering|remove)\s+(?P<match>.+?)\s+(?:in|for)\s+(?P<room>.+)$", re.IGNORECASE),
        re.compile(r"^(?:please\s+)?(?:forget|stop remembering|remove)\s+(?P<match>.+)$", re.IGNORECASE),
    )
    ROOM_MEMORY_INDEX_WORDS = {
        "1": 1,
        "#1": 1,
        "first": 1,
        "first one": 1,
        "the first": 1,
        "the first one": 1,
        "2": 2,
        "#2": 2,
        "second": 2,
        "second one": 2,
        "the second": 2,
        "the second one": 2,
        "3": 3,
        "#3": 3,
        "third": 3,
        "third one": 3,
        "the third": 3,
        "the third one": 3,
        "4": 4,
        "#4": 4,
        "fourth": 4,
        "fourth one": 4,
        "the fourth": 4,
        "the fourth one": 4,
        "5": 5,
        "#5": 5,
        "fifth": 5,
        "fifth one": 5,
        "the fifth": 5,
        "the fifth one": 5,
    }
    ROOM_MEMORY_LIST_HINTS = (
        "what memory objects do you have saved",
        "what memory objects do i have saved",
        "what memory objects are saved",
        "what memories do you have saved",
        "what memories do i have saved",
        "what memories are saved",
        "what do you remember",
        "what do you remember in",
        "show memory objects",
        "list memory objects",
        "list saved memories",
        "show saved memories",
    )
    ROOM_NAVIGATION_PREFIXES = (
        "go to ",
        "go back to ",
        "take me to ",
        "take us to ",
        "move to ",
        "switch to ",
        "return to ",
    )
    ROOM_NAVIGATION_RE = re.compile(
        r"\b(?:go|take|move|switch|bring|send|head|route|direct|return)(?:\s+me|\s+us)?\s+to\b|\bback\s+to\b",
        re.IGNORECASE,
    )
    ROOM_NAVIGATION_AMBIGUOUS_CUES = (
        "can you",
        "could you",
        "would you",
        "please",
        "i want",
        "i need",
        "i'd like",
        "i would like",
        "let's",
        "we should",
        "help me",
        "maybe",
    )
    SEARCH_WEB_HINTS = (
        "search the internet",
        "search the web",
        "look this up",
        "look it up",
        "search online",
        "web search",
        "check online",
    )
    SEARCH_REVIEW_HINTS = (
        "reviews",
        "review",
        "highest rated",
        "top rated",
        "best rated",
        "yelp",
        "tripadvisor",
    )
    SEARCH_PLACE_HINTS = (
        "restaurant",
        "restaurants",
        "resaurnat",
        "resaurnats",
        "restaurnat",
        "restaurnats",
        "resteraunt",
        "resteraunts",
        "restaraunt",
        "restaraunts",
        "resturant",
        "resturants",
        "bar",
        "bars",
        "coffee",
        "cafe",
        "hotel",
        "hotels",
        "place",
        "places",
    )
    SEARCH_PLACE_DISCOVERY_HINTS = (
        "find",
        "recommend",
        "nearest",
        "nearby",
        "near me",
        "where is",
        "where are",
        "what's near",
        "whats near",
        "what is near",
        "closest",
    )
    SEARCH_BUSINESS_ADVICE_HINTS = (
        "increase food sales",
        "increase sales",
        "boost sales",
        "improve sales",
        "grow sales",
        "sales strategy",
        "marketing strategy",
        "how do you increase",
        "how can i increase",
        "revenue strategy",
        "how do i improve",
    )
    INTENT_META_HINTS = (
        "why did you respond that way",
        "what criteria did you use",
        "explain your reasoning",
        "read your last response",
        "how are you deciding",
        "how did you decide",
        "why did you say that",
        "what did you mean",
        "what are you doing",
    )
    INTENT_ADVICE_HINTS = (
        "what are the best restaurants to model mine after",
        "how should i improve",
        "how can i improve",
        "how do i improve",
        "improve my restaurant marketing",
        "what makes a restaurant successful",
        "what makes restaurants successful",
        "model mine after",
        "best practices",
        "restaurant marketing",
        "sales strategy",
        "marketing strategy",
    )
    MODEL_NO_BACKGROUND_RULE = (
        "Do not claim you are searching, processing, working in the background, or that you will send results later. "
        "You can only answer with information available in this response. If a tool or missing detail is needed, say so directly."
    )
    MODEL_CONTEXT_RULE = (
        "Apply active-room behavior memory as durable room-specific instructions when present. "
        "Use the provided session conversation history as the current chat thread. "
        "When the user asks a follow-up, comparison, pronoun-based question, 'what about ...', or 'how about ...', "
        "resolve it against the immediately relevant prior turns instead of treating it as a blank new chat. "
        "For broad help or capability questions like 'what can you help me with here?', answer from the active room and persona instead of continuing the previous topic. "
        "Do not ask for details already present in recent context. "
        "If the user asks a reflective follow-up like 'how did you come to that conclusion?' or 'what makes you say that?', "
        "explain the immediately previous answer instead of asking the user for more context."
    )
    MODEL_DIRECT_ANSWER_RULE = (
        "Answer normal advice, strategy, explanation, and meta questions directly. "
        "Do not convert them into file, search, place, or room actions unless the user explicitly asks for that action."
    )
    MODEL_CAPABILITY_RULE = (
        "Veridex can search the web when explicitly asked, upload/download/list/read files, extract text from uploaded documents, "
        "switch rooms, create/switch sessions, create/select workspaces, and save artifacts/files. "
        "Do not deny these Veridex capabilities. If the user asks how to use one, explain the app workflow."
    )
    MODEL_RISK_RULE = (
        "When advice touches legal, regulatory, safety, financial, employment, privacy, or policy risk, "
        "be cautious, avoid unsupported certainty, and include a brief verification note when appropriate. "
        "Do not present risky promotional, medical, legal, or financial tactics as clean advice without a caution."
    )
    CORRECTION_VOCABULARY = (
        "artifact",
        "artifacts",
        "bar",
        "bars",
        "break",
        "cafe",
        "coffee",
        "conference",
        "directory",
        "document",
        "download",
        "extract",
        "file",
        "files",
        "finance",
        "hotel",
        "hotels",
        "internet",
        "italian",
        "lobby",
        "load",
        "marketing",
        "office",
        "open",
        "read",
        "restaurant",
        "restaurants",
        "reviews",
        "room",
        "sales",
        "save",
        "search",
        "session",
        "thai",
        "upload",
        "workspace",
    )
    ROOM_STATUS_HINTS = (
        "where am i",
        "what room am i in",
        "which room am i in",
        "what room is this",
        "where are we",
        "current room",
        "what room are we in",
    )
    OCR_EXPLICIT_HINTS = (
        "ocr",
        "extract text",
        "extract the text",
        "read the text from",
        "read file",
        "read the file",
        "read document",
        "show the extracted text from",
        "show me the extracted text from",
        "transcribe",
    )
    SESSION_CREATE_HINTS = (
        "new session",
        "start new session",
        "create new session",
        "start a new session",
        "create a new session",
    )
    CONTEXTUAL_REFERENCE_HINTS = (
        "which one",
        "what one",
        "which level",
        "what level",
        "most effective one",
        "most powerful one",
        "the first one",
        "the last one",
        "the strongest one",
        "the best one",
        "the most powerful one",
        "the most powerful level",
        "how does that compare",
        "would that work",
        "would that work for",
        "does that work",
    )
    NUMBERED_LIST_ITEM_RE = re.compile(r"(?m)^\s*\d+\.\s+")
    PRIOR_TOPIC_PATTERNS = (
        re.compile(r"\bwhat\s+is\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\bexplain\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\btell me about\s+(.+?)\??$", re.IGNORECASE),
    )
    STRATEGY_TOPIC_PATTERNS = (
        re.compile(r"\bmain ways?\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\btypes of\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\bways?\s+to\s+(.+?)\??$", re.IGNORECASE),
    )
    META_REFERENCE_PATTERNS = (
        re.compile(r"^how did you come to that conclusion\??$", re.IGNORECASE),
        re.compile(r"^why did you come to that conclusion\??$", re.IGNORECASE),
        re.compile(r"^what makes you say that\??$", re.IGNORECASE),
        re.compile(r"^why do you think that\??$", re.IGNORECASE),
        re.compile(r"^why that conclusion\??$", re.IGNORECASE),
        re.compile(r"^how did you decide that\??$", re.IGNORECASE),
        re.compile(r"^why that one\??$", re.IGNORECASE),
    )

    def __init__(
        self,
        kernel,
        navigator_control,
        utc_now_fn,
        tool_names: Optional[List[str]] = None,
        tool_catalog: Optional[List[Dict[str, Any]]] = None,
        app_version: Optional[str] = None,
    ):
        self.kernel = kernel
        self.navigator_control = navigator_control
        self.utc_now = utc_now_fn
        self.tool_names = tool_names or []
        self.tool_catalog = tool_catalog or []
        self.app_version = app_version or "0.0.0"
        self.conversation_planner = ConversationPlanner()

    def health_response(self) -> Dict[str, Any]:
        return {"ok": True, "ts": self.utc_now()}

    def tools_response(self) -> Dict[str, Any]:
        return {
            "tools": self.tool_names,
            "capabilities": self.tool_catalog,
            "commands": [
                {"name": "Start Veridex", "description": "Launch the self-healing backend loop now."},
                {"name": "Install Autostart", "description": "Create a startup shortcut so Veridex launches at login."},
                {"name": "Remove Autostart", "description": "Delete the startup shortcut for Veridex."},
            ],
            "version": self.app_version,
        }

    def workspaces_list_response(self, idx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "structuredContent": idx,
            "content": [{"type": "text", "text": f"Found {len(idx.get('workspaces', []))} workspace(s)."}],
        }

    def workspace_new_response(self, workspace_id: str, label: str) -> Dict[str, Any]:
        return {
            "structuredContent": {"workspace_id": workspace_id, "label": label},
            "content": [{"type": "text", "text": f"Created workspace {workspace_id}."}],
        }

    def current_context(self, workspace_id: str) -> Dict[str, Any]:
        return self.kernel.current_context(workspace_id)

    def snapshot(self, workspace_id: str) -> Dict[str, Any]:
        ctx = self.current_context(workspace_id)
        return {
            "workspace_id": workspace_id,
            "active_room": ctx["active_room"],
            "active_persona": ctx["active_persona"],
            "active_persona_profile": ctx["active_persona_profile"],
            "navigator": self.navigator_control,
            "rooms": rooms_payload(),
            "room_policies": load_room_policies(),
            "timestamp_utc": self.utc_now(),
        }

    def snapshot_response(self, workspace_id: str) -> Dict[str, Any]:
        snap = self.snapshot(workspace_id)
        return {
            "structuredContent": snap,
            "content": [{"type": "text", "text": f"Active room: {snap['active_room']} | Persona: {snap['active_persona']}"}],
        }

    def enter_room_response(self, workspace_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "previous_room": result["previous_room"],
                "active_room": result["active_room"],
                "active_persona": result["active_persona"],
                "active_persona_profile": result["active_persona_profile"],
                "navigator": self.navigator_control,
                "rooms": rooms_payload(),
            },
            "content": [{"type": "text", "text": f"Active room set to {result['room_title']} | Persona: {result['active_persona']}."}],
        }

    def assert_mailroom_allowed(self, from_room: str, to_room: str) -> None:
        policies = load_room_policies()

        if to_room == "break_room":
            raise HTTPException(
                status_code=403,
                detail="Break Room is non-operational. Memo dispatch is not allowed to break_room.",
            )

        if from_room == "break_room":
            raise HTTPException(
                status_code=403,
                detail="Break Room is non-operational. Memo dispatch is not allowed from break_room.",
            )

        if from_room == "vr_room":
            vr_policy = policies.get("vr_room", {})
            if not vr_policy.get("affects_other_rooms", False):
                raise HTTPException(
                    status_code=403,
                    detail="VR Room sandbox is isolated. Dispatch to other rooms is not allowed from vr_room.",
                )

    def recommend_room(self, request_text: str) -> Dict[str, Any]:
        text = request_text.lower()

        def has_keyword(keyword: str) -> bool:
            term = keyword.strip().lower()
            if not term:
                return False
            if " " in term or "-" in term:
                return term in text
            pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
            return re.search(pattern, text) is not None

        rules = [
            (["my office"], "my_office"),
            (["contract", "legal", "law", "lawsuit", "liability", "agreement", "negotiation"], "law_office"),
            (["payroll", "accounting", "budget", "bank", "banking", "finance", "expense"], "finance_department"),
            (["computer", "it", "network", "wifi", "router", "software", "programming", "phone", "technical"], "it_department"),
            (["marketing", "campaign", "advertising", "audience", "promotion", "brand"], "marketing_room"),
            (["sales", "prospect", "client", "crm", "deal", "account executive", "outreach"], "sales_department"),
            (["design", "poster", "graphic", "video", "audio", "art", "creative"], "art_department"),
            (["hr", "employee", "staff", "burnout", "wellbeing", "policy", "onboarding"], "hr_department"),
            (["archive", "records", "database", "paperwork", "documents", "filing"], "records_archive"),
            (["invent", "invention", "prototype", "engineering", "chemistry", "patent", "r&d"], "rnd_room"),
            (["security", "phishing", "camera", "alarm", "threat", "social engineering"], "security_room"),
            (["sandbox", "simulate", "simulation", "test rules", "vr"], "vr_room"),
            (["break", "joke", "game", "fun", "relax"], "break_room"),
        ]

        for keywords, room_id in rules:
            if any(has_keyword(k) for k in keywords):
                room = validate_room(room_id)
                return {
                    "matched": True,
                    "room_id": room["id"],
                    "room_title": room["title"],
                    "persona": str(room.get("default_persona") or "Navigator"),
                    "reason": f"Matched request keywords to {room['title']}.",
                }

        room = validate_room("my_office")
        return {
            "matched": False,
            "room_id": room["id"],
            "room_title": room["title"],
            "persona": str(room.get("default_persona") or "Nancy"),
            "reason": "No strong department match found. Keeping request in My Office.",
        }

    def extract_navigation_room(self, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.strip()
        if not self.is_explicit_room_navigation(text):
            return None

        normalized = text.lower().strip()
        normalized = re.sub(
            r"^(?:go|take|move|switch|bring|send|head|route|direct|return)(?:\s+me|\s+us)?\s+to\s+",
            "",
            normalized,
        )
        normalized = re.sub(r"^back\s+to\s+", "", normalized)
        normalized = normalized.strip(" .,!?:;")
        if not normalized:
            return None

        rooms = rooms_payload()
        candidates: List[Dict[str, Any]] = []
        for room in rooms:
            room_id = str(room.get("id") or "").strip()
            room_title = str(room.get("title") or room_id).strip()
            if not room_id or not room_title:
                continue
            room_id_norm = normalize_room_text(room_id)
            room_title_norm = normalize_room_text(room_title)
            if normalized == room_id_norm or normalized == room_title_norm:
                return room
            if normalized in {room_id_norm, room_title_norm}:
                return room
            candidates.append(
                {
                    "room": room,
                    "aliases": [room_id_norm, room_title_norm],
                }
            )

        alias_map: Dict[str, Dict[str, Any]] = {}
        alias_keys: List[str] = []
        for candidate in candidates:
            room = candidate["room"]
            for alias in candidate["aliases"]:
                if alias and alias not in alias_map:
                    alias_map[alias] = room
                    alias_keys.append(alias)

        if alias_keys:
            matches = difflib.get_close_matches(normalized, alias_keys, n=1, cutoff=0.78)
            if matches:
                return alias_map[matches[0]]

        return None

    def room_navigation_requires_confirmation(self, request_text: str) -> bool:
        text = request_text.strip().lower()
        if not text:
            return False
        route = self.recommend_room(request_text)
        if not route.get("matched"):
            return False
        if self.is_explicit_room_navigation(request_text):
            return False
        if " to " not in f" {text} ":
            return False
        return any(cue in text for cue in self.ROOM_NAVIGATION_AMBIGUOUS_CUES)

    def nancy_route(self, workspace_id: str, request_text: str) -> Dict[str, Any]:
        ctx = self.current_context(workspace_id)
        route = self.recommend_room(request_text)
        return {
            "room_id": route["room_id"],
            "room_title": route["room_title"],
            "persona": route["persona"],
            "reason": route["reason"],
            "auto_routed": True,
            "requires_confirmation": False,
            "current_room": ctx["active_room"],
            "current_persona": ctx["active_persona"],
        }

    def nancy_route_response(self, workspace_id: str, request_text: str) -> Dict[str, Any]:
        route = self.nancy_route(workspace_id, request_text)
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "request": request_text,
                "recommended_room": route["room_id"],
                "recommended_room_title": route["room_title"],
                "recommended_persona": route["persona"],
                "recommended_persona_profile": persona_profile_for_name(route["persona"]),
                "reason": route["reason"],
                "auto_routed": route["auto_routed"],
                "requires_confirmation": route["requires_confirmation"],
                "current_room": route["current_room"],
                "current_persona": route["current_persona"],
            },
            "content": [{"type": "text", "text": f"Nancy moved you to {route['room_title']} ({route['persona']})."}],
        }

    def artifact_retrieval_scope(self, workspace_id: str, request_text: str) -> str:
        ctx = self.current_context(workspace_id)
        active_room = str(ctx.get("active_room") or "").strip().lower()
        text = request_text.lower().strip()

        if active_room == self.ARTIFACT_ARCHIVE_ROOM:
            return "archive_global"

        if any(trigger in text for trigger in self.ARTIFACT_GLOBAL_TRIGGERS):
            return "archive_global"

        return "workspace"

    def route_artifact_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None

        retrieval_scope = self.artifact_retrieval_scope(workspace_id, request_text)

        if any(trigger in text for trigger in self.ARTIFACT_CREATE_TRIGGERS):
            return {
                "capability": "artifact.create",
                "tool": "office.artifact_create",
                "arguments": {
                    "type": "note",
                    "title": "Saved note",
                    "content": request_text,
                    "created_by": "user",
                    "metadata": {
                        "source": "natural_language_request",
                        "intent": "save",
                        "request_text": request_text,
                    },
                },
                "reason": "Matched a save/store keyword.",
            }

        if any(trigger in text for trigger in self.ARTIFACT_LIST_TRIGGERS):
            list_args: Dict[str, Any] = {
                "retrieval_scope": retrieval_scope,
            }
            if retrieval_scope != "workspace":
                list_args["include_archived"] = True
            return {
                "capability": "artifact.list",
                "tool": "office.artifact_list",
                "arguments": list_args,
                "reason": "Matched a list/show keyword.",
            }

        if any(trigger in text for trigger in self.ARTIFACT_OPEN_TRIGGERS):
            match = self.ARTIFACT_ID_RE.search(request_text)
            if match:
                get_args: Dict[str, Any] = {
                    "artifact_id": match.group(0),
                    "retrieval_scope": retrieval_scope,
                }
                return {
                    "capability": "artifact.get",
                    "tool": "office.artifact_get",
                    "arguments": get_args,
                    "reason": "Matched an open/read keyword and found an artifact id.",
                }

        return None

    def route_user_request(self, workspace_id: str, request_text: str) -> Dict[str, Any]:
        room_memory_list_route = self.route_room_memory_list_request(workspace_id, request_text)
        if room_memory_list_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **room_memory_list_route,
            }

        room_memory_route = self.route_room_memory_request(workspace_id, request_text)
        if room_memory_route is not None:
            if "route_kind" in room_memory_route:
                return {
                    "workspace_id": workspace_id,
                    "request": request_text,
                    **room_memory_route,
                }
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **room_memory_route,
            }

        capability_route = self.route_capability_question(workspace_id, request_text)
        if capability_route is not None:
            return capability_route

        intent = self.classify_intent(request_text)
        if intent in {"meta", "advice"}:
            return self.model_route(
                workspace_id,
                request_text,
                reason=f"Classified as {intent} intent before tool routing.",
            )

        artifact_route = self.route_artifact_request(workspace_id, request_text)
        if artifact_route is not None:
            return {
                "route_kind": "artifact",
                "workspace_id": workspace_id,
                "request": request_text,
                **artifact_route,
            }

        ocr_route = self.route_ocr_request(workspace_id, request_text)
        if ocr_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **ocr_route,
            }

        search_route = self.route_search_request(workspace_id, request_text)
        if search_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **search_route,
            }

        status_route = self.route_room_status_request(workspace_id, request_text)
        if status_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **status_route,
            }

        session_route = self.route_session_request(workspace_id, request_text)
        if session_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **session_route,
            }

        navigation_room = self.extract_navigation_room(request_text)
        if navigation_room is not None:
            return {
                "route_kind": "navigation",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "room.navigate",
                "tool": "office.room_set",
                "arguments": {"workspace_id": workspace_id, "room_id": navigation_room["id"]},
                "reason": f"Explicit room navigation to {navigation_room['title']}.",
                "room_id": navigation_room["id"],
                "room_title": navigation_room["title"],
                "persona": str(navigation_room.get("default_persona") or "Navigator"),
                "requires_confirmation": False,
            }

        route = self.recommend_room(request_text)
        if route.get("matched") and self.is_explicit_room_navigation(request_text):
            return {
                "route_kind": "navigation",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "room.navigate",
                "tool": "office.room_set",
                "arguments": {"workspace_id": workspace_id, "room_id": route["room_id"]},
                "reason": route["reason"],
                "room_id": route["room_id"],
                "room_title": route["room_title"],
                "persona": route["persona"],
            }

        if route.get("matched") and self.room_navigation_requires_confirmation(request_text):
            return {
                "route_kind": "navigation",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "room.navigate",
                "tool": "office.room_set",
                "arguments": {"workspace_id": workspace_id, "room_id": route["room_id"]},
                "reason": route["reason"],
                "room_id": route["room_id"],
                "room_title": route["room_title"],
                "persona": route["persona"],
                "requires_confirmation": True,
            }

        correction = self.suggest_correction(request_text)
        if correction is not None:
            return {
                "route_kind": "clarify",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "clarification.spelling",
                "tool": "office.clarify_spelling",
                "arguments": correction,
                "reason": f"Possible misspelling: {correction['word']} -> {correction['suggestion']}.",
            }

        return self.model_route(
            workspace_id,
            request_text,
            reason="No explicit tool or room command found. Using the model route.",
        )

    def resolve_room_reference(self, room_text: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_room_text(room_text)
        if not normalized:
            return None

        for room in rooms_payload():
            room_id = str(room.get("id") or "").strip()
            title = str(room.get("title") or room_id).strip()
            aliases = {
                normalize_room_text(room_id),
                normalize_room_text(title),
                normalize_room_text(title.replace("&", "and")),
                normalize_room_text(title.replace("Department", "").replace("department", "")),
                normalize_room_text(room_id.replace("_department", "").replace("_room", "")),
            }
            if normalized in aliases:
                return room

        route = self.recommend_room(room_text)
        if route.get("matched"):
            return validate_room(str(route["room_id"]))
        return None

    def route_room_memory_list_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip().lower())
        if not text:
            return None
        if not any(hint in text for hint in self.ROOM_MEMORY_LIST_HINTS):
            return None
        ctx = self.current_context(workspace_id)
        room_id = str(ctx.get("active_room") or "lobby")
        room = validate_room(room_id)
        return {
            "capability": "room.memory.list",
            "tool": "office.room_memory_list",
            "arguments": {
                "workspace_id": workspace_id,
                "room_id": str(room["id"]),
            },
            "reason": f"Matched a room behavior memory list request for {room['title']}.",
        }

    def route_room_memory_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip())
        if not text:
            return None
        for pattern in self.ROOM_MEMORY_FORGET_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue
            match_text = re.sub(r"\s+", " ", str(match.groupdict().get("match") or "").strip(" ."))
            memory_index = self.ROOM_MEMORY_INDEX_WORDS.get(normalize_room_text(match_text))
            if not match_text or (memory_index is None and normalize_room_text(match_text) in {"memory", "behavior", "behaviour", "that", "it", "this"}):
                return {
                    "route_kind": "clarify",
                    "capability": "clarification.room_memory",
                    "tool": "office.capability_info",
                    "arguments": {
                        "response_text": "Which remembered behavior should I remove from this room?",
                        "match_text": match_text,
                    },
                    "reason": "Room memory removal request did not identify what to forget.",
                }
            room_text = str(match.groupdict().get("room") or "").strip(" .")
            room_id = ""
            if room_text:
                room = self.resolve_room_reference(room_text)
                if room is None:
                    if normalize_room_text(room_text) == "mind":
                        continue
                    return {
                        "route_kind": "clarify",
                        "capability": "clarification.room_memory",
                        "tool": "office.capability_info",
                        "arguments": {
                            "response_text": f"I can remove room behavior memory, but I could not identify the room: {room_text}.",
                            "room_text": room_text,
                        },
                        "reason": "Room memory removal request included an unknown room reference.",
                    }
                room_id = str(room["id"])
            else:
                ctx = self.current_context(workspace_id)
                room_id = str(ctx.get("active_room") or "lobby")
            room = validate_room(room_id)
            return {
                "capability": "room.memory.forget",
                "tool": "office.room_memory_forget",
                "arguments": {
                    "workspace_id": workspace_id,
                    "room_id": str(room["id"]),
                    "match_text": match_text,
                    "memory_index": memory_index,
                },
                "reason": f"Matched a room behavior memory removal request for {room['title']}.",
            }

        if not re.search(r"\b(remember|from now on)\b", text, re.IGNORECASE):
            return None
        for pattern in self.ROOM_MEMORY_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue
            instruction = re.sub(r"\s+", " ", str(match.groupdict().get("instruction") or "").strip(" ."))
            if not instruction:
                continue
            room_id = ""
            room_text = str(match.groupdict().get("room") or "").strip(" .")
            if not room_text:
                domain = str(match.groupdict().get("domain") or "").strip(" .")
                if domain:
                    room_text = domain
            if room_text:
                room = self.resolve_room_reference(room_text)
                if room is None:
                    return {
                        "route_kind": "clarify",
                        "capability": "clarification.room_memory",
                        "tool": "office.capability_info",
                        "arguments": {
                            "response_text": f"I can store that as room behavior memory, but I could not identify the room: {room_text}.",
                            "room_text": room_text,
                        },
                        "reason": "Room memory request included an unknown room reference.",
                    }
                room_id = str(room["id"])
            else:
                ctx = self.current_context(workspace_id)
                room_id = str(ctx.get("active_room") or "lobby")
            room = validate_room(room_id)
            return {
                "capability": "room.memory.remember",
                "tool": "office.room_memory_remember",
                "arguments": {
                    "workspace_id": workspace_id,
                    "room_id": str(room["id"]),
                    "instruction": instruction,
                },
                "reason": f"Matched a room behavior memory request for {room['title']}.",
            }
        return None

    def model_route(self, workspace_id: str, request_text: str, *, reason: str, apply_conversation_plan: bool = True) -> Dict[str, Any]:
        ctx = self.current_context(workspace_id)
        active_room = str(ctx["active_room"])
        active_persona = str(ctx["active_persona"])
        user_prompt = request_text
        if apply_conversation_plan:
            user_prompt = self.conversation_planner.plan_model_prompt(request_text).user_prompt
        system_prompt = (
            f"You are Veridex. The active workspace is {workspace_id}. "
            f"The active room is {active_room}. The active persona is {active_persona}. "
            "Respond clearly, concisely, and in a way that fits the current office context. "
            f"{self.MODEL_CONTEXT_RULE} {self.MODEL_NO_BACKGROUND_RULE} {self.MODEL_DIRECT_ANSWER_RULE} "
            f"{self.MODEL_CAPABILITY_RULE} {self.MODEL_RISK_RULE}"
        )
        return {
            "route_kind": "model",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": "ai.respond",
            "tool": "office.ai_generate",
            "arguments": {
                "workspace_id": workspace_id,
                "task_type": "conversation",
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "context": {
                    "workspace_id": workspace_id,
                    "active_room": active_room,
                    "active_persona": active_persona,
                },
                "settings": {
                    "temperature": 0.4,
                    "max_output_tokens": 512,
                    "provider_by_task_type": {
                        "conversation": "gemini",
                    },
                },
            },
            "reason": reason,
        }

    def route_capability_question(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        capability = self.capability_question_kind(request_text)
        if capability is None:
            return None
        ctx = self.current_context(workspace_id)
        active_room = str(ctx.get("active_room") or "lobby")
        active_persona = str(ctx.get("active_persona") or "Receptionist")
        response_text = self.capability_response_text(
            capability,
            active_room=active_room,
            active_persona=active_persona,
        )
        return {
            "route_kind": "clarify",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": f"capability.{capability}.info",
            "tool": "office.capability_info",
            "arguments": {
                "response_text": response_text,
                "active_room": active_room,
                "active_persona": active_persona,
            },
            "reason": f"Answered a {capability} capability question without running a tool.",
        }

    def capability_question_kind(self, request_text: str) -> Optional[str]:
        text = request_text.lower().strip()
        if not text:
            return None
        if self.is_explicit_room_navigation(text) or self.FILE_ID_RE.search(request_text) or self.FILE_NAME_RE.search(request_text):
            return None
        if self.is_search_capability_question(text):
            return "search"
        if not self.is_capability_question(text):
            return None
        if re.search(r"\b(upload|attach|add file|choose file|submit file|send file)\b", text):
            return "upload"
        if re.search(r"\b(download|export|get files?|save.*to my computer)\b", text):
            return "download"
        if re.search(r"\b(load|open files?|view files?|reader|file list)\b", text):
            return "load"
        if re.search(r"\b(ocr|extract text|read documents?|read files?|read uploaded|transcribe|text from)\b", text):
            return "document_read"
        if re.search(r"\b(save|store|artifact|artifacts|note|notes)\b", text):
            return "save"
        if re.search(r"\b(room|rooms|department|departments|persona|personas|switch rooms?|change rooms?)\b", text):
            return "rooms"
        if re.search(r"\b(session|sessions|thread|threads)\b", text):
            return "sessions"
        if re.search(r"\b(workspace|workspaces|project folder|project folders|projects)\b", text):
            return "workspaces"
        if re.search(r"\b(memory|remember|recall|stored info|saved info)\b", text):
            return "memory"
        if re.match(r"^(?:what can you do|what are your capabilities|what tools do you have|what can veridex do)\??$", text):
            return "overview"
        return None

    def is_capability_question(self, text: str) -> bool:
        return bool(
            re.match(
                r"^(?:can|could|do|does|are|will|would)\s+(?:you|veridex)\b|"
                r"^(?:how\s+(?:do|can)\s+i|how\s+does\s+veridex|do\s+you\s+know\s+how|"
                r"what\s+can\s+you\s+do|what\s+are\s+your\s+capabilities|what\s+tools\s+do\s+you\s+have)",
                text,
            )
        )

    def capability_response_text(self, capability: str, *, active_room: str, active_persona: str) -> str:
        room_title = self.room_title_for_id(active_room)
        profile = persona_profile_for_name(active_persona)
        persona_purpose = str(profile.get("purpose") or "").strip()
        persona_style = str(profile.get("style") or "").strip()
        room_line = f"Here in {room_title}, I am the {active_persona}."
        if persona_purpose:
            room_line += f" My room-specific role is: {persona_purpose}"
        if persona_style:
            room_line += f" My style here is {persona_style}."
        coordination_line = (
            "When a task needs another department, I can help coordinate with other rooms through the memo system "
            "instead of pretending this room owns every specialty."
        )

        responses = {
            "search": (
                f"{room_line}\n\n"
                "Yes. I can search the internet when you explicitly ask me to search, look something up, "
                "or check online. I will apply this room's role to how I interpret the results. "
                f"{coordination_line} What would you like me to search for?"
            ),
            "upload": (
                f"{room_line}\n\n"
                "Yes. Use the Save/Upload controls, choose a file, pick its type and scope, then upload it. "
                f"After it is saved, you can ask me to read or use that file. {coordination_line}"
            ),
            "download": (
                f"{room_line}\n\n"
                f"Yes. Open Load, select the saved file, then use Download from the reader/file view. {coordination_line}"
            ),
            "load": (
                f"{room_line}\n\n"
                f"Yes. Use Load to list saved files by scope, select one, and it will open in the reader window. {coordination_line}"
            ),
            "document_read": (
                f"{room_line}\n\n"
                "Yes. I can read or extract text from uploaded documents. Upload or select the file, then ask "
                f"for example: 'extract text from filename.rtf'. {coordination_line}"
            ),
            "save": (
                f"{room_line}\n\n"
                "Yes. I can save notes/artifacts from chat, and the app can save files by scope: room, session, public, or private. "
                f"{coordination_line}"
            ),
            "rooms": (
                f"{room_line}\n\n"
                "Yes. Use the Directory button or say something explicit like 'go to Sales Department'. "
                f"Room changes are backend-controlled so the active persona and room state stay consistent. {coordination_line}"
            ),
            "sessions": (
                f"{room_line}\n\n"
                "Yes. Sessions are individual chat threads inside a workspace. Say 'new session for ...' or select a session from the lobby/session controls. "
                f"{coordination_line}"
            ),
            "workspaces": (
                f"{room_line}\n\n"
                "Yes. Workspaces act like project folders. You can create/select them from the lobby, and sessions live inside the active workspace. "
                f"{coordination_line}"
            ),
            "memory": (
                f"{room_line}\n\n"
                "Yes, within Veridex boundaries. Workspace data holds project files/artifacts; session data holds the chat thread and summary; rooms do not keep separate durable memory. "
                f"{coordination_line}"
            ),
            "overview": (
                f"{room_line}\n\n"
                "Across Veridex, I can chat, search the web when explicitly asked, switch rooms, manage sessions/workspaces, "
                "upload/download/list files, read uploaded documents, save artifacts or notes, and coordinate with other departments through the memo system. "
                "What makes this room different is the role and judgment I apply to those tools."
            ),
        }
        return responses.get(capability, responses["overview"])

    def room_title_for_id(self, room_id: str) -> str:
        for room in rooms_payload():
            if str(room.get("id") or "").strip() == room_id:
                return str(room.get("title") or room_id).strip()
        return room_id or "Lobby"

    def classify_intent(self, request_text: str) -> str:
        text = request_text.lower().strip()
        if not text:
            return "task"
        if self.is_meta_intent(text):
            return "meta"
        if self.is_explicit_task_intent(request_text):
            return "task"
        if self.is_advice_intent(text):
            return "advice"
        return "task"

    def is_meta_intent(self, text: str) -> bool:
        if any(hint in text for hint in self.INTENT_META_HINTS):
            return True
        return bool(
            re.search(
                r"\b(?:why|how|what)\s+(?:did|do|are)\s+you\s+(?:respond|answer|decide|choos|think|reason)",
                text,
            )
        )

    def is_advice_intent(self, text: str) -> bool:
        if any(hint in text for hint in self.INTENT_ADVICE_HINTS):
            return True
        if re.search(r"\bwhat\s+makes\b", text):
            return True
        if re.match(r"^(?:how|why)\s+(?:do|does|can|could|should|would|is|are)\b", text):
            return True
        if re.match(r"^(?:what|which)\s+is\s+the\s+best\s+way\b", text):
            return True
        advice_terms = (
            "advice",
            "approach",
            "best practice",
            "criteria",
            "explain",
            "idea",
            "improve",
            "increase",
            "marketing",
            "model",
            "plan",
            "strategy",
            "successful",
            "tip",
        )
        question_starter = re.match(r"^(?:what|which|tell me|can you explain|help me)\b", text)
        return bool(question_starter and any(term in text for term in advice_terms))

    def is_explicit_task_intent(self, request_text: str) -> bool:
        text = request_text.lower().strip()
        if not text:
            return False
        if self.is_explicit_room_navigation(text):
            return True
        if any(hint in text for hint in self.ROOM_STATUS_HINTS):
            return True
        if any(hint in text for hint in self.SESSION_CREATE_HINTS):
            return True
        if any(trigger in text for trigger in self.ARTIFACT_CREATE_TRIGGERS + self.ARTIFACT_LIST_TRIGGERS + self.ARTIFACT_OPEN_TRIGGERS):
            return True
        if any(hint in text for hint in self.OCR_EXPLICIT_HINTS):
            return True
        if any(hint in text for hint in self.SEARCH_WEB_HINTS):
            return True

        starts_with_discovery = re.match(r"^(?:find|show me|list|recommend|give me)\b", text) is not None
        has_place_hint = any(hint in text for hint in self.SEARCH_PLACE_HINTS)
        if has_place_hint:
            place_query = self.normalize_place_query(request_text)
            review_signal = any(hint in text for hint in self.SEARCH_REVIEW_HINTS) or bool(
                re.search(r"\b(?:best|top|highest rated|top rated|best rated)\b", text)
            )
            has_location_or_nearby = bool(place_query["location"] or place_query["needs_location"])
            if starts_with_discovery or review_signal or has_location_or_nearby:
                if self.is_advice_intent(text) and not starts_with_discovery and not place_query["location"]:
                    return False
                return True

        return False

    def route_search_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        if self.is_search_capability_question(text):
            return None

        if any(hint in text for hint in self.SEARCH_BUSINESS_ADVICE_HINTS):
            if not any(hint in text for hint in self.SEARCH_WEB_HINTS) and not any(
                hint in text for hint in self.SEARCH_REVIEW_HINTS
            ):
                return None

        place_query = self.normalize_place_query(request_text)
        time_window = self.extract_time_window(text)
        review_signal = any(hint in text for hint in self.SEARCH_REVIEW_HINTS) or any(
            hint in text for hint in ("top rated", "best rated", "highest rated", "top 5", "top 10")
        ) or bool(
            re.search(r"\bbest\b", text)
            and any(hint in text for hint in self.SEARCH_PLACE_HINTS)
            and not any(hint in text for hint in self.INTENT_ADVICE_HINTS)
        )

        if review_signal and any(hint in text for hint in self.SEARCH_PLACE_HINTS) and place_query["needs_location"]:
            return {
                "capability": "search.places",
                "tool": "office.search_places",
                "arguments": {
                    "query": place_query["normalized_query"] or request_text,
                    "location": place_query["location"],
                    "category": place_query["category"],
                    "needs_location": True,
                    "limit": 5,
                },
                "reason": "Matched place lookup intent but needs a location.",
            }

        if review_signal and any(hint in text for hint in self.SEARCH_PLACE_HINTS):
            return {
                "capability": "search.reviews",
                "tool": "office.search_reviews",
                "arguments": {
                    "query": place_query["normalized_query"] or request_text,
                    "location": place_query["location"],
                    "time_window": time_window,
                    "limit": 5,
                },
                "reason": "Matched review and place lookup intent.",
            }

        if any(hint in text for hint in self.SEARCH_WEB_HINTS):
            return {
                "capability": "search.web",
                "tool": "office.search_web",
                "arguments": {
                    "query": request_text,
                    "limit": 5,
                },
                "reason": "Matched explicit web search intent.",
            }

        if any(hint in text for hint in self.SEARCH_PLACE_HINTS) and (
            place_query["is_explicit"] or place_query["location"] is not None or place_query["needs_location"]
        ):
            return {
                "capability": "search.places",
                "tool": "office.search_places",
                "arguments": {
                    "query": place_query["normalized_query"] or request_text,
                    "location": place_query["location"],
                    "category": place_query["category"],
                    "needs_location": place_query["needs_location"],
                    "limit": 5,
                },
                "reason": "Matched place lookup intent.",
            }

        return None

    def is_search_capability_question(self, text: str) -> bool:
        return bool(
            re.match(
                r"^(?:can|could|do)\s+you\s+(?:actually\s+|really\s+)?"
                r"(?:search(?:\s+the)?\s+(?:internet|web)|search\s+online|look\s+things\s+up|check\s+online|"
                r"use(?:\s+the)?\s+(?:internet|web)|access(?:\s+the)?\s+(?:internet|web)|browse(?:\s+the)?\s+web)\??$",
                text,
            )
        )

    def route_room_status_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        if not any(hint in text for hint in self.ROOM_STATUS_HINTS):
            return None
        return {
            "capability": "workspace.state.get",
            "tool": "office.state_get",
            "arguments": {
                "workspace_id": workspace_id,
            },
            "reason": "Matched a room status query.",
        }

    def _recent_assistant_turn(self, recent_turns: List[Dict[str, Any]], *, require_numbered_list: bool = False) -> Optional[str]:
        for turn in reversed(recent_turns[-8:]):
            if str(turn.get("role") or "").strip().lower() == "assistant":
                text = str(turn.get("text") or "").strip()
                if text and (not require_numbered_list or self.NUMBERED_LIST_ITEM_RE.search(text)):
                    return text
        return None

    def _recent_user_turn_before_assistant(self, recent_turns: List[Dict[str, Any]]) -> Optional[str]:
        seen_assistant = False
        for turn in reversed(recent_turns[-8:]):
            role = str(turn.get("role") or "").strip().lower()
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            if role == "assistant" and not seen_assistant:
                seen_assistant = True
                continue
            if seen_assistant and role == "user":
                return text
        return None

    def _recent_user_turns(self, recent_turns: List[Dict[str, Any]]) -> List[str]:
        rows: List[str] = []
        for turn in recent_turns[-8:]:
            if str(turn.get("role") or "").strip().lower() != "user":
                continue
            text = str(turn.get("text") or "").strip()
            if text:
                rows.append(text)
        return rows

    def _infer_followup_subject(self, recent_turns: List[Dict[str, Any]]) -> tuple[Optional[str], str]:
        assistant_text = self._recent_assistant_turn(recent_turns, require_numbered_list=True) or self._recent_assistant_turn(recent_turns) or ""
        user_text = self._recent_user_turn_before_assistant(recent_turns) or ""
        user_turns = self._recent_user_turns(recent_turns)
        combined = f"{user_text}\n{assistant_text}".lower()

        if "maslow" in combined:
            return "Maslow's hierarchy of needs", "level"

        for candidate_text in [user_text, *reversed(user_turns)]:
            if not candidate_text:
                continue
            for pattern in self.STRATEGY_TOPIC_PATTERNS:
                match = pattern.search(candidate_text)
                if match:
                    subject = re.sub(r"\s+", " ", match.group(1).strip(" .?!"))
                    if subject:
                        return subject, "option"

        for pattern in self.PRIOR_TOPIC_PATTERNS:
            match = pattern.search(user_text)
            if match:
                subject = re.sub(r"\s+", " ", match.group(1).strip(" .?!"))
                if subject:
                    return subject, "item"

        if assistant_text and self.NUMBERED_LIST_ITEM_RE.search(assistant_text):
            first_sentence = assistant_text.split("\n", 1)[0].strip()
            if first_sentence:
                return first_sentence.rstrip(".:"), "item"

        return None, "item"

    def _looks_like_contextual_followup(self, request_text: str) -> bool:
        lowered = re.sub(r"\s+", " ", request_text.strip().lower())
        if not lowered:
            return False
        if any(hint in lowered for hint in self.CONTEXTUAL_REFERENCE_HINTS):
            return True
        if len(lowered.split()) <= 8 and re.search(r"\b(it|that|those|them|one|ones|level)\b", lowered):
            return True
        return False

    def _extract_ordinal_reference(self, lowered: str) -> Optional[str]:
        if "first" in lowered:
            return "first"
        if "second" in lowered:
            return "second"
        if "third" in lowered:
            return "third"
        if "last" in lowered:
            return "last"
        return None

    def _extract_list_items(self, assistant_text: str) -> List[str]:
        text = re.sub(r"\s+", " ", assistant_text.strip())
        if not text:
            return []
        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        working = re.sub(
            r"^.*?(?:through a combination of|include|includes|including|are|is)\s+",
            "",
            first_sentence,
            flags=re.IGNORECASE,
        )
        working = working.strip(" .")
        if "," not in working and " and " not in working:
            return []
        working = re.sub(r",\s*(?:and|or)\s+", ", ", working, flags=re.IGNORECASE)
        parts = [re.sub(r"^(?:by|a|an|the)\s+", "", part.strip(" .")) for part in working.split(",")]
        cleaned = []
        for part in parts:
            if len(part) < 4:
                continue
            if part.lower().startswith(("this is because", "for example", "such as")):
                continue
            cleaned.append(part)
        unique: List[str] = []
        seen = set()
        for item in cleaned:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique if len(unique) >= 3 else []

    def _extract_primary_claim(
        self,
        assistant_text: str,
        *,
        subject: Optional[str] = None,
        unit: Optional[str] = None,
    ) -> Optional[str]:
        text = re.sub(r"\s+", " ", assistant_text.strip())
        if not text:
            return None

        bold_match = re.search(r"\*\*(.+?)\*\*", assistant_text)
        if bold_match:
            bold_value = re.sub(r"\s+", " ", bold_match.group(1).strip(" .,:;"))
            if subject == "Maslow's hierarchy of needs" and bold_value:
                return f"{bold_value} is the most powerful single {unit} of {subject} in marketing"
            return bold_value

        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        short_label = first_sentence.strip(" .,:;")
        if subject == "Maslow's hierarchy of needs" and unit == "level" and short_label:
            if re.fullmatch(r"[A-Za-z][A-Za-z -]{1,40}", short_label):
                return f"{short_label} is the most powerful single {unit} of {subject} in marketing"
        if unit == "option" and short_label:
            if re.fullmatch(r"[A-Za-z][A-Za-z '&-]{1,50}", short_label):
                return short_label
        if len(first_sentence) >= 12:
            return first_sentence.rstrip(".")
        return None

    def _normalize_option_subject(self, subject: str) -> str:
        text = re.sub(r"\s+", " ", str(subject or "").strip())
        return text

    def _extract_option_label(self, claim: str) -> str:
        text = re.sub(r"\s+", " ", str(claim or "").strip()).strip(" .")
        if not text:
            return text
        head = re.split(r"\s+is\s+", text, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,:;")
        return head or text

    def _rewrite_meta_reference_followup(
        self,
        request_text: str,
        recent_turns: List[Dict[str, Any]],
    ) -> Optional[str]:
        text = re.sub(r"\s+", " ", request_text.strip())
        if not text:
            return None
        if not any(pattern.match(text) for pattern in self.META_REFERENCE_PATTERNS):
            return None

        assistant_text = self._recent_assistant_turn(recent_turns)
        if not assistant_text:
            return None

        subject, unit = self._infer_followup_subject(recent_turns)
        claim = self._extract_primary_claim(
            assistant_text,
            subject=subject,
            unit=unit,
        )
        if not claim:
            return None

        if unit == "option" and subject:
            option_subject = self._normalize_option_subject(subject)
            option_label = self._extract_option_label(claim)
            return (
                f"Explain why you concluded that {option_label} is the strongest option for {option_subject}. "
                "Keep the explanation tied to the immediately previous answer, compare it briefly with the next strongest option, "
                "and keep it concrete to customer behavior."
            )
        return (
            f"Explain why you concluded that {claim}. "
            "Keep the explanation tied to the immediately previous answer, compare it briefly with the next strongest level, "
            "and keep it concrete to marketing behavior."
        )

    def _rewrite_contextual_reference_followup(
        self,
        request_text: str,
        recent_turns: List[Dict[str, Any]],
    ) -> Optional[str]:
        assistant_text = self._recent_assistant_turn(recent_turns, require_numbered_list=True) or self._recent_assistant_turn(recent_turns) or ""
        if not assistant_text:
            return None

        text = re.sub(r"\s+", " ", request_text.strip())
        lowered = text.lower()
        if not self._looks_like_contextual_followup(text):
            return None

        subject, unit = self._infer_followup_subject(recent_turns)
        if not subject:
            return None
        list_items = self._extract_list_items(assistant_text)

        if (
            any(phrase in lowered for phrase in ("most powerful one", "most powerful level", "which level", "what level"))
            and "marketing" in lowered
        ):
            return (
                f"Which single {unit} of {subject} is most powerful in marketing? "
                "Answer with one level first, then a brief reason."
            )
        if "how does that compare" in lowered:
            return f"How does that compare with the other {unit}s in {subject}?"
        if "would that work" in lowered or "does that work" in lowered:
            target_match = re.search(r"\bfor\s+([A-Za-z][A-Za-z0-9 '&-]{1,60})\??$", text, re.IGNORECASE)
            if target_match:
                target = re.sub(r"\s+too$", "", target_match.group(1).strip(), flags=re.IGNORECASE).strip()
                return f"Would that {unit} from {subject} also work for {target}?"
            return f"Would that {unit} from {subject} also work in a similar context?"
        if "strongest one" in lowered:
            return f"Which {unit} of {subject} is strongest?"
        if "best one" in lowered:
            return f"Which {unit} of {subject} is most effective?"
        if list_items and any(
            phrase in lowered
            for phrase in (
                "which one",
                "what one",
                "most effective one",
                "most powerful one",
                "strongest one",
                "best one",
            )
        ):
            items_text = ", ".join(list_items[:-1]) + f", or {list_items[-1]}" if len(list_items) > 1 else list_items[0]
            return (
                f"For {subject}, which single option is most effective out of these: {items_text}? "
                "Name one first, then briefly explain why."
            )
        ordinal = self._extract_ordinal_reference(lowered)
        if ordinal is not None and (self.NUMBERED_LIST_ITEM_RE.search(assistant_text) or list_items):
            return f"Tell me more about the {ordinal} {unit} in {subject}."
        if "which one" in lowered or "what one" in lowered:
            return f"Which single {unit} of {subject} is the best fit here? Answer with one {unit} first, then a brief reason."
        return None

    def route_contextual_followup(
        self,
        workspace_id: str,
        request_text: str,
        recent_turns: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        text = request_text.strip()
        lowered = re.sub(r"\s+", " ", text.lower())
        match = re.match(r"^(?:what|how)\s+about\s+(.+?)\??$", text, re.IGNORECASE)
        recent_text = "\n".join(str(turn.get("text") or "") for turn in recent_turns[-8:])
        recent_lower = recent_text.lower()
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

    def route_session_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        if not any(hint in text for hint in self.SESSION_CREATE_HINTS):
            return None
        title = re.sub(r"^(?:new|start|create)(?:\s+a|\s+an|\s+the)?\s+session", "", request_text, flags=re.IGNORECASE).strip(" .,:;")
        if title.lower().startswith("for "):
            title = title[4:].strip(" .,:;")
        if title.lower().startswith("about "):
            title = title[6:].strip(" .,:;")
        if not title:
            title = "New Session"
        return {
            "capability": "session.create",
            "tool": "office.session_create",
            "arguments": {
                "title": title,
                "description": title,
                "request_text": request_text,
            },
            "reason": "Matched a new session request.",
        }

    def route_ocr_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        if not any(hint in text for hint in self.OCR_EXPLICIT_HINTS):
            return None
        match = self.FILE_ID_RE.search(request_text)
        if match:
            return {
                "capability": "document.ocr",
                "tool": "office.ocr_extract",
                "arguments": {
                    "file_id": match.group(0),
                },
                "reason": "Matched OCR request with a file id.",
            }
        file_name_match = self.FILE_NAME_RE.search(request_text)
        if not file_name_match:
            read_file_match = re.search(
                r"\bread(?:\s+the)?\s+file\s+(?P<name>[A-Za-z0-9_().-]{1,120})\b",
                request_text,
                re.IGNORECASE,
            )
            if not read_file_match:
                return None
            file_name = read_file_match.group("name").strip()
            return {
                "capability": "document.ocr",
                "tool": "office.ocr_extract",
                "arguments": {
                    "file_name": file_name,
                },
                "reason": "Matched OCR request with a file reference.",
            }
        return {
            "capability": "document.ocr",
            "tool": "office.ocr_extract",
            "arguments": {
                "file_name": file_name_match.group("name").strip(),
            },
            "reason": "Matched OCR request with a file name.",
        }

    def is_explicit_room_navigation(self, request_text: str) -> bool:
        text = request_text.strip().lower()
        if not text:
            return False
        return any(text.startswith(prefix) for prefix in self.ROOM_NAVIGATION_PREFIXES) or self.ROOM_NAVIGATION_RE.search(text) is not None

    def extract_location(self, request_text: str) -> Optional[str]:
        match = re.search(r"\bin\s+([A-Za-z][A-Za-z0-9 .,'&-]{1,60})", request_text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip(" .")

    def extract_time_window(self, text: str) -> Optional[str]:
        if "last month" in text:
            return "last month"
        if "last week" in text:
            return "last week"
        if "today" in text:
            return "today"
        return None

    def extract_place_category(self, text: str) -> Optional[str]:
        for candidate in (
            "restaurant",
            "restaurants",
            "resaurnat",
            "resaurnats",
            "restaurnat",
            "restaurnats",
            "resteraunt",
            "resteraunts",
            "restaraunt",
            "restaraunts",
            "resturant",
            "resturants",
            "bar",
            "bars",
            "coffee",
            "cafe",
            "hotel",
            "hotels",
            "thai",
        ):
            if candidate in text:
                return candidate
        return None

    def suggest_correction(self, request_text: str) -> Optional[Dict[str, str]]:
        words = re.findall(r"[A-Za-z]{4,}", request_text.lower())
        if not words:
            return None
        vocabulary = list(dict.fromkeys(self.CORRECTION_VOCABULARY + tuple(normalize_room_text(room.get("title", "")) for room in rooms_payload())))
        vocabulary = [word for phrase in vocabulary for word in phrase.split() if len(word) >= 4]
        for word in words:
            if word in vocabulary:
                continue
            matches = difflib.get_close_matches(word, vocabulary, n=1, cutoff=0.84)
            if matches:
                suggestion = matches[0]
                if suggestion.startswith(word) or word.startswith(suggestion):
                    continue
                return {
                    "word": word,
                    "suggestion": suggestion,
                    "response_text": f"Did you mean \"{suggestion}\" when you wrote \"{word}\"?",
                }
        return None

    def normalize_place_query(self, request_text: str) -> Dict[str, Any]:
        text = request_text.strip()
        lowered = text.lower().strip()
        lowered = re.sub(r"\b(?:resaurnats|restaurnats|resteraunts|restaraunts|resturants)\b", "restaurants", lowered)
        lowered = re.sub(r"\b(?:resaurnat|restaurnat|resteraunt|restaraunt|resturant)\b", "restaurant", lowered)
        lowered = re.sub(r"^[\s,]*(?:find|show me|list|recommend|give me)\s+", "", lowered).strip()
        lowered = re.sub(r"\b(?:near me|nearby|around me)\b", "", lowered).strip()
        location = self.extract_location(text)
        lowered = re.sub(r"\bin\s+[A-Za-z][A-Za-z0-9 .,'&-]{1,60}", "", lowered, flags=re.IGNORECASE).strip()
        lowered = lowered.strip(" .,!?:;")
        if lowered.startswith("the "):
            lowered = lowered[4:].strip()
        cuisine_match = re.search(r"\b([A-Za-z][A-Za-z0-9&'-]{1,40})\s+restaurants?\b", lowered or text, re.IGNORECASE)
        if cuisine_match and cuisine_match.group(1).lower() not in {"best", "top", "local", "good", "great"}:
            cuisine = cuisine_match.group(1).strip().lower()
            category = cuisine
            normalized_query = f"{cuisine} restaurants"
        else:
            category = self.extract_place_category(lowered or text)
            category_map = {
                "restaurant": "restaurants",
                "restaurants": "restaurants",
                "resaurnat": "restaurants",
                "resaurnats": "restaurants",
                "restaurnat": "restaurants",
                "restaurnats": "restaurants",
                "resteraunt": "restaurants",
                "resteraunts": "restaurants",
                "restaraunt": "restaurants",
                "restaraunts": "restaurants",
                "resturant": "restaurants",
                "resturants": "restaurants",
                "bar": "bars",
                "bars": "bars",
                "coffee": "coffee",
                "cafe": "cafe",
                "hotel": "hotels",
                "hotels": "hotels",
            }
            category = category_map.get(category or "", category)
            if category in {"restaurants", "bars", "hotels"} and (
                lowered == category or any(marker in lowered for marker in ("best", "top", "local"))
            ):
                normalized_query = category
            else:
                normalized_query = lowered or category or ""
        normalized_query = re.sub(r"\s+", " ", normalized_query).strip()
        needs_location = bool(
            not location and any(marker in text.lower() for marker in ("near me", "nearby", "around me", "best ", "top ", "local"))
        )
        is_explicit = bool(
            re.match(r"^(find|show me|list|recommend|give me)\b", text.strip(), re.IGNORECASE)
            or location is not None
            or " near " in f" {text.lower()} "
        )
        return {
            "normalized_query": normalized_query,
            "category": category,
            "location": location,
            "needs_location": needs_location,
            "is_explicit": is_explicit,
        }

    def mailroom_header(self, to_persona: str, dest_room_title: str, subject: str) -> str:
        return f"Memo filed to: {to_persona} ({dest_room_title})\\nSubject: {subject}\\n"

    def mailroom_response(
        self,
        *,
        workspace_id: str,
        memo_id: str,
        from_room: str,
        to_room: str,
        to_persona: str,
        subject: str,
        dest_room_title: str,
    ) -> Dict[str, Any]:
        header = self.mailroom_header(to_persona, dest_room_title, subject)
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "memo_id": memo_id,
                "from_room": from_room,
                "to_room": to_room,
                "to_persona": to_persona,
                "subject": subject,
                "is_refusal": False,
                "closure_appended": False,
                "response_text": header,
            },
            "content": [{"type": "text", "text": header}],
        }

    def memos_list_response(self, workspace_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "structuredContent": {"workspace_id": workspace_id, "count": len(rows), "memos": rows},
            "content": [{"type": "text", "text": f"Found {len(rows)} memo(s)."}],
        }

    def memo_get_text(self, obj: Dict[str, Any], body: str) -> str:
        return (
            f"Memo {obj.get('memo_id')}\\n"
            f"From: {obj.get('from_room')}\\n"
            f"To: {obj.get('to_room')} ({obj.get('to_persona')})\\n"
            f"Subject: {obj.get('subject')}\\n\\n"
            f"{body}"
        )

    def memo_get_response(self, obj: Dict[str, Any], body: str) -> Dict[str, Any]:
        return {
            "structuredContent": obj,
            "content": [{"type": "text", "text": self.memo_get_text(obj, body)}],
        }
