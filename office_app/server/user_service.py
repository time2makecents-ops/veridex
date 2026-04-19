from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from office_app.server.errors import error_missing_required_field
from office_app.server.session_store import SessionStore
from office_app.server.user_store import UserStore


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


PIN_RE = re.compile(r"^\d{4}$")


class UserService:
    def __init__(
        self,
        *,
        kernel,
        runtime_dir: Path = Path("office_app/runtime"),
        utc_now_fn=utc_now_iso,
    ):
        self.kernel = kernel
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir = self.runtime_dir / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runtime_dir / "veridex.db"
        self.utc_now = utc_now_fn
        self.store = UserStore(self.db_path)
        self.sessions = SessionStore(self.db_path)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _safe_folder_name(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
        slug = slug.strip("._-")
        return slug or "user"

    @staticmethod
    def _normalize_pin(pin_code: Any) -> str:
        pin = str(pin_code or "").strip()
        if not PIN_RE.fullmatch(pin):
            raise HTTPException(status_code=400, detail="PIN code must be exactly 4 digits.")
        return pin

    @staticmethod
    def _photo_extension(mime_type: str) -> str:
        mime = mime_type.lower().strip()
        if mime in {"image/jpeg", "image/jpg"}:
            return "jpg"
        if mime == "image/png":
            return "png"
        if mime == "image/webp":
            return "webp"
        return "bin"

    @staticmethod
    def _decode_photo_data(photo_data: Optional[str]) -> tuple[Optional[str], Optional[bytes]]:
        if not photo_data:
            return None, None

        raw = str(photo_data).strip()
        if not raw:
            return None, None

        if raw.startswith("data:") and "," in raw:
            header, payload = raw.split(",", 1)
            mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
            return mime_type, base64.b64decode(payload)

        return "image/jpeg", base64.b64decode(raw)

    @staticmethod
    def _decorate_user(record: Dict[str, Any]) -> Dict[str, Any]:
        decorated = dict(record)
        decorated["lobby_ready"] = bool(decorated.get("onboarding_complete"))
        return decorated

    def _user_folder_path(self, record: Dict[str, Any]) -> Path:
        label = record.get("display_name") or record.get("name") or "user"
        folder_name = f"{self._safe_folder_name(str(label))}-{record['user_id']}"
        return self.users_dir / folder_name

    def _sync_user_folder(self, record: Dict[str, Any]) -> None:
        folder = self._user_folder_path(record)
        folder.mkdir(parents=True, exist_ok=True)

        photo_file_name = None
        face_photo_data = record.get("face_photo_data")
        if face_photo_data:
            mime_type, photo_bytes = self._decode_photo_data(face_photo_data)
            if mime_type and photo_bytes is not None:
                photo_ext = self._photo_extension(mime_type)
                for old_file in folder.glob("face_photo.*"):
                    try:
                        old_file.unlink()
                    except OSError:
                        pass
                photo_file = folder / f"face_photo.{photo_ext}"
                photo_file.write_bytes(photo_bytes)
                photo_file_name = photo_file.name

        profile = {
            "user_id": record.get("user_id"),
            "name": record.get("name"),
            "display_name": record.get("display_name"),
            "onboarding_complete": bool(record.get("onboarding_complete")),
            "default_workspace_id": record.get("default_workspace_id"),
            "last_active_workspace_id": record.get("last_active_workspace_id"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "has_face_photo": bool(photo_file_name),
            "face_photo_file": photo_file_name,
        }
        (folder / "profile.json").write_text(
            json.dumps(profile, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _ensure_workspace(self, workspace_id: str, label: str) -> Dict[str, Any]:
        try:
            return self.kernel.get_state(workspace_id)
        except HTTPException:
            self.kernel.create_workspace(workspace_id, label)
            return self.kernel.get_state(workspace_id)

    def _create_or_return_session(self, user_id: str, workspace_id: str) -> Dict[str, Any]:
        existing = self.sessions.fetch_session_for_user(user_id)
        now = self.utc_now()
        if existing is None:
            session = self.sessions.insert_session(
                {
                    "session_id": f"sess_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "active_workspace_id": workspace_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return session

        return self.sessions.update_session(
            existing["session_id"],
            {
                "active_workspace_id": workspace_id,
                "updated_at": now,
            },
        )

    def onboard_user(
        self,
        *,
        name: str,
        pin_code: str,
        display_name: Optional[str] = None,
        face_photo_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        name_text = self._normalize_text(name)
        if not name_text:
            raise error_missing_required_field("name")

        pin = self._normalize_pin(pin_code)
        if self.store.fetch_user_by_pin(pin) is not None:
            raise HTTPException(status_code=409, detail="That PIN code is already in use.")

        display_text = self._normalize_text(display_name) or name_text
        user_id = f"usr_{uuid.uuid4().hex[:10]}"
        workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
        now = self.utc_now()

        self.kernel.create_workspace(workspace_id, display_text)
        record = self.store.insert_user(
            {
                "user_id": user_id,
                "name": name_text,
                "display_name": display_text,
                "pin_code": pin,
                "face_photo_data": face_photo_data,
                "onboarding_complete": True,
                "default_workspace_id": workspace_id,
                "last_active_workspace_id": workspace_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        self._sync_user_folder(record)
        session = self._create_or_return_session(user_id, workspace_id)

        state = self.kernel.get_state(workspace_id)
        return {
            "user": self._decorate_user(record),
            "session": session,
            "session_id": session["session_id"],
            "workspace_id": workspace_id,
            "workspace_state": state,
            "mode": "onboarding_complete",
        }

    def enter_lobby(self, *, pin_code: str) -> Dict[str, Any]:
        pin = self._normalize_pin(pin_code)
        record = self.store.fetch_user_by_pin(pin)
        if record is None:
            raise HTTPException(status_code=401, detail="Invalid PIN code.")

        workspace_id = str(record.get("last_active_workspace_id") or record.get("default_workspace_id") or "").strip()
        if not workspace_id:
            raise HTTPException(status_code=409, detail="User profile is missing a workspace link.")

        workspace_state = self._ensure_workspace(workspace_id, record.get("display_name") or record.get("name") or "Workspace")
        updated = self.store.update_user(
            record["user_id"],
            {
                "last_active_workspace_id": workspace_id,
                "updated_at": self.utc_now(),
            },
        )
        self._sync_user_folder(updated)
        session = self._create_or_return_session(record["user_id"], workspace_id)

        return {
            "user": self._decorate_user(updated),
            "session": session,
            "session_id": session["session_id"],
            "workspace_id": workspace_id,
            "workspace_state": workspace_state,
            "mode": "lobby_reentry",
        }

    def get_user_by_pin(self, pin_code: str) -> Dict[str, Any]:
        pin = self._normalize_pin(pin_code)
        record = self.store.fetch_user_by_pin(pin)
        if record is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return self._decorate_user(record)

    def resolve_workspace_for_session(self, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        session = self.sessions.fetch_session(session_id)
        if session is None:
            raise HTTPException(status_code=401, detail="Invalid session.")
        return str(session.get("active_workspace_id") or "").strip() or None

    def get_session(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions.fetch_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session
