from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from office_app.server.conversation_planner import ConversationPlanner
from office_app.server.request_followup import RequestFollowupRouter
from office_app.server.request_grounding import EntityGroundingRouter
from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.request_intent import RequestIntentAnalyzer, RequestIntentConfig
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
        "what memory items do you have saved",
        "what memory items do i have saved",
        "what memory items are saved",
        "what memories do you have saved",
        "what memories do i have saved",
        "what memories are saved",
        "what do you remember",
        "what do you remember in",
        "show memory objects",
        "show memory items",
        "list memory objects",
        "list memory items",
        "list saved memories",
        "show saved memories",
        "what memory items are saved now",
        "what memory objects are saved now",
        "what memories are saved now",
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
    SEARCH_PRODUCT_HINTS = (
        "cellphone",
        "cellphones",
        "phone",
        "phones",
        "smartphone",
        "smartphones",
        "camera",
        "cameras",
        "laptop",
        "laptops",
        "tv",
        "tvs",
        "television",
        "televisions",
        "headphone",
        "headphones",
        "earbud",
        "earbuds",
        "tablet",
        "tablets",
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
        "mall",
        "malls",
        "shopping mall",
        "shopping center",
        "shopping centre",
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
        "what was wrong with the question",
        "what went wrong",
        "what should have happened",
        "what was wrong",
        "why was that wrong",
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
        "Apply persona behavior memory as style guidance when present, but do not echo the source book or memory label unless the user explicitly asks about it. "
        "Use the provided session conversation history as the current chat thread. "
        "When the user asks a follow-up, comparison, pronoun-based question, 'what about ...', or 'how about ...', "
        "resolve it against the immediately relevant prior turns instead of treating it as a blank new chat. "
        "If the user pastes prior assistant output, logs, or transcript text, treat it as evidence to analyze rather than a brand-new question. "
        "Bind your answer to the exact pasted text and do not reinterpret it into an unrelated topic. "
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
    MODEL_GROUNDING_RULE = (
        "For factual questions about a specific company, entity, or person, do not invent unsupported details. "
        "If verified grounding is missing, say so directly and offer search when appropriate."
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
    SESSION_INFO_HINTS = (
        "what is the name of this session",
        "what is this session called",
        "what session is this",
        "what is this session",
        "what's the name of this session",
        "what's this session called",
        "what is the title of this session",
        "current session title",
        "session name",
    )
    SESSION_RENAME_HINTS = (
        "rename this session",
        "rename session",
        "retitle this session",
        "retitle session",
        "change this session name",
        "change session name",
    )
    SESSION_REQUEST_RE = re.compile(
        r"^(?:new|start|create)(?:\s+a|\s+an|\s+the)?(?:\s+new)?\s+session(?:\s+for|\s+about|\s+called|\s+named)?\s*(.*)$",
        re.IGNORECASE,
    )
    SESSION_INFO_RE = re.compile(
        r"^(?:what(?:'s| is)?|tell\s+me|give\s+me)\s+(?:the\s+)?(?:name|title)\s+of\s+(?:this|the|my|current)\s+session\??$"
        r"|^(?:what(?:'s| is)?\s+this\s+session(?:\s+called)?\??)$"
        r"|^(?:what\s+session\s+is\s+this\??)$",
        re.IGNORECASE,
    )
    SESSION_RENAME_RE = re.compile(
        r"^(?:rename|retitle|change)(?:\s+this)?\s+session(?:\s+to|\s+as|\s+named|\s+called)?\s*(.*)$",
        re.IGNORECASE,
    )
    SESSION_LIST_HINTS = (
        "list sessions",
        "show sessions",
        "show me the sessions",
        "show me all sessions",
        "what sessions do i have",
        "what sessions are there",
        "what are my sessions",
        "which sessions do i have",
    )
    SESSION_LIST_CLARIFY_RE = re.compile(
        r"^(?:what|which)\s+sessions?\b.*(?:are\s+there|in\s+(?:this|the|my|our|current)\s+(?:workspace|room)|here)\b.*$",
        re.IGNORECASE,
    )
    SESSION_LIST_RE = re.compile(
        r"^(?:show|display|list|give\s+me|tell\s+me|which)\b.*\bsessions?\b"
        r"(?:\s+in\s+(?:this|the|my|our|current)\s+(?:workspace|room))?"
        r"(?:\s+here)?\??$",
        re.IGNORECASE,
    )
    WHAT_SESSIONS_LIST_RE = re.compile(
        r"^what\s+sessions?\b.*$",
        re.IGNORECASE,
    )
    SESSION_ACTIVATE_RE = re.compile(
        r"^(?:go(?:\s+back)?\s+to|switch\s+to|activate|open|return\s+to)\s+session\s+(.+?)\??$",
        re.IGNORECASE,
    )
    SESSION_SEARCH_RE = re.compile(
        r"^(?:search|look(?:\s+through)?|check|scan)\s+(?:my\s+|the\s+)?(?:(other|all)\s+)?sessions\s+(?:for|about)\s+(.+?)\??$",
        re.IGNORECASE,
    )
    SESSION_SEARCH_DETAIL_RE = re.compile(
        r"^(?:display|show|list|summarize|tell\s+me)\s+(?:the\s+)?"
        r"(?:information|details|results|responses|answers)\s+"
        r"(?:the\s+)?sessions\s+(?:gave|said|had)\s+(?:about|for)\s+(.+?)\??$",
        re.IGNORECASE,
    )
    WORKSPACE_REFERENCE_SEARCH_RE = re.compile(
        r"^(?:can\s+you\s+)?(?:search|check|scan|look(?:\s+through)?)\s+"
        r"(?:the\s+)?(?:current\s+)?workspace\b.*\b(?:references?|mentions?|info(?:rmation)?)\b.*\b(?:to|for|about)\s+(.+?)\??$",
        re.IGNORECASE,
    )
    PREVIOUS_SESSIONS_ENTITY_RE = re.compile(
        r"^(?:what|which|can\s+you(?:\s+give|\s+show|\s+tell)\s+me).*\b(?:previous|other|past)\s+sessions\b.*$",
        re.IGNORECASE,
    )
    SESSION_THREAD_HINTS = (
        "show this sessions thread",
        "show this session thread",
        "show this session's thread",
        "show session thread",
        "show this thread",
        "show this session conversation",
        "show this session transcript",
        "show this thread history",
        "show this session history",
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
    FACTUAL_ENTITY_LOOKUP_PATTERNS = (
        re.compile(r"^(?:what\s+can\s+you\s+tell\s+me\s+about|what\s+do\s+you\s+know\s+about|tell\s+me\s+about|information\s+about)\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"^(?:who|what)\s+is\s+(.+?)\??$", re.IGNORECASE),
    )
    FACTUAL_ENTITY_SEARCH_PATTERNS = (
        re.compile(r"^(?:search(?:\s+the\s+(?:web|internet))?\s+for|search\s+online\s+for|look\s+up)\s+(.+?)\??$", re.IGNORECASE),
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
        self.intent_analyzer = RequestIntentAnalyzer(
            RequestIntentConfig(
                artifact_create_triggers=self.ARTIFACT_CREATE_TRIGGERS,
                artifact_list_triggers=self.ARTIFACT_LIST_TRIGGERS,
                artifact_open_triggers=self.ARTIFACT_OPEN_TRIGGERS,
                factual_entity_lookup_patterns=self.FACTUAL_ENTITY_LOOKUP_PATTERNS,
                factual_entity_search_patterns=self.FACTUAL_ENTITY_SEARCH_PATTERNS,
                file_id_re=self.FILE_ID_RE,
                file_name_re=self.FILE_NAME_RE,
                intent_advice_hints=self.INTENT_ADVICE_HINTS,
                intent_meta_hints=self.INTENT_META_HINTS,
                ocr_explicit_hints=self.OCR_EXPLICIT_HINTS,
                room_status_hints=self.ROOM_STATUS_HINTS,
                search_business_advice_hints=self.SEARCH_BUSINESS_ADVICE_HINTS,
                search_place_hints=self.SEARCH_PLACE_HINTS,
                search_review_hints=self.SEARCH_REVIEW_HINTS,
                search_web_hints=self.SEARCH_WEB_HINTS,
                session_create_hints=self.SESSION_CREATE_HINTS,
            ),
            normalize_place_query=self.normalize_place_query,
            is_explicit_room_navigation=self.is_explicit_room_navigation,
        )
        self.entity_grounding = EntityGroundingRouter(
            extract_factual_entity_request=self.intent_analyzer.extract_factual_entity_request,
            load_recent_transcript_turns=lambda workspace_id, session_id=None: self._load_recent_transcript_turns(
                workspace_id,
                session_id=session_id,
            ),
            resolve_active_room_title=lambda workspace_id: self.room_title_for_id(
                str(self.current_context(workspace_id).get("active_room") or "lobby")
            ),
        )
        self.followup_router = RequestFollowupRouter(
            conversation_planner=self.conversation_planner,
            model_route=lambda workspace_id, user_prompt, **kwargs: self.model_route(
                workspace_id,
                user_prompt,
                reason=str(kwargs.get("reason") or ""),
                apply_conversation_plan=bool(kwargs.get("apply_conversation_plan", True)),
            ),
            extract_location=self.extract_location,
            load_grounded_search_context=lambda workspace_id, session_id=None: self._load_grounded_search_context(
                workspace_id,
                session_id=session_id,
            ),
        )

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

    def route_user_request(self, workspace_id: str, request_text: str, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        recent_turns = self._load_recent_transcript_turns(workspace_id, session_id=session_id)

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

        session_thread_route = self.route_session_thread_request(workspace_id, request_text)
        if session_thread_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **session_thread_route,
            }

        session_route = self.route_session_request(workspace_id, request_text)
        if session_route is not None:
            if "route_kind" in session_route:
                return {
                    "workspace_id": workspace_id,
                    "request": request_text,
                    **session_route,
                }
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **session_route,
            }

        contextual_followup_route = self.route_contextual_followup(
            workspace_id,
            request_text,
            recent_turns,
            session_id=session_id,
        )
        if contextual_followup_route is not None:
            return contextual_followup_route

        capability_route = self.route_capability_question(workspace_id, request_text)
        if capability_route is not None:
            return capability_route

        product_search_route = self.route_product_search_request(workspace_id, request_text)
        if product_search_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **product_search_route,
            }

        intent = self.classify_intent(request_text)
        if intent in {"meta", "advice"}:
            return self.model_route(
                workspace_id,
                request_text,
                reason=f"Classified as {intent} intent before tool routing.",
            )

        factual_entity_route = self.route_factual_entity_request(
            workspace_id,
            request_text,
            session_id=session_id,
        )
        if factual_entity_route is not None:
            return factual_entity_route

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

        status_route = self.route_room_status_request(workspace_id, request_text)
        if status_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **status_route,
            }

        search_route = self.route_search_request(workspace_id, request_text)
        if search_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **search_route,
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
            f"{self.MODEL_CAPABILITY_RULE} {self.MODEL_RISK_RULE} {self.MODEL_GROUNDING_RULE}"
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

    def _load_recent_transcript_turns(self, workspace_id: str, *, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        store = getattr(self.kernel, "store", None)
        loader = getattr(store, "load_transcript", None)
        if loader is None:
            return []
        try:
            return loader(workspace_id, limit=24, session_id=session_id)
        except Exception:
            return []

    def _load_grounded_search_context(self, workspace_id: str, *, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        try:
            state = self.kernel.get_state(workspace_id)
        except Exception:
            return None
        contexts = state.get("grounded_search_by_session")
        if not isinstance(contexts, dict):
            return None
        context = contexts.get(session_id)
        return context if isinstance(context, dict) else None

    def _clean_entity_subject(self, subject: str) -> str:
        return self.intent_analyzer.clean_entity_subject(subject)

    def _looks_like_specific_entity(self, subject: str) -> bool:
        return self.intent_analyzer.looks_like_specific_entity(subject)

    def extract_factual_entity_request(self, request_text: str) -> Optional[Dict[str, Any]]:
        return self.intent_analyzer.extract_factual_entity_request(request_text)

    def entity_has_verified_grounding(
        self,
        workspace_id: str,
        entity_subject: str,
        *,
        session_id: Optional[str] = None,
    ) -> bool:
        return self.entity_grounding.entity_has_verified_grounding(
            workspace_id,
            entity_subject,
            session_id=session_id,
        )

    def route_factual_entity_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.entity_grounding.route_factual_entity_request(
            workspace_id,
            request_text,
            session_id=session_id,
        )

    def place_search_signals(self, request_text: str) -> Dict[str, Any]:
        return self.intent_analyzer.place_search_signals(request_text)

    def classify_intent(self, request_text: str) -> str:
        return self.intent_analyzer.classify_intent(request_text)

    def is_meta_intent(self, text: str) -> bool:
        return self.intent_analyzer.is_meta_intent(text)

    def is_advice_intent(self, text: str) -> bool:
        return self.intent_analyzer.is_advice_intent(text)

    def is_explicit_task_intent(self, request_text: str) -> bool:
        return self.intent_analyzer.is_explicit_task_intent(request_text)

    def route_search_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        if self.is_search_capability_question(text):
            return None
        entity_request = self.extract_factual_entity_request(request_text)
        if entity_request is not None and entity_request.get("search_requested"):
            entity_subject = str(entity_request["entity_subject"])
            return {
                "capability": "search.web",
                "tool": "office.search_web",
                "arguments": {
                    "query": entity_subject,
                    "limit": 5,
                },
                "reason": "Matched explicit search intent for a specific entity.",
                "grounding_required": True,
                "entity_subject": entity_subject,
            }

        if any(hint in text for hint in self.SEARCH_BUSINESS_ADVICE_HINTS):
            if not any(hint in text for hint in self.SEARCH_WEB_HINTS) and not any(
                hint in text for hint in self.SEARCH_REVIEW_HINTS
            ):
                return None

        place_signals = self.place_search_signals(request_text)
        place_query = dict(place_signals["place_query"])
        time_window = self.extract_time_window(text)
        review_signal = place_signals["review_signal"]
        mall_discovery_signal = bool(
            re.search(r"\b(?:which\s+ones?|what\s+are\s+they|what\s+ones?)\b", text)
            and any(hint in text for hint in ("mall", "malls", "shopping mall", "shopping center", "shopping centre"))
        )
        if mall_discovery_signal:
            place_query["category"] = place_query.get("category") or "malls"
            if not place_query.get("normalized_query"):
                place_query["normalized_query"] = "malls"
        place_task = bool(
            place_signals["has_place_hint"]
            and (place_signals["discovery_signal"] or review_signal or mall_discovery_signal)
            and (place_signals["location_signal"] or place_signals["explicit_review_signal"])
        )

        if review_signal and place_signals["has_place_hint"] and place_query["needs_location"]:
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

        if review_signal and place_signals["has_place_hint"] and place_task:
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

        if place_task:
            normalized_query = place_query["normalized_query"] or request_text
            if place_query.get("category") and place_query.get("location"):
                normalized_query = str(place_query["category"])
            if mall_discovery_signal:
                normalized_query = "malls"
            return {
                "capability": "search.places",
                "tool": "office.search_places",
                "arguments": {
                    "query": normalized_query,
                    "location": place_query["location"],
                    "category": place_query["category"],
                    "needs_location": place_query["needs_location"],
                    "limit": 5,
                },
                "reason": "Matched place lookup intent.",
            }

        return None

    def route_product_search_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        has_product_hint = any(hint in text for hint in self.SEARCH_PRODUCT_HINTS)
        if not has_product_hint:
            return None
        product_comparison_signal = bool(
            re.search(r"\b(best|top|highest rated|most reliable|most durable|which\s+is\s+best|which\s+one\s+is\s+best|compare|comparison|versus|vs\.?)\b", text)
        )
        if not product_comparison_signal:
            return None
        return {
            "capability": "search.web",
            "tool": "office.search_web",
            "arguments": {
                "query": request_text,
                "limit": 5,
            },
            "reason": "Matched product research intent.",
        }

    def is_search_capability_question(self, text: str) -> bool:
        return self.intent_analyzer.is_search_capability_question(text)

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

    def route_contextual_followup(
        self,
        workspace_id: str,
        request_text: str,
        recent_turns: List[Dict[str, Any]],
        *,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.followup_router.route_contextual_followup(
            workspace_id,
            request_text,
            recent_turns,
            session_id=session_id,
        )

    def route_session_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        entity_request = self.intent_analyzer.extract_factual_entity_request(request_text)
        if self.PREVIOUS_SESSIONS_ENTITY_RE.match(request_text.strip()) and entity_request is not None:
            query = self._normalize_session_search_query(str(entity_request.get("entity_subject") or ""))
            if query:
                return {
                    "capability": "session.search",
                    "tool": "office.sessions_search",
                    "arguments": {
                        "query": query,
                        "include_current": False,
                        "detail": True,
                    },
                    "reason": "Matched a request for topic information from previous sessions.",
                }
        workspace_search_match = self.WORKSPACE_REFERENCE_SEARCH_RE.match(request_text.strip())
        if workspace_search_match:
            query = self._normalize_session_search_query(str(workspace_search_match.group(1) or ""))
            if query:
                return {
                    "capability": "session.search",
                    "tool": "office.sessions_search",
                    "arguments": {
                        "query": query,
                        "include_current": True,
                        "detail": True,
                    },
                    "reason": "Matched a request to search current workspace session references for a topic.",
                }
        detail_match = self.SESSION_SEARCH_DETAIL_RE.match(request_text.strip())
        if detail_match:
            query = self._normalize_session_search_query(str(detail_match.group(1) or ""))
            if query:
                return {
                    "capability": "session.search",
                    "tool": "office.sessions_search",
                    "arguments": {
                        "query": query,
                        "include_current": False,
                        "detail": True,
                    },
                    "reason": "Matched a request to display detailed session transcript information about a topic.",
                }
        search_match = self.SESSION_SEARCH_RE.match(request_text.strip())
        if search_match:
            query = self._normalize_session_search_query(str(search_match.group(2) or ""))
            if query:
                return {
                    "capability": "session.search",
                    "tool": "office.sessions_search",
                    "arguments": {
                        "query": query,
                        "include_current": str(search_match.group(1) or "").strip().lower() != "other",
                    },
                    "reason": "Matched a request to search session transcripts.",
                }
        activate_match = self.SESSION_ACTIVATE_RE.match(request_text.strip())
        if activate_match:
            session_ref = re.sub(r"\s+", " ", str(activate_match.group(1) or "").strip(" .,:;"))
            if session_ref:
                return {
                    "capability": "session.activate",
                    "tool": "office.session_activate",
                    "arguments": {
                        "session_ref": session_ref,
                    },
                    "reason": "Matched a session switch request.",
                }
        if self.SESSION_LIST_CLARIFY_RE.match(request_text.strip()):
            return {
                "route_kind": "clarify",
                "capability": "session.list.confirmation",
                "tool": "office.capability_info",
                "arguments": {
                    "response_text": "Do you want me to list the sessions in this workspace?",
                },
                "reason": "Matched an ambiguous session list request.",
            }
        if any(hint in text for hint in self.SESSION_RENAME_HINTS):
            match = self.SESSION_RENAME_RE.match(request_text.strip())
            title = str(match.group(1) if match else "").strip(" .,:;")
            if title:
                return {
                    "capability": "session.rename",
                    "tool": "office.session_rename",
                    "arguments": {
                        "title": title,
                        "description": title,
                    },
                    "reason": "Matched a session rename request.",
                }
            return {
                "route_kind": "clarify",
                "capability": "session.rename.name_required",
                "tool": "office.session_rename",
                "arguments": {
                    "response_text": "What should I rename the session to?",
                },
                "reason": "Need a new session title before renaming the session.",
            }
        if any(hint in text for hint in self.SESSION_INFO_HINTS) or self.SESSION_INFO_RE.match(request_text.strip()):
            return {
                "capability": "session.info",
                "tool": "office.session_info",
                "arguments": {},
                "reason": "Matched a request for the current session name or title.",
            }
        if (
            any(hint in text for hint in self.SESSION_LIST_HINTS)
            or self.SESSION_LIST_RE.match(request_text.strip())
            or self.WHAT_SESSIONS_LIST_RE.match(request_text.strip())
        ):
            return {
                "capability": "session.list",
                "tool": "office.sessions_list",
                "arguments": {},
                "reason": "Matched a session list request.",
            }
        if not any(hint in text for hint in self.SESSION_CREATE_HINTS):
            return None
        match = self.SESSION_REQUEST_RE.match(request_text.strip())
        title = str(match.group(1) if match else "").strip(" .,:;")
        if title.lower().startswith("for "):
            title = title[4:].strip(" .,:;")
        if title.lower().startswith("about "):
            title = title[6:].strip(" .,:;")
        if not title:
            return {
                "route_kind": "clarify",
                "capability": "session.create.name_required",
                "tool": "office.session_create",
                "arguments": {
                    "response_text": "What should I name the new session?",
                },
                "reason": "Need a session name before creating a new session.",
            }
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

    def route_session_thread_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip().lower())
        if not text:
            return None
        if not any(hint in text for hint in self.SESSION_THREAD_HINTS):
            return None
        return {
            "capability": "workspace.transcript.get",
            "tool": "office.transcript_get",
            "arguments": {
                "limit": 24,
            },
            "reason": "Matched a request to show the current session thread.",
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
        location = re.sub(r"\s+", " ", match.group(1)).strip(" .")
        location = re.split(
            r"[.?!,]|(?:\s+(?:and|or|but|with|who|which|that|what|can|could|would|do|does|we|you)\b)",
            location,
            maxsplit=1,
        )[0].strip(" .")
        return location or None

    def extract_time_window(self, text: str) -> Optional[str]:
        if "last month" in text:
            return "last month"
        if "last week" in text:
            return "last week"
        if "today" in text:
            return "today"
        return None

    @staticmethod
    def _normalize_session_search_query(query: str) -> str:
        text = re.sub(r"\s+", " ", str(query or "").strip(" .,:;?!"))
        text = re.sub(r"^(?:info(?:rmation)?|references?|mentions?)\s+(?:about|for|to)\s+", "", text, flags=re.IGNORECASE)
        if text.lower().endswith(" information"):
            text = text[:-12].rstrip(" .,:;?!")
        return text

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
            "mall",
            "malls",
            "shopping mall",
            "shopping center",
            "shopping centre",
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
        if location:
            lowered = re.sub(
                rf"\bin\s+{re.escape(location)}\b",
                "",
                lowered,
                flags=re.IGNORECASE,
            ).strip()
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
                "mall": "malls",
                "malls": "malls",
                "shopping mall": "malls",
                "shopping center": "malls",
                "shopping centre": "malls",
            }
            category = category_map.get(category or "", category)
            if category in {"restaurants", "bars", "hotels", "malls"} and (
                lowered == category or any(marker in lowered for marker in ("best", "top", "local"))
            ):
                normalized_query = category
            else:
                normalized_query = lowered or category or ""
            if category == "malls" and location and any(marker in lowered for marker in ("which one", "which ones", "major mall", "major malls", "tell me")):
                normalized_query = "malls"
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
