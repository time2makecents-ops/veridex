from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

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
    ROOM_NAVIGATION_PREFIXES = (
        "go to ",
        "take me to ",
        "move to ",
        "switch to ",
        "enter ",
        "open ",
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
        "bar",
        "bars",
        "coffee",
        "cafe",
        "hotel",
        "hotels",
        "place",
        "places",
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

        navigation_room = self.extract_navigation_room(request_text)
        if navigation_room is not None:
            return {
                "route_kind": "nancy",
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
                "route_kind": "nancy",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "room.navigate",
                "tool": "office.nancy_route",
                "arguments": {"workspace_id": workspace_id, "request": request_text},
                "reason": route["reason"],
                "room_id": route["room_id"],
                "room_title": route["room_title"],
                "persona": route["persona"],
            }

        if route.get("matched") and self.room_navigation_requires_confirmation(request_text):
            return {
                "route_kind": "nancy",
                "workspace_id": workspace_id,
                "request": request_text,
                "capability": "room.navigate",
                "tool": "office.nancy_route",
                "arguments": {"workspace_id": workspace_id, "request": request_text},
                "reason": route["reason"],
                "room_id": route["room_id"],
                "room_title": route["room_title"],
                "persona": route["persona"],
                "requires_confirmation": True,
            }

        ctx = self.current_context(workspace_id)
        active_room = str(ctx["active_room"])
        active_persona = str(ctx["active_persona"])
        system_prompt = (
            f"You are Veridex. The active workspace is {workspace_id}. "
            f"The active room is {active_room}. The active persona is {active_persona}. "
            "Respond clearly, concisely, and in a way that fits the current office context."
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
                "user_prompt": request_text,
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
            "reason": "No strong department match found. Using the model route.",
        }

    def route_search_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None

        location = self.extract_location(request_text)
        time_window = self.extract_time_window(text)

        if any(hint in text for hint in self.SEARCH_REVIEW_HINTS) and any(hint in text for hint in self.SEARCH_PLACE_HINTS):
            return {
                "capability": "search.reviews",
                "tool": "office.search_reviews",
                "arguments": {
                    "query": request_text,
                    "location": location,
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

        if any(hint in text for hint in self.SEARCH_PLACE_HINTS) and ("find" in text or location or "near" in text):
            category = self.extract_place_category(text)
            return {
                "capability": "search.places",
                "tool": "office.search_places",
                "arguments": {
                    "query": request_text,
                    "location": location,
                    "category": category,
                    "limit": 5,
                },
                "reason": "Matched place lookup intent.",
            }

        return None

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

    def route_ocr_request(self, workspace_id: str, request_text: str) -> Optional[Dict[str, Any]]:
        text = request_text.lower().strip()
        if not text:
            return None
        if "ocr" not in text and "extract text" not in text and "extracted text" not in text and "read file" not in text and "show me" not in text:
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
            return None
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
        for candidate in ("restaurant", "bar", "bars", "coffee", "cafe", "hotel", "hotels"):
            if candidate in text:
                return candidate
        return None

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
