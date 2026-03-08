from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.room_router import (
    default_persona_for_external_room,
    normalize_external_room,
    rooms_payload,
    validate_room,
)
from office_app.server.room_policy_registry import load_room_policies


def room_policy(room_id: str) -> Dict[str, Any]:
    return load_room_policies().get(normalize_external_room(room_id), {})


def is_break_room(room_id: str) -> bool:
    return normalize_external_room(room_id) == "break_room"


def is_vr_room(room_id: str) -> bool:
    return normalize_external_room(room_id) == "vr_room"


class RequestPipeline:
    def __init__(self, store, navigator_control, utc_now_fn):
        self.store = store
        self.navigator_control = navigator_control
        self.utc_now = utc_now_fn

    def load_workspace(self, workspace_id: str) -> Dict[str, Any]:
        state = self.store.load_state(workspace_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"Workspace not initialized: {workspace_id}")
        return state

    def current_context(self, workspace_id: str) -> Dict[str, Any]:
        state = self.load_workspace(workspace_id)
        active_room = state.get("active_room", "lobby")
        active_persona = state.get("active_persona", default_persona_for_external_room(active_room))
        return {
            "state": state,
            "active_room": active_room,
            "active_persona": active_persona,
            "active_persona_profile": persona_profile_for_name(active_persona),
        }

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

    def enter_room(self, workspace_id: str, room_id: str) -> Dict[str, Any]:
        state = self.load_workspace(workspace_id)
        previous_room = state.get("active_room", "lobby")

        target_external = normalize_external_room(room_id)
        room = validate_room(target_external)

        self._clear_vr_session_state_if_needed(workspace_id, previous_room, target_external)

        state["active_room"] = target_external
        state["active_persona"] = str(room.get("default_persona") or "Navigator")
        self.store.save_state(workspace_id, state)
        self.store.touch_workspace(workspace_id, target_external)
        self.store.append_transcript(workspace_id, "system", target_external, f"Entered {room['title']}")

        return {
            "previous_room": previous_room,
            "active_room": target_external,
            "active_persona": state["active_persona"],
            "active_persona_profile": persona_profile_for_name(state["active_persona"]),
            "room_title": room["title"],
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
        if is_break_room(to_room):
            raise HTTPException(
                status_code=403,
                detail="Break Room is non-operational. Memo dispatch is not allowed to break_room."
            )

        if is_break_room(from_room):
            raise HTTPException(
                status_code=403,
                detail="Break Room is non-operational. Memo dispatch is not allowed from break_room."
            )

        if is_vr_room(from_room):
            vr_policy = room_policy("vr_room")
            if not vr_policy.get("affects_other_rooms", False):
                raise HTTPException(
                    status_code=403,
                    detail="VR Room sandbox is isolated. Dispatch to other rooms is not allowed from vr_room."
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

    def _clear_vr_session_state_if_needed(self, workspace_id: str, previous_room: str, new_room: str) -> None:
        previous_room = normalize_external_room(previous_room)
        new_room = normalize_external_room(new_room)

        if previous_room != "vr_room" or new_room == "vr_room":
            return

        vr_policy = room_policy("vr_room")
        if not vr_policy.get("clear_state_on_exit", False):
            return

        ws_state = self.store.load_state(workspace_id)
        if ws_state.get("vr_session"):
            ws_state["vr_session"] = {}
            self.store.save_state(workspace_id, ws_state)
            self.store.append_transcript(workspace_id, "system", new_room, "VR session state cleared on exit.")
