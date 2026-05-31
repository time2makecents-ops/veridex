from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from office_app.server.conversation_planner import ConversationPlanner
from office_app.server.governance_registry_service import GovernanceRegistryService
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


def room_reference_aliases(room: Dict[str, Any]) -> List[str]:
    room_id = str(room.get("id") or "").strip()
    title = str(room.get("title") or room_id).strip()
    raw_aliases = {
        room_id,
        title,
        title.replace("&", "and"),
        title.replace("Department", "").replace("department", ""),
        room_id.replace("_department", "").replace("_room", "").replace("_office", ""),
    }

    id_base = room_id
    for suffix in ("_department", "_room", "_office"):
        if id_base.endswith(suffix):
            id_base = id_base[: -len(suffix)]
            break
    id_base_words = id_base.replace("_", " ").strip()
    if id_base_words:
        raw_aliases.update(
            {
                id_base_words,
                f"{id_base_words} room",
                f"{id_base_words} department",
                f"{id_base_words} office",
            }
        )

    special_aliases = {
        "control_room": ("navigator", "navigator room", "control"),
        "marketing_room": ("marketing", "marketing room", "advertising", "advertising room"),
        "art_department": ("art", "art room", "creative", "creative room"),
        "records_archive": ("archive", "archive room", "records", "records room"),
        "rnd_room": ("r d", "r and d", "rnd", "rnd room", "research", "research room", "research and development"),
        "hr_department": ("hr", "hr room", "human resources", "human resources room"),
        "it_department": ("it", "it room", "tech", "tech room", "technical support"),
        "my_office": ("office", "my office", "nancy", "nancy office"),
        "lobby": ("reception", "reception desk", "front desk"),
    }
    raw_aliases.update(special_aliases.get(room_id, ()))

    aliases: List[str] = []
    for alias in raw_aliases:
        normalized = normalize_room_text(alias)
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


