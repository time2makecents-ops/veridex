from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

SERVER_DIR = Path(__file__).resolve().parent
PKG_DIR = SERVER_DIR.parent
DATA_DIR = PKG_DIR / "data"

ROOM_POLICIES_PATH = DATA_DIR / "room_policies.json"


DEFAULT_POLICIES: Dict[str, Any] = {
    "global": {
        "navigator_always_present": True,
        "navigator_visibility_default": "invisible",
    },
    "vr_room": {
        "sandbox_mode": True,
        "persistent_storage": False,
        "allow_persona_morph": True,
        "clear_state_on_exit": True,
        "allow_rule_simulation": True,
        "allow_session_artifacts": True,
        "affects_other_rooms": False,
    },
    "break_room": {
        "operational_decisions": False,
        "policy_changes": False,
    },
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_room_policies() -> Dict[str, Any]:
    policies = _read_json(ROOM_POLICIES_PATH, DEFAULT_POLICIES)
    if isinstance(policies, dict):
        return policies
    return DEFAULT_POLICIES