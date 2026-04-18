from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.room_policy_registry import load_room_policies
from office_app.server.room_router import rooms_payload, validate_room


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

    def __init__(
        self,
        kernel,
        navigator_control,
        utc_now_fn,
        tool_names: Optional[List[str]] = None,
        app_version: Optional[str] = None,
    ):
        self.kernel = kernel
        self.navigator_control = navigator_control
        self.utc_now = utc_now_fn
        self.tool_names = tool_names or []
        self.app_version = app_version or "0.0.0"

    def health_response(self) -> Dict[str, Any]:
        return {"ok": True, "ts": self.utc_now()}

    def tools_response(self) -> Dict[str, Any]:
        return {"tools": self.tool_names, "version": self.app_version}

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

    def recommend_room(self, request_text: str) -> Dict[str, str]:
        text = request_text.lower()

        rules = [
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
            if any(k in text for k in keywords):
                room = validate_room(room_id)
                return {
                    "room_id": room["id"],
                    "room_title": room["title"],
                    "persona": str(room.get("default_persona") or "Navigator"),
                    "reason": f"Matched request keywords to {room['title']}.",
                }

        room = validate_room("my_office")
        return {
            "room_id": room["id"],
            "room_title": room["title"],
            "persona": str(room.get("default_persona") or "Nancy"),
            "reason": "No strong department match found. Keeping request in My Office.",
        }

    def nancy_route(self, workspace_id: str, request_text: str) -> Dict[str, Any]:
        ctx = self.current_context(workspace_id)
        route = self.recommend_room(request_text)
        return {
            "room_id": route["room_id"],
            "room_title": route["room_title"],
            "persona": route["persona"],
            "reason": route["reason"],
            "auto_routed": False,
            "requires_confirmation": True,
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
            "content": [{"type": "text", "text": f"Nancy recommends {route['room_title']} ({route['persona']}). Confirm if you want to move there."}],
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

        route = self.nancy_route(workspace_id, request_text)
        return {
            "route_kind": "nancy",
            "workspace_id": workspace_id,
            "request": request_text,
            "tool": "office.nancy_route",
            "arguments": {"workspace_id": workspace_id, "request": request_text},
            "reason": route["reason"],
            "room_id": route["room_id"],
            "room_title": route["room_title"],
            "persona": route["persona"],
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