def _default_governance_registry_service() -> GovernanceRegistryService:
    server_dir = Path(__file__).resolve().parent
    pkg_dir = server_dir.parent
    root_dir = pkg_dir.parent
    return GovernanceRegistryService(
        registry_path=pkg_dir / "backend" / "registry.csv",
        governance_guide_path=root_dir / "01_Architecture" / "Veridex_Governance_Guide_v1.0.0.md",
        room_state_model_path=root_dir / "01_Architecture" / "Room_State_Model_v1.0.0.md",
        mailroom_contract_path=root_dir / "01_Architecture" / "Mailroom_Dispatch_Contract_v1.0.0.md",
        persona_registry_path=server_dir / "persona_registry.py",
        room_registry_path=server_dir / "room_router.py",
    )


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
        "list all objects saved",
        "show all objects saved",
        "what are all the objects saved",
        "what memory objects are saved",
        "what are the memory objects saved",
        "what memory objects do you have saved",
        "what memory objects do i have saved",
        "what memory items are saved",
        "what are the memory items saved",
        "what memory items do you have saved",
        "what memory items do i have saved",
        "what objects are saved",
        "what are the objects saved",
        "what objects do you have saved",
        "what objects do i have saved",
        "what objects are saved in the workspace",
        "what are the objects saved in the workspace",
        "what objects are saved in this workspace",
        "what are the objects saved in this workspace",
        "what workspace objects are saved",
        "what saved objects are in the workspace",
        "list objects",
        "show objects",
        "list saved objects",
        "show saved objects",
    )
    ARTIFACT_OPEN_TRIGGERS = (
        "open artifact",
        "open the artifact",
        "view artifact",
        "read artifact",
    )
    ARTIFACT_DELETE_TRIGGERS = (
        "delete",
        "remove",
        "trash",
    )
    OBJECT_SCOPE_CLARIFICATION_HINTS = (
        "what objects are saved",
        "what are the objects saved",
        "what are all the objects saved",
        "what objects do you have saved",
        "what objects do i have saved",
        "list objects",
        "show objects",
        "list saved objects",
        "show saved objects",
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
    OCR_FILE_NAME_WITH_SPACES_RE = re.compile(
        r"""\b(?:from|file)\s+[“"'`]?
        (?P<name>(?:[A-Za-z0-9_().-]+\s+)*[A-Za-z0-9_().-]+\.(?:txt|rtf|pdf|png|jpg|jpeg|webp|gif|bmp|tif|tiff|md|csv|json|xml|html|htm|doc|docx))
        [”"'`]?(?=\s|$|[?.!,])""",
        re.IGNORECASE | re.VERBOSE,
    )
    ARTIFACT_DELETE_NUMBER_RE = re.compile(
        r"^(?:delete|remove|trash)\s+(?:number\s+|item\s+|artifact\s+|#)?(?P<index>\d+)\b.*$",
        re.IGNORECASE,
    )
    ARTIFACT_DELETE_ID_RE = re.compile(
        r"^(?:delete|remove|trash)\s+(?:the\s+)?(?:artifact\s+)?(?P<artifact_id>art_[A-Za-z0-9]+)\b.*$",
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
        "what do you remember",
        "what do you remember in",
        "what room behavior memories are saved",
        "what behavior memories are saved",
        "what behavior memories do you have saved",
        "what behavior memories do i have saved",
        "what behavior objects are saved",
        "what are the behavior objects saved",
        "what objects are saved in this room",
        "what are the objects saved in this room",
        "show behavior memories",
        "show room behavior memories",
        "list behavior memories",
        "list room behavior memories",
        "list saved behavior memories",
        "show saved behavior memories",
        "what behavior memories are saved now",
        "what room behavior memories are saved now",
    )
    MEMO_DISPATCH_RE = re.compile(
        r"^(?:please\s+)?(?:send|file|dispatch)\s+(?:a\s+)?memo\s+to\s+(?P<target>[^.?!:;,]+)[.?!:;,-]*\s*(?P<body>.*)$",
        re.IGNORECASE,
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
    NON_NAVIGATION_GO_TO_PATTERNS = (
        re.compile(r"\bwhy\s+did\b.+\bgo\s+to\b", re.IGNORECASE),
        re.compile(r"\byou\s+asked\b.+\bgo\s+to\b", re.IGNORECASE),
        re.compile(r"\bthe\s+pun\b.+\bgo\s+to\b", re.IGNORECASE),
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
    ROOM_DIRECTORY_HINTS = (
        "what rooms are there",
        "what rooms do you have",
        "what departments are there",
        "what departments do you have",
        "is there a list of places i can go",
        "list of places i can go",
        "places i can go",
        "where can i go",
        "where can we go",
        "where could i go",
        "where should i go",
        "list all rooms",
        "list all departments",
        "list all offices",
        "all departments",
        "what offices",
    )
    ROOM_DIRECTORY_FOLLOWUP_HINTS = (
        "can you list all of them",
        "list all of them",
        "all of them",
        "specific offices",
    )
    ROOM_DIRECTORY_LIST_RE = re.compile(
        r"^(?:list|show|display|give\s+me|tell\s+me)\s+"
        r"(?:(?:all\s+)?(?:departments?\s+and\s+rooms?|rooms?\s+and\s+departments?)|"
        r"(?:all\s+)?(?:rooms?|departments?|offices?))\b.*$",
        re.IGNORECASE,
    )
    BREAK_ROOM_JOKE_HINTS = (
        "tell me a joke",
        "tell me another joke",
        "tell me another one",
        "tell us a joke",
        "say something funny",
        "give me a joke",
        "got any jokes",
        "do you know any jokes",
        "make me laugh",
    )
    BREAK_ROOM_AFFIRMATIVE_HINTS = (
        "yes",
        "yeah",
        "yep",
        "sure",
        "ok",
        "okay",
        "please",
        "another",
        "one more",
        "tell me another",
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
    PERSONA_ROLE_HINTS = (
        "what is your job here",
        "what is your role here",
        "what is your role in the app",
        "what is your role in this app",
        "what do you do here",
        "what are you here for",
        "what is your purpose here",
        "what is your purpose in the app",
        "what is your job in the app",
    )
    CONTROL_ROOM_GOVERNANCE_HINTS = (
        "what rules are you governed by",
        "what governs you",
        "what rules govern the app",
        "what are the veridex guidelines",
        "what are the system rules",
        "what hard rules govern the app",
        "what gates do you enforce",
        "what gates are active",
        "what gates are enabled",
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
    SESSION_OBJECTS_HINTS = (
        "what objects are saved in the session",
        "what are the objects saved in the session",
        "what objects are saved in this session",
        "what are the objects saved in this session",
        "what session objects are saved",
        "what are the session objects saved",
        "what saved objects are in this session",
        "what is saved in this session",
        "show session objects",
        "list session objects",
    )
    WORKSPACE_CREATE_RE = re.compile(
        r"^(?:please\s+)?(?:create|make|start)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?workspace(?:\s+(?:called|named))?\s*(?P<name>.*)$",
        re.IGNORECASE,
    )
    LIST_CREATE_RE = re.compile(
        r"^(?:please\s+)?(?:create|make|start)\s+(?:a\s+|an\s+|the\s+)?list(?:\s+(?:called|named))?\s*(?P<name>.*)$",
        re.IGNORECASE,
    )
    WORKSPACE_LIST_CREATE_AMBIGUOUS_RE = re.compile(
        r"^(?:please\s+)?(?:create|make|start)\s+(?:a\s+|an\s+|the\s+)?workspace\s*/\s*list\b(?:\s+(?:called|named))?\s*(?P<name>.*)$",
        re.IGNORECASE,
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
        governance_registry_service: Optional[GovernanceRegistryService] = None,
    ):
        self.kernel = kernel
        self.navigator_control = navigator_control
        self.utc_now = utc_now_fn
        self.tool_names = tool_names or []
        self.tool_catalog = tool_catalog or []
        self.app_version = app_version or "0.0.0"
        self.governance_registry_service = governance_registry_service or _default_governance_registry_service()
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

    def workspace_new_response(self, workspace_id: str, label: str, description: str = "") -> Dict[str, Any]:
        return {
            "structuredContent": {"workspace_id": workspace_id, "label": label, "description": str(description or "")},
            "content": [{"type": "text", "text": f"Created workspace {workspace_id} ({label})."}],
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
        normalized = re.sub(r"^(?:the|a|an)\s+", "", normalized).strip()
        if not normalized:
            return None

        rooms = rooms_payload()
        candidates: List[Dict[str, Any]] = []
        for room in rooms:
            room_id = str(room.get("id") or "").strip()
            room_title = str(room.get("title") or room_id).strip()
            if not room_id or not room_title:
                continue
            aliases = room_reference_aliases(room)
            if normalized in aliases:
                return room
            if normalized.startswith("the ") and normalized[4:] in aliases:
                return room
            candidates.append(
                {
                    "room": room,
                    "aliases": aliases,
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
            matches = difflib.get_close_matches(normalized, alias_keys, n=1, cutoff=0.86)
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

    def route_artifact_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        recent_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None

        retrieval_scope = self.artifact_retrieval_scope(workspace_id, request_text)

        delete_id_match = self.ARTIFACT_DELETE_ID_RE.match(request_text)
        if delete_id_match:
            return {
                "capability": "artifact.delete",
                "tool": "office.artifact_delete",
                "arguments": {
                    "artifact_id": delete_id_match.group("artifact_id"),
                    "retrieval_scope": retrieval_scope,
                },
                "reason": "Matched an artifact delete request with an explicit artifact id.",
            }

        delete_index_match = self.ARTIFACT_DELETE_NUMBER_RE.match(request_text)
        if delete_index_match:
            recent_list_context = self._recent_artifact_list_context(recent_turns or [])
            if not recent_list_context:
                return {
                    "route_kind": "clarify",
                    "capability": "clarification.artifact_delete",
                    "tool": "office.capability_info",
                    "arguments": {
                        "response_text": "Which listed workspace artifact should I delete?",
                    },
                    "reason": "Artifact delete request used a number but no recent artifact list was available.",
                }
            index = int(delete_index_match.group("index"))
            artifact_id = ""
            for item in recent_list_context:
                if int(item.get("index") or 0) == index:
                    artifact_id = str(item.get("artifact_id") or "").strip()
                    break
            if not artifact_id:
                return {
                    "route_kind": "clarify",
                    "capability": "clarification.artifact_delete",
                    "tool": "office.capability_info",
                    "arguments": {
                        "response_text": "I could not find that numbered artifact in the most recent workspace list.",
                    },
                    "reason": "Artifact delete request used a number that did not match the recent list.",
                }
            return {
                "capability": "artifact.delete",
                "tool": "office.artifact_delete",
                "arguments": {
                    "artifact_id": artifact_id,
                    "retrieval_scope": retrieval_scope,
                },
                "reason": "Matched a numbered artifact delete request against the recent workspace artifact list.",
            }

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

    def _recent_artifact_list_context(self, recent_turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for turn in reversed(recent_turns[-12:]):
            if str(turn.get("role") or "").strip().lower() != "assistant":
                continue
            text = str(turn.get("text") or "").strip()
            if not text or "artifact(s)" not in text.lower():
                continue
            items: List[Dict[str, Any]] = []
            for match in re.finditer(r"(?m)^\s*(\d+)\.\s+.*?\((art_[A-Za-z0-9]+)\)", text):
                items.append(
                    {
                        "index": int(match.group(1)),
                        "artifact_id": match.group(2),
                    }
                )
            if items:
                return items
        return []

    def route_object_scope_clarification(self, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip().lower())
        if not text:
            return None
        if not any(hint in text for hint in self.OBJECT_SCOPE_CLARIFICATION_HINTS):
            return None
        if any(scope in text for scope in ("workspace", "session", "room", "behavior", "behaviour", "memory")):
            return None
        return {
            "route_kind": "clarify",
            "capability": "clarification.object_scope",
            "tool": "office.capability_info",
            "arguments": {
                "response_text": "Do you mean workspace objects, session objects, or behavior memories?",
            },
            "reason": "The request for saved objects was ambiguous about scope.",
        }

    def route_user_request(self, workspace_id: str, request_text: str, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        recent_turns = self._load_recent_transcript_turns(workspace_id, session_id=session_id)

        session_objects_route = None
        if request_text and any(hint in re.sub(r"\s+", " ", request_text.lower().strip()) for hint in self.SESSION_OBJECTS_HINTS):
            session_objects_route = self.route_session_objects_request(workspace_id, request_text, session_id=session_id)
        if session_objects_route is not None:
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **session_objects_route,
            }

        memo_dispatch_route = self.route_memo_dispatch_request(workspace_id, request_text)
        if memo_dispatch_route is not None:
            if "route_kind" in memo_dispatch_route:
                return {
                    "workspace_id": workspace_id,
                    "request": request_text,
                    **memo_dispatch_route,
                }
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **memo_dispatch_route,
            }

        break_room_joke_route = self.route_break_room_joke_request(
            workspace_id,
            request_text,
            recent_turns=recent_turns,
            session_id=session_id,
        )
        if break_room_joke_route is not None:
            return break_room_joke_route

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

        workspace_route = self.route_workspace_request(workspace_id, request_text)
        if workspace_route is not None:
            if "route_kind" in workspace_route:
                return {
                    "workspace_id": workspace_id,
                    "request": request_text,
                    **workspace_route,
                }
            return {
                "route_kind": "tool",
                "workspace_id": workspace_id,
                "request": request_text,
                **workspace_route,
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

        persona_role_route = self.route_persona_role_request(workspace_id, request_text)
        if persona_role_route is not None:
            return persona_role_route

        governance_route = self.route_control_room_governance_request(workspace_id, request_text)
        if governance_route is not None:
            return governance_route

        object_scope_clarification = self.route_object_scope_clarification(request_text)
        if object_scope_clarification is not None:
            return {
                "workspace_id": workspace_id,
                "request": request_text,
                **object_scope_clarification,
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

        room_directory_route = self.route_room_directory_request(workspace_id, request_text, recent_turns=recent_turns)
        if room_directory_route is not None:
            return room_directory_route

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

        artifact_route = self.route_artifact_request(workspace_id, request_text, recent_turns=recent_turns)
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

        search_route = self.route_search_request(workspace_id, request_text, recent_turns=recent_turns, session_id=session_id)
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
        normalized_without_article = re.sub(r"^(?:the|a|an)\s+", "", normalized).strip()
        if not normalized:
            return None

        for room in rooms_payload():
            aliases = set(room_reference_aliases(room))
            if normalized in aliases or normalized_without_article in aliases:
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
        if "workspace" in text and "room" not in text and "behavior" not in text:
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

    def route_session_object_list_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        session_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip().lower())
        if not text:
            return None
        if not any(hint in text for hint in self.SESSION_OBJECTS_HINTS):
            return None
        session_ref = re.sub(r"\s+", " ", str(session_id or "").strip())
        if not session_ref:
            return None
        return {
            "capability": "session.objects.list",
            "tool": "office.session_objects_list",
            "arguments": {
                "workspace_id": workspace_id,
                "session_id": session_ref,
            },
            "reason": "Matched a request for session-scoped saved objects.",
        }

    def route_session_objects_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        session_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        return self.route_session_object_list_request(
            workspace_id,
            request_text,
            session_id=session_id,
        )

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

    def route_room_directory_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        recent_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", request_text.lower().strip().rstrip("?!."))
        if not text:
            return None
        if self.is_explicit_room_navigation(text):
            return None
        direct_match = any(hint in text for hint in self.ROOM_DIRECTORY_HINTS) or self.ROOM_DIRECTORY_LIST_RE.match(text) is not None
        followup_match = any(hint in text for hint in self.ROOM_DIRECTORY_FOLLOWUP_HINTS)
        if not direct_match and not (followup_match and self.recent_context_was_room_directory(recent_turns or [])):
            return None
        ctx = self.current_context(workspace_id)
        active_room = str(ctx.get("active_room") or "lobby")
        active_persona = str(ctx.get("active_persona") or "Receptionist")
        response_text = self.room_directory_response_text(active_room=active_room, active_persona=active_persona)
        return {
            "route_kind": "clarify",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": "room.directory",
            "tool": "office.capability_info",
            "arguments": {
                "response_text": response_text,
                "active_room": active_room,
                "active_persona": active_persona,
                "rooms": rooms_payload(),
            },
            "reason": "Answered a room directory request from the authoritative room registry.",
        }

    def recent_context_was_room_directory(self, recent_turns: List[Dict[str, Any]]) -> bool:
        for row in reversed(recent_turns[-6:]):
            text = re.sub(r"\s+", " ", str(row.get("text") or "").lower())
            if any(term in text for term in ("rooms", "departments", "offices", "places you can go", "places i can go")):
                return True
        return False

    def route_memo_dispatch_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip())
        if not text:
            return None
        match = self.MEMO_DISPATCH_RE.match(text)
        if not match:
            return None
        target_text = re.sub(r"^(?:the|a|an)\s+", "", str(match.group("target") or "").strip(), flags=re.IGNORECASE)
        body = str(match.group("body") or "").strip(" .")
        if not target_text:
            return {
                "route_kind": "clarify",
                "capability": "memo.dispatch.target_required",
                "tool": "office.capability_info",
                "arguments": {"response_text": "Who should I send the memo to?"},
                "reason": "Memo dispatch request did not include a destination.",
            }
        if not body:
            return {
                "route_kind": "clarify",
                "capability": "memo.dispatch.body_required",
                "tool": "office.capability_info",
                "arguments": {"response_text": f"What should the memo to {target_text} say?"},
                "reason": "Memo dispatch request did not include a body.",
            }

        target_room = self.resolve_memo_target_room(target_text)
        if target_room is None:
            return {
                "route_kind": "clarify",
                "capability": "memo.dispatch.target_unknown",
                "tool": "office.capability_info",
                "arguments": {"response_text": f"I can send a memo, but I could not identify the destination: {target_text}."},
                "reason": "Memo dispatch destination did not match a known room or persona.",
            }
        room_id = str(target_room.get("id") or "").strip()
        persona = str(target_room.get("default_persona") or "").strip()
        return {
            "capability": "memo.dispatch",
            "tool": "mailroom.dispatch",
            "arguments": {
                "workspace_id": workspace_id,
                "to_room": room_id,
                "body": body,
                "explicit_persona": persona or None,
            },
            "reason": f"Matched a memo dispatch request to {target_room.get('title') or room_id}.",
        }

    def resolve_memo_target_room(self, target_text: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_room_text(target_text)
        if normalized in {"navigator", "control", "control room"}:
            return validate_room("control_room")
        for room in rooms_payload():
            persona = normalize_room_text(str(room.get("default_persona") or ""))
            if normalized and normalized == persona:
                return room
        return self.resolve_room_reference(target_text)

    def route_break_room_joke_request(
        self,
        workspace_id: str,
        request_text: str,
        *,
        recent_turns: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ctx = self.current_context(workspace_id)
        active_room = str(ctx.get("active_room") or "").strip()
        active_persona = str(ctx.get("active_persona") or "Break Room Host").strip() or "Break Room Host"
        if active_room != "break_room":
            return None

        if self.is_explicit_room_navigation(request_text):
            return None

        turns = recent_turns or []
        text = re.sub(r"\s+", " ", request_text.lower().strip().rstrip("?!."))
        if self.recent_break_room_joke_asked_for_another(turns) and self.is_break_room_affirmative(text):
            return self.break_room_joke_generate_route(
                workspace_id=workspace_id,
                request_text=request_text,
                active_room=active_room,
                active_persona=active_persona,
                reason="Generate another Break Room joke after user accepted the offer.",
            )

        pending_joke = self.pending_break_room_joke(workspace_id=workspace_id, session_id=session_id)
        if pending_joke is not None:
            response_text = self.break_room_punchline_response_text(pending_joke, request_text)
            return {
                "route_kind": "clarify",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "break_room.joke.punchline",
                "tool": "office.capability_info",
                "arguments": {
                    "response_text": response_text,
                    "active_room": active_room,
                    "active_persona": active_persona,
                    "joke_phase": "punchline",
                    "clear_pending_break_room_joke": True,
                },
                "reason": "Answered the user's guess after a pending Break Room joke setup.",
            }

        if not text or not any(hint in text for hint in self.BREAK_ROOM_JOKE_HINTS):
            return None

        return self.break_room_joke_generate_route(
            workspace_id=workspace_id,
            request_text=request_text,
            active_room=active_room,
            active_persona=active_persona,
            reason="Generate a Break Room joke and show only the setup.",
        )

    def break_room_joke_generate_route(
        self,
        *,
        workspace_id: str,
        request_text: str,
        active_room: str,
        active_persona: str,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "route_kind": "break_room_joke",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": "break_room.joke.generate",
            "tool": "office.ai_generate",
            "arguments": {
                "active_room": active_room,
                "active_persona": active_persona,
                "joke_phase": "setup",
            },
            "reason": reason,
        }

    def recent_break_room_joke_asked_for_another(self, recent_turns: List[Dict[str, Any]]) -> bool:
        for row in reversed(recent_turns[-4:]):
            if str(row.get("role") or "").strip().lower() != "assistant":
                continue
            return "want another one?" in str(row.get("text") or "").lower()
        return False

    def is_break_room_affirmative(self, text: str) -> bool:
        if not text:
            return False
        return text in self.BREAK_ROOM_AFFIRMATIVE_HINTS or any(hint in text for hint in self.BREAK_ROOM_AFFIRMATIVE_HINTS)

    def pending_break_room_joke(self, *, workspace_id: str, session_id: Optional[str]) -> Optional[Dict[str, str]]:
        if not session_id:
            return None
        try:
            state = self.kernel.get_state(workspace_id)
        except Exception:
            return None
        pending_by_session = state.get("pending_break_room_jokes")
        if not isinstance(pending_by_session, dict):
            return None
        pending = pending_by_session.get(session_id)
        if not isinstance(pending, dict):
            return None
        setup = str(pending.get("setup") or "").strip()
        punchline = str(pending.get("punchline") or "").strip()
        if not setup or not punchline:
            return None
        return {"setup": setup, "punchline": punchline}

    def break_room_punchline_response_text(self, joke: Dict[str, str], request_text: str) -> str:
        if self.break_room_guess_matches_punchline(joke, request_text):
            return f"Exactly. {joke['punchline']}\n\nWant another one?"
        return f"{joke['punchline']}\n\nWant another one?"

    def break_room_guess_matches_punchline(self, joke: Dict[str, str], request_text: str) -> bool:
        guess = normalize_room_text(request_text)
        punchline = normalize_room_text(joke["punchline"])
        if not guess:
            return False
        if guess in punchline or punchline in guess:
            return True
        punchline_words = {word for word in punchline.split() if len(word) > 3}
        guess_words = {word for word in guess.split() if len(word) > 3}
        return bool(punchline_words) and len(punchline_words & guess_words) >= max(2, len(punchline_words) // 2)

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
                f"{self.room_directory_response_text(active_room=active_room, active_persona=active_persona)}\n\n"
                "Say something explicit like 'go to Sales Department' when you want me to move you. "
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

    def room_directory_response_text(self, *, active_room: str, active_persona: str) -> str:
        active_rooms = [room for room in rooms_payload() if room.get("is_active", True)]
        lines = [
            f"Here in {self.room_title_for_id(active_room)}, I am the {active_persona}.",
            "",
            "You can go to these Veridex rooms:",
        ]
        for index, room in enumerate(active_rooms, start=1):
            title = str(room.get("title") or room.get("id") or f"Room {index}").strip()
            persona = str(room.get("default_persona") or "Navigator").strip()
            room_id = str(room.get("id") or "").strip()
            suffix = f" ({room_id})" if room_id else ""
            lines.append(f"{index}. {title} - {persona}{suffix}")
        lines.extend(
            [
                "",
                "To move, say for example: go to Sales Department, go to My Office, or go to Records Archive.",
            ]
        )
        return "\n".join(lines)

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

    def _recent_session_location(self, workspace_id: str, *, session_id: Optional[str] = None, recent_turns: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        markers = (
            "i live in",
            "i am in",
            "i'm in",
            "i am located in",
            "i'm located in",
            "my location is",
            "i am from",
            "you are located in",
            "your location is",
            "i've saved that you're located in",
            "i have saved that you're located in",
            "i?ve saved that you?re located in",
            "i've saved that you are located in",
        )

        def scan(turns: List[Dict[str, Any]]) -> Optional[str]:
            for turn in reversed(turns[-48:]):
                text = re.sub(r"\s+", " ", str(turn.get("text") or "").strip())
                if not text:
                    continue
                lowered = text.casefold()
                if "verified information about your current location" in lowered:
                    continue
                for marker in markers:
                    marker_lower = marker.casefold()
                    index = lowered.find(marker_lower)
                    if index == -1:
                        continue
                    location = text[index + len(marker):].strip(" .,:;\"'")
                    location = re.split(r"[.?!]", location, maxsplit=1)[0].strip(" .,:;\"'")
                    location = re.split(r"(?:,|;|\band\b|\bbut\b|\bor\b|\bso\b|\bwhile\b)", location, maxsplit=1)[0].strip(" .,:;\"'")
                    if location:
                        return location
            return None

        turns = recent_turns or []
        location = scan(turns)
        if location:
            return location
        if not session_id:
            return None
        store = getattr(self.kernel, "store", None)
        loader = getattr(store, "load_transcript", None)
        if loader is None:
            return None
        try:
            transcript_rows = loader(workspace_id, limit=200, session_id=session_id)
        except Exception:
            return None
        return scan(list(transcript_rows or []))

    def route_search_request(self, workspace_id: str, request_text: str, *, recent_turns: Optional[List[Dict[str, Any]]] = None, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        session_location = self._recent_session_location(workspace_id, session_id=session_id, recent_turns=recent_turns or [])
        if not place_query.get("location") and session_location:
            place_query["location"] = session_location
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
        effective_location_signal = bool(place_query.get("location")) or place_signals["location_signal"]
        place_task = bool(
            place_signals["has_place_hint"]
            and (place_signals["discovery_signal"] or review_signal or mall_discovery_signal)
            and (effective_location_signal or place_signals["explicit_review_signal"])
        )

        if review_signal and place_signals["has_place_hint"] and place_query["needs_location"] and not effective_location_signal:
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

    def route_persona_role_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip().lower())
        if not text:
            return None
        if not any(hint in text for hint in self.PERSONA_ROLE_HINTS):
            return None
        ctx = self.current_context(workspace_id)
        active_room = str(ctx.get("active_room") or "lobby")
        active_persona = str(ctx.get("active_persona") or "Receptionist")
        profile = dict(ctx.get("active_persona_profile") or {})
        room = validate_room(active_room)
        purpose = str(profile.get("purpose") or "").strip()
        style = str(profile.get("style") or "").strip()
        response_text = (
            f"I am {active_persona} in {room.get('title')}. "
            f"My role here is {purpose or 'to operate within this room’s responsibilities.'}"
        )
        if style:
            response_text += f" My operating style is {style}."
        return {
            "route_kind": "clarify",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": "room.persona_role",
            "tool": "office.capability_info",
            "arguments": {
                "response_text": response_text,
                "speaker": active_persona,
                "active_room": active_room,
                "active_persona": active_persona,
            },
            "reason": "Answered a room/persona role question from the authoritative room and persona registry.",
        }

    def route_control_room_governance_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip().lower())
        if not text:
            return None
        if not any(hint in text for hint in self.CONTROL_ROOM_GOVERNANCE_HINTS):
            return None
        ctx = self.current_context(workspace_id)
        active_room = str(ctx.get("active_room") or "lobby")
        active_persona = str(ctx.get("active_persona") or "Receptionist")
        if active_room != "control_room" or active_persona != "Navigator":
            return None

        gate_state = {}
        try:
            gate_state = dict((self.kernel.get_state(workspace_id) or {}).get("gates") or {})
        except Exception:
            gate_state = {}
        active_workspace_gates = [name for name, enabled in gate_state.items() if bool(enabled)]
        registry_gates = self.governance_registry_service.active_gate_objects()
        registry_gate_names = [str(row.get("object_id") or "").strip() for row in registry_gates if str(row.get("object_id") or "").strip()]

        registry_path = str(self.governance_registry_service.registry_path).replace("\\", "/")
        governance_guide_path = str(self.governance_registry_service.governance_guide_path).replace("\\", "/")
        room_state_model_path = str(self.governance_registry_service.room_state_model_path).replace("\\", "/")
        mailroom_contract_path = str(self.governance_registry_service.mailroom_contract_path).replace("\\", "/")
        persona_registry_path = str(self.governance_registry_service.persona_registry_path).replace("\\", "/")
        room_registry_path = str(self.governance_registry_service.room_registry_path).replace("\\", "/")

        if "what gates" in text:
            workspace_gate_text = ", ".join(active_workspace_gates) if active_workspace_gates else "none"
            registry_gate_text = ", ".join(registry_gate_names[:8]) if registry_gate_names else "none"
            response_text = (
                f"The currently active workspace gates are {workspace_gate_text}. "
                f"The broader governance gate definitions are in {registry_path}, including {registry_gate_text}."
            )
        elif "guidelines" in text or "system rules" in text or "hard rules" in text or "rules govern the app" in text:
            response_text = (
                "Veridex follows a few core rules: one active room at a time, no implicit room switching, "
                "Navigator acts as the governance authority, tool-backed actions must be real, "
                f"mailroom dispatch does not change the active room, and active workspace gates currently include {', '.join(active_workspace_gates) or 'none'}. "
                f"The user-facing summary is in {governance_guide_path}. "
                f"The canonical enforcement sources remain {registry_path}, {room_state_model_path}, {mailroom_contract_path}, {persona_registry_path}, and {room_registry_path}."
            )
        else:
            response_text = (
                f"As Navigator, I am governed by the active governance registry in {registry_path}, "
                f"the room-state rules in {room_state_model_path}, "
                f"the mailroom contract in {mailroom_contract_path}, "
                f"and the active workspace gates ({', '.join(active_workspace_gates) or 'none'})."
            )
        return {
            "route_kind": "clarify",
            "workspace_id": workspace_id,
            "request": request_text,
            "capability": "control_room.governance",
            "tool": "office.capability_info",
            "arguments": {
                "response_text": response_text,
                "speaker": "Navigator",
                "active_room": active_room,
                "active_persona": active_persona,
                "workspace_gates": active_workspace_gates,
                "registry_gates": registry_gate_names,
            },
            "reason": "Answered a Control Room governance question from the governance registry and active workspace state.",
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

    def route_workspace_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = str(request_text or "").strip()
        if not text:
            return None

        ambiguous_match = self.WORKSPACE_LIST_CREATE_AMBIGUOUS_RE.match(text)
        if ambiguous_match:
            return {
                "route_kind": "clarify",
                "capability": "workspace_or_list.create.confirmation",
                "tool": "office.capability_info",
                "arguments": {
                    "response_text": "Do you want me to create a workspace or a saved list artifact?",
                },
                "reason": "Matched an ambiguous workspace/list create request.",
            }

        workspace_match = self.WORKSPACE_CREATE_RE.match(text)
        if workspace_match:
            label = str(workspace_match.group("name") or "").strip(" .,:;")
            if not label:
                return {
                    "route_kind": "clarify",
                    "capability": "workspace.create.name_required",
                    "tool": "office.workspace_new",
                    "arguments": {
                        "response_text": "What should I name the new workspace?",
                    },
                    "reason": "Need a workspace name before creating a new workspace.",
                }
            return {
                "capability": "workspace.create",
                "tool": "office.workspace_new",
                "arguments": {
                    "label": label,
                },
                "reason": "Matched a workspace create request.",
            }

        list_match = self.LIST_CREATE_RE.match(text)
        if list_match:
            title = str(list_match.group("name") or "").strip(" .,:;")
            if not title or title.lower().startswith("of "):
                return {
                    "route_kind": "clarify",
                    "capability": "artifact.create.name_required",
                    "tool": "office.artifact_create",
                    "arguments": {
                        "response_text": "What should I name the list artifact?",
                    },
                    "reason": "Need a list name before creating a saved list artifact.",
                }
            return {
                "route_kind": "artifact",
                "capability": "artifact.create",
                "tool": "office.artifact_create",
                "arguments": {
                    "artifact_type": "list",
                    "title": title,
                    "content": "",
                    "format": "text/plain",
                    "status": "active",
                    "created_by": "user",
                },
                "reason": "Matched a list create request and routed to artifact creation.",
            }

        return None

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
        spaced_name_match = self.OCR_FILE_NAME_WITH_SPACES_RE.search(request_text)
        if spaced_name_match:
            return {
                "capability": "document.ocr",
                "tool": "office.ocr_extract",
                "arguments": {
                    "file_name": spaced_name_match.group("name").strip(),
                },
                "reason": "Matched OCR request with a file name.",
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
        if self.is_non_navigation_go_to_context(text):
            return False
        return any(text.startswith(prefix) for prefix in self.ROOM_NAVIGATION_PREFIXES) or self.ROOM_NAVIGATION_RE.search(text) is not None

    def is_non_navigation_go_to_context(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.NON_NAVIGATION_GO_TO_PATTERNS)

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
        return f"Memo filed to: {to_persona} ({dest_room_title})\nSubject: {subject}\n"

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
        reply_text: str = "",
        reply_room: str = "",
        reply_persona: str = "",
        is_refusal: bool = False,
        closure_appended: bool = False,
    ) -> Dict[str, Any]:
        header = self.mailroom_header(to_persona, dest_room_title, subject)
        response_text = f"{header}\n{reply_text}".rstrip() if str(reply_text or "").strip() else header
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "memo_id": memo_id,
                "from_room": from_room,
                "to_room": to_room,
                "to_persona": to_persona,
                "subject": subject,
                "speaker": str(reply_persona or to_persona or "").strip(),
                "reply_text": str(reply_text or "").strip(),
                "reply_room": str(reply_room or "").strip(),
                "reply_persona": str(reply_persona or "").strip(),
                "is_refusal": bool(is_refusal),
                "closure_appended": bool(closure_appended),
                "response_text": response_text,
            },
            "content": [{"type": "text", "text": response_text}],
        }

    def memos_list_response(self, workspace_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "structuredContent": {"workspace_id": workspace_id, "count": len(rows), "memos": rows},
            "content": [{"type": "text", "text": f"Found {len(rows)} memo(s)."}],
        }

    def memo_get_text(self, obj: Dict[str, Any], body: str) -> str:
        header = (
            f"Memo {obj.get('memo_id')}\n"
            f"From: {obj.get('from_room')}\n"
            f"To: {obj.get('to_room')} ({obj.get('to_persona')})\n"
            f"Subject: {obj.get('subject')}\n\n"
        )
        reply_text = str(obj.get("reply_text") or "").strip()
        if reply_text:
            reply_persona = str(obj.get("reply_persona") or obj.get("to_persona") or "").strip()
            reply_room = str(obj.get("reply_room") or obj.get("to_room") or "").strip()
            return (
                f"{header}"
                f"{body}\n\n"
                f"Response from {reply_persona} ({reply_room}):\n"
                f"{reply_text}"
            )
        return f"{header}{body}"

    def memo_get_response(self, obj: Dict[str, Any], body: str) -> Dict[str, Any]:
        return {
            "structuredContent": obj,
            "content": [{"type": "text", "text": self.memo_get_text(obj, body)}],
        }
