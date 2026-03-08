from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException


SERVER_DIR = Path(__file__).resolve().parent
PKG_DIR = SERVER_DIR.parent
DATA_DIR = PKG_DIR / "data"
ROOMS_PATH = DATA_DIR / "rooms.json"


DEFAULT_ROOMS: List[Dict[str, Any]] = [
    {"id": "lobby", "title": "Lobby", "default_persona": "Receptionist", "is_active": True},
    {"id": "conference_room", "title": "Conference Room", "default_persona": "Facilitator", "is_active": True},
    {"id": "control_room", "title": "Control Room", "default_persona": "Navigator", "is_active": True},
    {"id": "infrastructure_room", "title": "Infrastructure Room", "default_persona": "Infrastructure Manager", "is_active": True},
    {"id": "sales_department", "title": "Sales Department", "default_persona": "Sales Director", "is_active": True},
    {"id": "marketing_room", "title": "Marketing & Advertising", "default_persona": "Marketing Director", "is_active": True},
    {"id": "hr_department", "title": "HR Department", "default_persona": "HR Manager", "is_active": True},
    {"id": "it_department", "title": "IT Department", "default_persona": "IT Administrator", "is_active": True},
    {"id": "art_department", "title": "Art Department", "default_persona": "Creative Director", "is_active": True},
    {"id": "law_office", "title": "Law Office", "default_persona": "Legal Counsel", "is_active": True},
    {"id": "finance_department", "title": "Finance Department", "default_persona": "Finance Director", "is_active": True},
    {"id": "my_office", "title": "My Office", "default_persona": "Nancy", "is_active": True},
    {
        "id": "vr_room",
        "title": "VR Room",
        "default_persona": "Simulation Guide",
        "is_active": True,
        "is_sandbox": True,
        "persistent_storage": False,
        "allow_persona_morph": True,
        "clear_on_exit": True,
    },
    {"id": "records_archive", "title": "Records Archive", "default_persona": "Archivist", "is_active": True},
    {"id": "rnd_room", "title": "Research & Development (R&D)", "default_persona": "R&D Director", "is_active": True},
    {"id": "security_room", "title": "Security Room", "default_persona": "Security Chief", "is_active": True},
    {"id": "break_room", "title": "Break Room", "default_persona": "Break Room Host", "is_active": True},
]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_rooms() -> List[Dict[str, Any]]:
    rooms = _read_json(ROOMS_PATH, DEFAULT_ROOMS)
    return rooms if isinstance(rooms, list) and rooms else DEFAULT_ROOMS


def rooms() -> List[Dict[str, Any]]:
    return load_rooms()


def normalize_external_room(room_id: str) -> str:
    return room_id.strip().lower().replace(" ", "_")


def room_index() -> Dict[str, Dict[str, Any]]:
    return {normalize_external_room(r["id"]): r for r in rooms()}


def validate_room(room_id_external: str) -> Dict[str, Any]:
    idx = room_index()
    rid = normalize_external_room(room_id_external)
    room = idx.get(rid)
    if not room or not room.get("is_active", False):
        valid = [r["id"] for r in rooms() if r.get("is_active", False)]
        raise HTTPException(status_code=400, detail=f"Room not recognized. Valid rooms: {valid}")
    return room


def default_persona_for_external_room(room_id_external: str) -> str:
    room = validate_room(room_id_external)
    return str(room.get("default_persona") or "Navigator")


def rooms_payload() -> List[Dict[str, Any]]:
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "default_persona": r.get("default_persona"),
            "is_active": bool(r.get("is_active", True)),
        }
        for r in rooms()
    ]