from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict


class DebugNotesStore:
    def __init__(self, *, runtime_dir: Path, utc_now_fn: Callable[[], str]) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.utc_now = utc_now_fn
        self.notes_dir = self.runtime_dir / "debug_notes"
        self.notes_path = self.notes_dir / "page_notes.json"

    @staticmethod
    def normalize_page_path(page_path: str) -> str:
        text = str(page_path or "").strip()
        text = re.split(r"[?#]", text, maxsplit=1)[0].strip()
        text = re.sub(r"/+", "/", text)
        text = re.sub(r"[^A-Za-z0-9/_-]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        if not text:
            return "/"
        if not text.startswith("/"):
            text = f"/{text}"
        if len(text) > 180:
            text = text[:180].rstrip("/-_") or "/"
        return text

    @staticmethod
    def _normalize_scope_value(value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        return text[:120]

    @classmethod
    def note_key(cls, page_path: str, *, active_room: str = "", active_persona: str = "") -> str:
        normalized = cls.normalize_page_path(page_path)
        room = cls._normalize_scope_value(active_room)
        persona = cls._normalize_scope_value(active_persona)
        if normalized == "/chat" and room:
            return f"{normalized}|{room}|{persona}"
        return normalized

    @staticmethod
    def _note_scope(note_key: str, page_path: str) -> str:
        return "room_persona" if note_key != page_path and page_path == "/chat" else "page"

    def _read_all(self) -> Dict[str, Dict[str, Any]]:
        if not self.notes_path.exists():
            return {}
        try:
            payload = json.loads(self.notes_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        notes = payload.get("notes", payload)
        if not isinstance(notes, dict):
            return {}
        return {str(key): dict(value) for key, value in notes.items() if isinstance(value, dict)}

    def _write_all(self, notes: Dict[str, Dict[str, Any]]) -> None:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        payload = {"notes": notes}
        self.notes_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _empty_record(self, page_path: str, *, note_key: str, active_room: str = "", active_persona: str = "") -> Dict[str, Any]:
        return {
            "note_key": note_key,
            "note_scope": self._note_scope(note_key, page_path),
            "page_path": page_path,
            "text": "",
            "updated_at": "",
            "session_id": "",
            "workspace_id": "",
            "active_room": self._normalize_scope_value(active_room),
            "active_persona": self._normalize_scope_value(active_persona),
        }

    def _record_for_key(
        self,
        notes: Dict[str, Dict[str, Any]],
        *,
        page_path: str,
        note_key: str,
        active_room: str,
        active_persona: str,
    ) -> Dict[str, Any]:
        record = dict(notes.get(note_key) or {})
        if not record and page_path == "/chat" and note_key != page_path:
            legacy = dict(notes.get(page_path) or {})
            legacy_room = self._normalize_scope_value(str(legacy.get("active_room") or ""))
            if legacy and legacy_room and legacy_room == self._normalize_scope_value(active_room):
                record = legacy
                record["note_key"] = note_key
                record["note_scope"] = "room_persona"
                record["page_path"] = page_path
                record["active_persona"] = self._normalize_scope_value(active_persona)
                notes[note_key] = record
                self._write_all(notes)
        if not record:
            return self._empty_record(
                page_path,
                note_key=note_key,
                active_room=active_room,
                active_persona=active_persona,
            )
        return {
            "note_key": note_key,
            "note_scope": self._note_scope(note_key, page_path),
            "page_path": page_path,
            "text": str(record.get("text") or ""),
            "updated_at": str(record.get("updated_at") or ""),
            "session_id": str(record.get("session_id") or ""),
            "workspace_id": str(record.get("workspace_id") or ""),
            "active_room": str(record.get("active_room") or self._normalize_scope_value(active_room)),
            "active_persona": str(record.get("active_persona") or self._normalize_scope_value(active_persona)),
        }

    def get_note(self, page_path: str, *, active_room: str = "", active_persona: str = "") -> Dict[str, Any]:
        normalized = self.normalize_page_path(page_path)
        note_key = self.note_key(normalized, active_room=active_room, active_persona=active_persona)
        notes = self._read_all()
        return self._record_for_key(
            notes,
            page_path=normalized,
            note_key=note_key,
            active_room=active_room,
            active_persona=active_persona,
        )

    def save_note(
        self,
        *,
        page_path: str,
        text: str,
        session_id: str = "",
        workspace_id: str = "",
        active_room: str = "",
        active_persona: str = "",
    ) -> Dict[str, Any]:
        normalized = self.normalize_page_path(page_path)
        note_key = self.note_key(normalized, active_room=active_room, active_persona=active_persona)
        record = {
            "note_key": note_key,
            "note_scope": self._note_scope(note_key, normalized),
            "page_path": normalized,
            "text": str(text or ""),
            "updated_at": self.utc_now(),
            "session_id": str(session_id or "").strip(),
            "workspace_id": str(workspace_id or "").strip(),
            "active_room": self._normalize_scope_value(active_room),
            "active_persona": self._normalize_scope_value(active_persona),
        }
        notes = self._read_all()
        notes[note_key] = record
        self._write_all(notes)
        return dict(record)
