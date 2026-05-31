from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from office_app.server.errors import error_workspace_not_initialized
from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.room_policy_registry import load_room_policies
from office_app.server.room_router import (
    default_persona_for_external_room,
    normalize_external_room,
    validate_room,
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


class WorkspaceStore:
    def __init__(self, workspaces_dir: Path, utc_now_fn):
        self.workspaces_dir = workspaces_dir
        self.utc_now = utc_now_fn
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.workspaces_dir / "index.json"

    def workspace_dir(self, workspace_id: str) -> Path:
        p = self.workspaces_dir / workspace_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def state_path(self, workspace_id: str) -> Path:
        return self.workspace_dir(workspace_id) / "state.json"

    def transcript_path(self, workspace_id: str, session_id: Optional[str] = None) -> Path:
        if session_id:
            return self.workspace_dir(workspace_id) / "sessions" / session_id / "transcript.ndjson"
        return self.workspace_dir(workspace_id) / "transcript.ndjson"

    def memos_dir(self, workspace_id: str) -> Path:
        p = self.workspace_dir(workspace_id) / "memos"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def load_state(self, workspace_id: str) -> Dict[str, Any]:
        return _read_json(self.state_path(workspace_id), {})

    def save_state(self, workspace_id: str, state: Dict[str, Any]) -> None:
        state["updated_at"] = self.utc_now()
        _write_json(self.state_path(workspace_id), state)

    def append_transcript(
        self,
        workspace_id: str,
        role: str,
        room_id: str,
        text: str,
        *,
        speaker: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        entry = {"ts": self.utc_now(), "role": role, "room": room_id, "text": text}
        if speaker:
            entry["speaker"] = speaker
        if session_id:
            entry["session_id"] = session_id
        tp = self.transcript_path(workspace_id, session_id=session_id)
        tp.parent.mkdir(parents=True, exist_ok=True)
        with tp.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def load_transcript(self, workspace_id: str, limit: int = 100, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        tp = self.transcript_path(workspace_id, session_id=session_id)
        if not tp.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with tp.open("r", encoding="utf-8") as f:
            raw = f.read()
        for line in raw.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
        if not rows and "\\n" in raw:
            for line in raw.replace("\\n", "\n").splitlines():
                text = line.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
        if limit > 0:
            rows = rows[-limit:]
        return rows

    def load_index(self) -> Dict[str, Any]:
        idx = _read_json(self.index_path, {"workspaces": []})
        if "workspaces" not in idx or not isinstance(idx["workspaces"], list):
            idx = {"workspaces": []}
        return idx

    def save_index(self, index: Dict[str, Any]) -> None:
        _write_json(self.index_path, index)

    def register_workspace(self, workspace_id: str, label: str, description: str = "") -> None:
        idx = self.load_index()
        rows = idx["workspaces"]
        for row in rows:
            if row.get("workspace_id") == workspace_id:
                row["label"] = label
                row["description"] = str(description or row.get("description") or "").strip()
                row["last_seen_utc"] = self.utc_now()
                self.save_index(idx)
                return
        rows.append(
            {
                "workspace_id": workspace_id,
                "label": label,
                "description": str(description or "").strip(),
                "created_utc": self.utc_now(),
                "last_seen_utc": self.utc_now(),
                "last_room": "lobby",
            }
        )
        self.save_index(idx)

    def update_workspace_metadata(
        self,
        workspace_id: str,
        *,
        label: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        idx = self.load_index()
        rows = idx.get("workspaces", [])
        normalized_id = str(workspace_id or "").strip()
        for row in rows:
            if str(row.get("workspace_id") or "").strip() != normalized_id:
                continue
            if label is not None:
                row["label"] = str(label or "").strip() or str(row.get("label") or normalized_id)
            if description is not None:
                row["description"] = str(description or "").strip()
            row["last_seen_utc"] = self.utc_now()
            self.save_index(idx)
            return row
        raise error_workspace_not_initialized(normalized_id)

    def touch_workspace(self, workspace_id: str, room_id: Optional[str] = None) -> None:
        idx = self.load_index()
        changed = False
        for row in idx["workspaces"]:
            if row.get("workspace_id") == workspace_id:
                row["last_seen_utc"] = self.utc_now()
                if room_id:
                    row["last_room"] = room_id
                changed = True
                break
        if changed:
            self.save_index(idx)

    def unregister_workspace(self, workspace_id: str) -> None:
        idx = self.load_index()
        rows = idx.get("workspaces", [])
        next_rows = [row for row in rows if str(row.get("workspace_id") or "").strip() != str(workspace_id or "").strip()]
        if len(next_rows) != len(rows):
            idx["workspaces"] = next_rows
            self.save_index(idx)


class WorkspaceKernel:
    def __init__(self, store: WorkspaceStore, utc_now_fn):
        self.store = store
        self.utc_now = utc_now_fn

    def build_workspace_state(self, workspace_id: str, active_room: str = "lobby") -> Dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "workspace_id": workspace_id,
            "active_room": active_room,
            "active_persona": default_persona_for_external_room(active_room),
            "active_mode": "STANDARD",
            "scope_lock": {"enabled": True, "max_rooms": 1},
            "engaged": {"CRE": False},
            "gates": {"SAVE_GATE": True, "PREFLIGHT": True, "VERIFICATION": True},
            "created_at": self.utc_now(),
            "vr_session": {},
        }

    def create_workspace(self, workspace_id: str, label: str, description: str = "") -> Dict[str, Any]:
        self.store.register_workspace(workspace_id, label, description=description)
        state = self.build_workspace_state(workspace_id)
        self.store.save_state(workspace_id, state)
        self.store.append_transcript(workspace_id, "system", "lobby", f"Workspace created: {label}")
        return state

    def bootstrap_workspace(self, workspace_id: str) -> Tuple[Dict[str, Any], bool]:
        state = self.store.load_state(workspace_id)
        created = False

        if not state:
            state = self.build_workspace_state(workspace_id)
            self.store.save_state(workspace_id, state)
            self.store.register_workspace(workspace_id, workspace_id)
            self.store.append_transcript(workspace_id, "system", "lobby", "Initialized workspace in Lobby.")
            created = True
        else:
            if not state.get("active_room"):
                state["active_room"] = "lobby"
            if not state.get("active_persona"):
                state["active_persona"] = default_persona_for_external_room(state["active_room"])
            self.store.save_state(workspace_id, state)
            self.store.touch_workspace(workspace_id, state.get("active_room", "lobby"))

        return self.store.load_state(workspace_id), created

    def list_workspaces(self) -> Dict[str, Any]:
        return self.store.load_index()

    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        state = self.store.load_state(workspace_id)
        if not state:
            raise error_workspace_not_initialized(workspace_id)
        return state

    def current_context(self, workspace_id: str) -> Dict[str, Any]:
        state = self.get_state(workspace_id)
        active_room = state.get("active_room", "lobby")
        active_persona = state.get("active_persona", default_persona_for_external_room(active_room))
        return {
            "state": state,
            "active_room": active_room,
            "active_persona": active_persona,
            "active_persona_profile": persona_profile_for_name(active_persona),
        }

    def enter_room(self, workspace_id: str, room_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        state = self.get_state(workspace_id)
        previous_room = state.get("active_room", "lobby")

        target_external = normalize_external_room(room_id)
        room = validate_room(target_external)

        self._clear_vr_session_state_if_needed(workspace_id, previous_room, target_external)

        state["active_room"] = target_external
        state["active_persona"] = str(room.get("default_persona") or "Navigator")
        self.store.save_state(workspace_id, state)
        self.store.touch_workspace(workspace_id, target_external)
        self.store.append_transcript(
            workspace_id,
            "system",
            target_external,
            f"Now in {room['title']}. Persona: {state['active_persona']}.",
            speaker="System",
            session_id=session_id,
        )

        return {
            "previous_room": previous_room,
            "active_room": target_external,
            "active_persona": state["active_persona"],
            "active_persona_profile": persona_profile_for_name(state["active_persona"]),
            "room_title": room["title"],
        }

    def _clear_vr_session_state_if_needed(self, workspace_id: str, previous_room: str, new_room: str) -> None:
        previous_room = normalize_external_room(previous_room)
        new_room = normalize_external_room(new_room)

        if previous_room != "vr_room" or new_room == "vr_room":
            return

        vr_policy = load_room_policies().get("vr_room", {})
        if not vr_policy.get("clear_state_on_exit", False):
            return

        ws_state = self.store.load_state(workspace_id)
        if ws_state.get("vr_session"):
            ws_state["vr_session"] = {}
            self.store.save_state(workspace_id, ws_state)
            self.store.append_transcript(workspace_id, "system", new_room, "VR session state cleared on exit.")
