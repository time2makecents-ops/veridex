from __future__ import annotations

import json
import re
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
    ROOM_BEHAVIOR_MEMORY_REFS_KEY = "room_behavior_memory_refs"
    MAX_ROOM_BEHAVIOR_NOTES = 20
    MODEL_CONTEXT_TURN_LIMIT = 12
    MODEL_CONTEXT_TURN_CHARS = 700
    MODEL_CONTEXT_HISTORY_CHARS = 5000
    MODEL_CONTEXT_SUMMARY_CHARS = 1400
    MODEL_CONTEXT_SESSION_FACT_LIMIT = 6
    MODEL_CONTEXT_SESSION_FACT_CHARS = 240

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
            if value is not None and key in {"room_directory", "persona_directory", "receptionist_script", "policy_summary", "known_user_profile"}:
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

    def remember_room_behavior_ref(
        self,
        *,
        workspace_id: str,
        room_id: str,
        artifact_id: str,
        artifact_workspace_id: Optional[str] = None,
        preview: str = "",
    ) -> Dict[str, Any]:
        room = str(room_id or "").strip()
        artifact = str(artifact_id or "").strip()
        if not room:
            raise ValueError("room_id is required")
        if not artifact:
            raise ValueError("artifact_id is required")

        current = self._ensure_context(workspace_id)
        profile = current.get("known_user_profile")
        profile = dict(profile) if isinstance(profile, dict) else {}
        refs_by_room = profile.get(self.ROOM_BEHAVIOR_MEMORY_REFS_KEY)
        refs_by_room = dict(refs_by_room) if isinstance(refs_by_room, dict) else {}
        refs = refs_by_room.get(room)
        refs = list(refs) if isinstance(refs, list) else []

        entry = {
            "artifact_id": artifact,
            "workspace_id": str(artifact_workspace_id or workspace_id).strip() or workspace_id,
            "linked_at": self.utc_now(),
        }
        preview_text = self._truncate_text(preview, 240)
        if preview_text:
            entry["preview"] = preview_text

        refs = [
            ref
            for ref in refs
            if not (
                isinstance(ref, dict)
                and str(ref.get("artifact_id") or "").strip() == artifact
                and str(ref.get("workspace_id") or workspace_id).strip() == entry["workspace_id"]
            )
        ]
        refs.append(entry)
        refs = refs[-self.MAX_ROOM_BEHAVIOR_NOTES :]
        refs_by_room[room] = refs
        profile[self.ROOM_BEHAVIOR_MEMORY_REFS_KEY] = refs_by_room
        self.update_context(workspace_id, {"known_user_profile": profile})
        return {
            "workspace_id": workspace_id,
            "room_id": room,
            "room_behavior_memory_refs": refs,
        }

    def room_behavior_memory_refs(self, *, workspace_id: str, room_id: str) -> List[Dict[str, Any]]:
        current = self._ensure_context(workspace_id)
        profile = current.get("known_user_profile")
        profile = profile if isinstance(profile, dict) else {}
        refs_by_room = profile.get(self.ROOM_BEHAVIOR_MEMORY_REFS_KEY)
        refs_by_room = refs_by_room if isinstance(refs_by_room, dict) else {}
        refs = refs_by_room.get(str(room_id or "").strip())
        return [dict(ref) for ref in refs if isinstance(ref, dict)] if isinstance(refs, list) else []

    def forget_room_behavior_refs(
        self,
        *,
        workspace_id: str,
        room_id: str,
        artifact_id: Optional[str] = None,
        memory_index: Optional[int] = None,
        match_text: str = "",
    ) -> Dict[str, Any]:
        current = self._ensure_context(workspace_id)
        profile = current.get("known_user_profile")
        profile = dict(profile) if isinstance(profile, dict) else {}
        refs_by_room = profile.get(self.ROOM_BEHAVIOR_MEMORY_REFS_KEY)
        refs_by_room = dict(refs_by_room) if isinstance(refs_by_room, dict) else {}
        room = str(room_id or "").strip()
        needle = str(match_text or "").strip().casefold()
        artifact = str(artifact_id or "").strip()
        index = memory_index if isinstance(memory_index, int) and memory_index > 0 else None

        target_rooms = list(refs_by_room.keys()) if room in {"*", "all"} else [room]
        kept_for_room: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []
        for target_room in target_rooms:
            refs = refs_by_room.get(target_room)
            refs = list(refs) if isinstance(refs, list) else []
            kept: List[Dict[str, Any]] = []
            for ref_index, ref in enumerate(refs, start=1):
                if not isinstance(ref, dict):
                    continue
                ref_artifact = str(ref.get("artifact_id") or "").strip()
                preview = str(ref.get("preview") or "")
                should_remove = bool(
                    (index is not None and target_room == room and ref_index == index)
                    or (artifact and ref_artifact == artifact)
                    or (needle and self._memory_text_matches(needle, preview))
                    or (not artifact and index is None and not needle)
                )
                if should_remove:
                    removed_ref = dict(ref)
                    removed_ref["room_id"] = target_room
                    removed.append(removed_ref)
                else:
                    kept.append(dict(ref))
            refs_by_room[target_room] = kept
            if target_room == room:
                kept_for_room = kept

        profile[self.ROOM_BEHAVIOR_MEMORY_REFS_KEY] = refs_by_room
        self.update_context(workspace_id, {"known_user_profile": profile})
        return {
            "workspace_id": workspace_id,
            "room_id": room,
            "removed_count": len(removed),
            "removed_refs": removed,
            "room_behavior_memory_refs": kept_for_room if room not in {"*", "all"} else [],
        }

    @staticmethod
    def _memory_text_matches(needle: str, haystack: str) -> bool:
        def normalize(value: str) -> str:
            return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()

        normalized_needle = normalize(needle)
        normalized_haystack = normalize(haystack)
        if not normalized_needle:
            return False
        if normalized_needle in normalized_haystack:
            return True
        stopwords = {
            "answer",
            "book",
            "from",
            "in",
            "mind",
            "my",
            "now",
            "on",
            "questions",
            "that",
            "the",
            "to",
            "use",
            "using",
            "with",
            "you",
        }
        tokens = [token for token in normalized_needle.split() if token not in stopwords]
        if not tokens:
            return False
        haystack_tokens = set(normalized_haystack.split())
        return all(token in haystack_tokens for token in tokens)

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

    @staticmethod
    def _clean_fact_value(value: str) -> str:
        value = re.sub(r"\s+", " ", str(value or "").strip())
        return value.rstrip(" .,!?:;")

    def _extract_session_facts(self, transcript_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        fact_patterns = [
            (
                re.compile(r"\b(?:i\s+live\s+in|i\s+am\s+in|i['’]m\s+in)\s+([A-Za-z][A-Za-z0-9 .,'&-]{1,80})\b", re.IGNORECASE),
                "location",
                "User lives in {value}.",
            ),
            (
                re.compile(r"\b(?:my\s+company\s+is|i\s+work\s+at|i\s+work\s+for|i\s+helped\s+start)\s+([A-Za-z][A-Za-z0-9 .,'&-]{1,80})\b", re.IGNORECASE),
                "organization",
                "User is associated with {value}.",
            ),
            (
                re.compile(r"\b(?:my\s+name\s+is|i\s+am\s+called)\s+([A-Za-z][A-Za-z0-9 .,'&-]{1,60})\b", re.IGNORECASE),
                "name",
                "User name is {value}.",
            ),
        ]
        facts: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for turn in transcript_rows[-self.MODEL_CONTEXT_TURN_LIMIT * 2 :]:
            if str(turn.get("role") or "").strip().lower() != "user":
                continue
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            for regex, fact_type, template in fact_patterns:
                match = regex.search(text)
                if not match:
                    continue
                value = self._clean_fact_value(match.group(1))
                if not value:
                    continue
                fact_text = template.format(value=value)
                key = (fact_type, fact_text.casefold())
                if key in seen:
                    continue
                seen.add(key)
                facts.append(
                    {
                        "type": fact_type,
                        "fact": self._truncate_text(fact_text, self.MODEL_CONTEXT_SESSION_FACT_CHARS),
                        "source_text": self._truncate_text(text, self.MODEL_CONTEXT_SESSION_FACT_CHARS),
                    }
                )
                if len(facts) >= self.MODEL_CONTEXT_SESSION_FACT_LIMIT:
                    return facts
        return facts

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
        active_room = str(state.get("active_room") or "lobby")
        transcript_rows: List[Dict[str, Any]] = []
        if session_id:
            transcript_rows = self.kernel.store.load_transcript(
                workspace_id,
                limit=max(self.MODEL_CONTEXT_TURN_LIMIT * 2, 16),
                session_id=session_id,
            )
        recent_turns = []
        recent_turn_records = []
        for turn in transcript_rows[-self.MODEL_CONTEXT_TURN_LIMIT :]:
            role = str(turn.get("role") or "assistant").strip()
            if role not in {"user", "assistant", "system"}:
                role = "assistant"
            speaker = str(turn.get("speaker") or turn.get("persona_name") or role.title()).strip()
            text = self._truncate_text(turn.get("text") or "", self.MODEL_CONTEXT_TURN_CHARS)
            if not text:
                continue
            room = str(turn.get("room") or turn.get("room_id") or state.get("active_room", "lobby")).strip()
            recent_turns.append(f"{speaker} [{role}]: {text}")
            recent_turn_records.append(
                {
                    "role": role,
                    "speaker": speaker,
                    "room": room,
                    "text": text,
                }
            )
        conversation_history_text = self._truncate_text(
            "\n".join(recent_turns),
            self.MODEL_CONTEXT_HISTORY_CHARS,
        )
        session_summary_text = self._truncate_text(
            " | ".join(recent_turns[-6:]),
            self.MODEL_CONTEXT_SUMMARY_CHARS,
        )
        session_facts = self._extract_session_facts(transcript_rows)
        session_facts_text = "\n".join(f"- {fact['fact']}" for fact in session_facts)
        merged = {
            "workspace_id": workspace_id,
            "active_room": active_room,
            "active_persona": state.get("active_persona", "Receptionist"),
            "session_summary_text": session_summary_text,
            "recent_turns_text": recent_turns,
            "recent_turns": recent_turn_records,
            "conversation_history_text": conversation_history_text,
            "session_facts": session_facts,
            "session_facts_text": session_facts_text,
            "room_behavior_memory_refs": self.room_behavior_memory_refs(
                workspace_id=workspace_id,
                room_id=active_room,
            ),
            "session_id": session_id,
        }
        return merged
