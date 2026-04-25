from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from office_app.server.persona_registry import load_personas
from office_app.server.room_policy_registry import load_room_policies
from office_app.server.room_router import rooms_payload


RECEPTIONIST_CONTEXT_COLUMNS = (
    "workspace_id",
    "room_directory_json",
    "persona_directory_json",
    "receptionist_script_json",
    "policy_summary_json",
    "known_user_profile_json",
    "session_summary_text",
    "recent_turns_json",
    "current_prompt_state_json",
    "updated_at",
)


class ReceptionistContextStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS receptionist_contexts (
                    workspace_id TEXT PRIMARY KEY,
                    room_directory_json TEXT NOT NULL,
                    persona_directory_json TEXT NOT NULL,
                    receptionist_script_json TEXT NOT NULL,
                    policy_summary_json TEXT NOT NULL,
                    known_user_profile_json TEXT NOT NULL,
                    session_summary_text TEXT NOT NULL DEFAULT '',
                    recent_turns_json TEXT NOT NULL,
                    current_prompt_state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _default_json(value: Any, default: Any) -> str:
        if value is None:
            return json.dumps(default)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return json.dumps(default)
            try:
                json.loads(stripped)
                return stripped
            except json.JSONDecodeError:
                return json.dumps(value)
        return json.dumps(value)

    @staticmethod
    def _load_json(value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except json.JSONDecodeError:
            return default

    def fetch_context(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM receptionist_contexts
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_context(row)

    def upsert_context(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload["room_directory_json"] = self._default_json(payload.get("room_directory_json"), [])
        payload["persona_directory_json"] = self._default_json(payload.get("persona_directory_json"), [])
        payload["receptionist_script_json"] = self._default_json(payload.get("receptionist_script_json"), {})
        payload["policy_summary_json"] = self._default_json(payload.get("policy_summary_json"), {})
        payload["known_user_profile_json"] = self._default_json(payload.get("known_user_profile_json"), {})
        payload["recent_turns_json"] = self._default_json(payload.get("recent_turns_json"), [])
        payload["current_prompt_state_json"] = self._default_json(payload.get("current_prompt_state_json"), {})

        columns = ", ".join(f'"{column}"' for column in RECEPTIONIST_CONTEXT_COLUMNS)
        placeholders = ", ".join("?" for _ in RECEPTIONIST_CONTEXT_COLUMNS)
        values = [payload[column] for column in RECEPTIONIST_CONTEXT_COLUMNS]

        with self._connection() as conn:
            conn.execute(
                f"""
                INSERT INTO receptionist_contexts ({columns})
                VALUES ({placeholders})
                ON CONFLICT(workspace_id) DO UPDATE SET
                    room_directory_json = excluded.room_directory_json,
                    persona_directory_json = excluded.persona_directory_json,
                    receptionist_script_json = excluded.receptionist_script_json,
                    policy_summary_json = excluded.policy_summary_json,
                    known_user_profile_json = excluded.known_user_profile_json,
                    session_summary_text = excluded.session_summary_text,
                    recent_turns_json = excluded.recent_turns_json,
                    current_prompt_state_json = excluded.current_prompt_state_json,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            conn.commit()

        fetched = self.fetch_context(str(payload["workspace_id"]))
        if fetched is None:
            raise LookupError(f"Receptionist context not found after upsert: {payload['workspace_id']}")
        return fetched

    def _row_to_context(self, row: sqlite3.Row) -> Dict[str, Any]:
        workspace_id = row["workspace_id"]
        try:
            state = self.kernel.get_state(workspace_id)
        except Exception:
            state = {}
        return {
            "workspace_id": workspace_id,
            "room_directory": self._load_json(row["room_directory_json"], []),
            "persona_directory": self._load_json(row["persona_directory_json"], []),
            "receptionist_script": self._load_json(row["receptionist_script_json"], {}),
            "policy_summary": self._load_json(row["policy_summary_json"], {}),
            "known_user_profile": self._load_json(row["known_user_profile_json"], {}),
            "session_summary_text": "",
            "recent_turns": [],
            "current_prompt_state": {
                "mode": "lobby",
                "awaiting": "text",
                "active_room": state.get("active_room", "lobby"),
                "active_persona": state.get("active_persona", "Receptionist"),
            },
            "updated_at": row["updated_at"],
        }


class ReceptionistContextService:
    def __init__(self, *, kernel, runtime_dir: Path, utc_now_fn):
        self.kernel = kernel
        self.runtime_dir = Path(runtime_dir)
        self.utc_now = utc_now_fn
        self.db_path = self.runtime_dir / "veridex.db"
        self.store = ReceptionistContextStore(self.db_path)

    def _default_room_directory(self) -> List[Dict[str, Any]]:
        return rooms_payload()

    def _default_persona_directory(self) -> List[Dict[str, Any]]:
        return load_personas()

    def _default_receptionist_script(self) -> Dict[str, Any]:
        return {
            "greeting": "Welcome to Veridex Headquarters.",
            "onboarding": [
                "Ask for full name and display name.",
                "Request a 4-digit PIN after the welcome speech.",
                "Confirm the user understands the PIN is private.",
            ],
            "pin_setup": [
                "Use the keypad when the backend requests pin mode.",
                "Require the user to enter the PIN twice for confirmation.",
            ],
            "files": [
                "Explain that Veridex supports workspace file uploads and downloads.",
                "Never redirect a simple upload question to IT unless the user asks for troubleshooting.",
                "If the user asks how to upload, describe the upload flow in plain language and offer to take the file.",
            ],
            "return_user": [
                "Accept a 4-digit PIN for returning users.",
                "Restore the last active workspace from the backend session.",
            ],
        }

    def _default_policy_summary(self, workspace_id: str) -> Dict[str, Any]:
        policies = load_room_policies()
        state = self.kernel.get_state(workspace_id)
        return {
            "workspace_id": workspace_id,
            "active_room": state.get("active_room", "lobby"),
            "active_persona": state.get("active_persona", "Receptionist"),
            "rooms": policies,
        }

    def _default_prompt_state(self, workspace_id: str) -> Dict[str, Any]:
        state = self.kernel.get_state(workspace_id)
        return {
            "mode": "lobby",
            "awaiting": "text",
            "active_room": state.get("active_room", "lobby"),
            "active_persona": state.get("active_persona", "Receptionist"),
        }

    def _ensure_context(self, workspace_id: str) -> Dict[str, Any]:
        try:
            self.kernel.bootstrap_workspace(workspace_id)
        except Exception:
            pass
        existing = self.store.fetch_context(workspace_id)
        if existing is not None:
            return existing
        context = self.store.upsert_context(
            {
                "workspace_id": workspace_id,
                "room_directory_json": self._default_room_directory(),
                "persona_directory_json": self._default_persona_directory(),
                "receptionist_script_json": self._default_receptionist_script(),
                "policy_summary_json": self._default_policy_summary(workspace_id),
                "known_user_profile_json": {},
                "session_summary_text": "",
                "recent_turns_json": [],
                "current_prompt_state_json": self._default_prompt_state(workspace_id),
                "updated_at": self.utc_now(),
            }
        )
        return context

    def get_context(self, workspace_id: str) -> Dict[str, Any]:
        return self._ensure_context(workspace_id)

    def update_context(self, workspace_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self._ensure_context(workspace_id)
        merged = dict(current)
        for key, value in updates.items():
            if key in {"room_directory", "persona_directory", "receptionist_script", "policy_summary", "known_user_profile"}:
                merged[key] = value
        payload = {
            "workspace_id": workspace_id,
            "room_directory_json": merged.get("room_directory", []),
            "persona_directory_json": merged.get("persona_directory", []),
            "receptionist_script_json": merged.get("receptionist_script", {}),
            "policy_summary_json": merged.get("policy_summary", {}),
            "known_user_profile_json": merged.get("known_user_profile", {}),
            "session_summary_text": current.get("session_summary_text", ""),
            "recent_turns_json": current.get("recent_turns", []),
            "current_prompt_state_json": current.get("current_prompt_state", self._default_prompt_state(workspace_id)),
            "updated_at": self.utc_now(),
        }
        return self.store.upsert_context(payload)

    @staticmethod
    def _trim_turns(turns: List[Dict[str, Any]], max_turns: int = 4) -> List[Dict[str, Any]]:
        if len(turns) <= max_turns:
            return turns
        return turns[-max_turns:]

    @staticmethod
    def _truncate_text(value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 1)].rstrip() + "…"

    def record_turn(
        self,
        *,
        workspace_id: str,
        role: str,
        text: str,
        room_id: Optional[str] = None,
        persona_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_context(workspace_id)
        return self.build_model_context(
            workspace_id=workspace_id,
            session_id=session_id,
        )

    def build_model_context(
        self,
        *,
        workspace_id: str,
        user_profile: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_context(workspace_id)
        state = self.kernel.get_state(workspace_id)
        transcript_rows: List[Dict[str, Any]] = []
        if session_id:
            transcript_rows = self.kernel.store.load_transcript(workspace_id, limit=8, session_id=session_id)
        recent_turns = []
        for turn in transcript_rows[-4:]:
            role = str(turn.get("role") or "assistant").strip()
            speaker = str(turn.get("persona_name") or role.title()).strip()
            text = self._truncate_text(turn.get("text") or "", 300)
            if not text:
                continue
            recent_turns.append(f"{speaker} [{role}]: {text[:300]}")
        session_summary_text = self._truncate_text(" | ".join(recent_turns[-4:]), 600)
        merged = {
            "workspace_id": workspace_id,
            "active_room": state.get("active_room", "lobby"),
            "active_persona": state.get("active_persona", "Receptionist"),
            "session_summary_text": session_summary_text,
            "recent_turns_text": recent_turns,
            "session_id": session_id,
        }
        return merged
