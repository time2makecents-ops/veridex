from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from office_app.server.room_router import load_rooms, normalize_external_room
from office_app.server.tool_definitions import VERIDEX_TOOL_DEFINITIONS


SERVER_DIR = Path(__file__).resolve().parent
PKG_DIR = SERVER_DIR.parent
DATA_DIR = PKG_DIR / "data"
ROOM_CAPABILITIES_PATH = DATA_DIR / "room_capabilities.json"


@dataclass(frozen=True)
class RoomCapabilityProfile:
    room_id: str
    primary_capabilities: List[str]
    allowed_tools: List[str]
    blocked_tools: List[str]
    preferred_collaborators: List[str]
    storage_scope: str
    approval_required_for: List[str]
    plugin_affinities: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "primary_capabilities": self.primary_capabilities,
            "allowed_tools": self.allowed_tools,
            "blocked_tools": self.blocked_tools,
            "preferred_collaborators": self.preferred_collaborators,
            "storage_scope": self.storage_scope,
            "approval_required_for": self.approval_required_for,
            "plugin_affinities": self.plugin_affinities,
        }


class RoomCapabilityRegistry:
    def __init__(
        self,
        *,
        path: Path = ROOM_CAPABILITIES_PATH,
        rooms: Optional[Iterable[Dict[str, Any]]] = None,
        tool_definitions: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.path = Path(path)
        self.rooms = list(rooms) if rooms is not None else load_rooms()
        self.tool_definitions = tool_definitions or VERIDEX_TOOL_DEFINITIONS
        self.raw = self._load()
        self.tool_groups = self._tool_groups()
        self.profiles = self._profiles()
        self.validate()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"tool_groups": {}, "profiles": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"tool_groups": {}, "profiles": {}}

    def _tool_groups(self) -> Dict[str, List[str]]:
        groups = self.raw.get("tool_groups")
        if not isinstance(groups, dict):
            return {}
        result: Dict[str, List[str]] = {}
        for name, tools in groups.items():
            if isinstance(tools, list):
                result[str(name)] = [str(tool) for tool in tools]
        return result

    def _profiles(self) -> Dict[str, Dict[str, Any]]:
        profiles = self.raw.get("profiles")
        if not isinstance(profiles, dict):
            return {}
        return {normalize_external_room(str(room_id)): dict(profile) for room_id, profile in profiles.items() if isinstance(profile, dict)}

    def validate(self) -> None:
        room_ids = {normalize_external_room(str(room.get("id") or "")) for room in self.rooms if room.get("is_active", True)}
        missing_profiles = sorted(room_id for room_id in room_ids if room_id and room_id not in self.profiles)
        if missing_profiles:
            raise ValueError(f"Missing room capability profiles: {', '.join(missing_profiles)}")
        unknown_profiles = sorted(room_id for room_id in self.profiles if room_id not in room_ids)
        if unknown_profiles:
            raise ValueError(f"Unknown room capability profiles: {', '.join(unknown_profiles)}")

        known_tools = set(self.tool_definitions)
        for group_name, tools in self.tool_groups.items():
            unknown = sorted(tool for tool in tools if tool not in known_tools)
            if unknown:
                raise ValueError(f"Room capability group {group_name} references unknown tools: {', '.join(unknown)}")

        for room_id, profile in self.profiles.items():
            unknown_groups = sorted(str(group) for group in profile.get("tool_groups", []) if str(group) not in self.tool_groups)
            if unknown_groups:
                raise ValueError(f"Room {room_id} references unknown tool groups: {', '.join(unknown_groups)}")
            tools = set(str(tool) for tool in profile.get("allowed_tools", []))
            tools.update(str(tool) for tool in profile.get("blocked_tools", []))
            for group in profile.get("tool_groups", []):
                tools.update(self.tool_groups.get(str(group), []))
            unknown_tools = sorted(tool for tool in tools if tool not in known_tools)
            if unknown_tools:
                raise ValueError(f"Room {room_id} references unknown tools: {', '.join(unknown_tools)}")
            unknown_collaborators = sorted(
                normalize_external_room(str(room))
                for room in profile.get("preferred_collaborators", [])
                if normalize_external_room(str(room)) not in room_ids
            )
            if unknown_collaborators:
                raise ValueError(f"Room {room_id} references unknown collaborators: {', '.join(unknown_collaborators)}")

    def allowed_tools_for_room(self, room_id: str) -> Set[str]:
        room_key = normalize_external_room(room_id)
        profile = self.profiles.get(room_key)
        if profile is None:
            return set()
        tools: Set[str] = set()
        for group in profile.get("tool_groups", []):
            tools.update(self.tool_groups.get(str(group), []))
        tools.update(str(tool) for tool in profile.get("allowed_tools", []))
        tools.difference_update(str(tool) for tool in profile.get("blocked_tools", []))
        return tools

    def blocked_tools_for_room(self, room_id: str) -> Set[str]:
        profile = self.profiles.get(normalize_external_room(room_id))
        if profile is None:
            return set()
        return {str(tool) for tool in profile.get("blocked_tools", [])}

    def is_tool_allowed(self, room_id: str, tool_name: str) -> bool:
        room_key = normalize_external_room(room_id)
        if room_key not in self.profiles:
            return True
        if tool_name in self.blocked_tools_for_room(room_key):
            return False
        return tool_name in self.allowed_tools_for_room(room_key)

    def profile_for_room(self, room_id: str) -> RoomCapabilityProfile:
        room_key = normalize_external_room(room_id)
        profile = self.profiles.get(room_key)
        if profile is None:
            raise KeyError(room_id)
        return RoomCapabilityProfile(
            room_id=room_key,
            primary_capabilities=[str(item) for item in profile.get("primary_capabilities", [])],
            allowed_tools=sorted(self.allowed_tools_for_room(room_key)),
            blocked_tools=sorted(self.blocked_tools_for_room(room_key)),
            preferred_collaborators=[str(item) for item in profile.get("preferred_collaborators", [])],
            storage_scope=str(profile.get("storage_scope") or "workspace"),
            approval_required_for=[str(item) for item in profile.get("approval_required_for", [])],
            plugin_affinities=[str(item) for item in profile.get("plugin_affinities", [])],
        )

    def profiles_payload(self) -> List[Dict[str, Any]]:
        return [self.profile_for_room(room_id).as_dict() for room_id in sorted(self.profiles)]
