from __future__ import annotations

import base64
import json
import shutil
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
    ADMIN_PIN = "1978"
    ADMIN_ROLE = "admin"
    DEFAULT_ROLE = "user"
    DEFAULT_ADMIN_NAME = "Admin"
    DEFAULT_ADMIN_DISPLAY_NAME = "Admin"

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
        decorated["is_admin"] = str(decorated.get("role") or "").strip().lower() == UserService.ADMIN_ROLE
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
            "pin_code": record.get("pin_code"),
            "role": record.get("role") or self.DEFAULT_ROLE,
            "onboarding_complete": bool(record.get("onboarding_complete")),
            "default_workspace_id": record.get("default_workspace_id"),
            "last_active_workspace_id": record.get("last_active_workspace_id"),
            "last_active_session_id": record.get("last_active_session_id"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "has_face_photo": bool(photo_file_name),
            "face_photo_file": photo_file_name,
        }
        (folder / "profile.json").write_text(
            json.dumps(profile, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        pin_code = str(record.get("pin_code") or "").strip()
        if pin_code:
            (folder / "pin_code.txt").write_text(f"{pin_code}\n", encoding="utf-8")

    def _role_for_pin(self, pin: str) -> str:
        return self.ADMIN_ROLE if str(pin or "").strip() == self.ADMIN_PIN else self.DEFAULT_ROLE

    def _ensure_workspace(self, workspace_id: str, label: str) -> Dict[str, Any]:
        try:
            return self.kernel.get_state(workspace_id)
        except HTTPException:
            self.kernel.create_workspace(workspace_id, label)
            return self.kernel.get_state(workspace_id)

    def _default_session_title(self, workspace_label: str) -> str:
        text = self._normalize_text(workspace_label) or "Session"
        if len(text) > 48:
            return text[:48].rstrip()
        return text

    def _create_session_record(
        self,
        *,
        user_id: str,
        workspace_id: str,
        title: str,
        description: str = "",
        active_room: Optional[str] = None,
        active_persona: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = self.utc_now()
        try:
            workspace_state = self.kernel.get_state(workspace_id)
            default_active_room = str(workspace_state.get("active_room") or "lobby")
            default_active_persona = str(workspace_state.get("active_persona") or "Receptionist")
        except Exception:
            default_active_room = "lobby"
            default_active_persona = "Receptionist"
        return self.sessions.insert_session(
            {
                "session_id": f"sess_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "title": self._normalize_text(title) or "Session",
                "description": self._normalize_text(description),
                "active_workspace_id": workspace_id,
                "active_room": self._normalize_text(active_room) or default_active_room,
                "active_persona": self._normalize_text(active_persona) or default_active_persona,
                "created_at": now,
                "updated_at": now,
                "last_active_at": now,
            }
        )

    def _workspace_label_for(self, workspace_id: str) -> str:
        try:
            index = self.kernel.list_workspaces()
        except Exception:
            return workspace_id
        for row in index.get("workspaces", []):
            if str(row.get("workspace_id") or "").strip() == workspace_id:
                return str(row.get("label") or workspace_id).strip() or workspace_id
        return workspace_id

    def _activate_session(self, user_id: str, session_id: str) -> Dict[str, Any]:
        session = self.sessions.fetch_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        now = self.utc_now()
        activated = self.sessions.update_session(
            session_id,
            {
                "last_active_at": now,
                "updated_at": now,
            },
        )
        self.store.update_user(
            user_id,
            {
                "last_active_workspace_id": activated["active_workspace_id"],
                "last_active_session_id": activated["session_id"],
                "updated_at": now,
            },
        )
        self._restore_session_room(activated)
        return activated

    def _restore_session_room(self, session: Dict[str, Any]) -> None:
        workspace_id = str(session.get("active_workspace_id") or "").strip()
        if not workspace_id:
            return
        try:
            state = self.kernel.get_state(workspace_id)
        except HTTPException:
            return
        active_room = str(session.get("active_room") or state.get("active_room") or "lobby")
        active_persona = str(session.get("active_persona") or state.get("active_persona") or "Receptionist")
        state["active_room"] = active_room
        state["active_persona"] = active_persona
        self.kernel.store.save_state(workspace_id, state)
        self.kernel.store.touch_workspace(workspace_id, active_room)

    def restore_session_room(self, session_id: Optional[str]) -> None:
        session_id = str(session_id or "").strip()
        if not session_id:
            return
        session = self.sessions.fetch_session(session_id)
        if session is None:
            return
        self._restore_session_room(session)

    def remember_session_room(self, session_id: Optional[str], *, active_room: str, active_persona: str) -> None:
        session_id = str(session_id or "").strip()
        if not session_id:
            return
        try:
            self.sessions.update_session(
                session_id,
                {
                    "active_room": self._normalize_text(active_room) or "lobby",
                    "active_persona": self._normalize_text(active_persona) or "Receptionist",
                    "updated_at": self.utc_now(),
                    "last_active_at": self.utc_now(),
                },
            )
        except LookupError:
            return

    def create_session(
        self,
        *,
        user_id: str,
        title: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        workspace_label: Optional[str] = None,
        active_room: Optional[str] = None,
        active_persona: Optional[str] = None,
    ) -> Dict[str, Any]:
        workspace_title = self._normalize_text(workspace_label) or self._default_session_title(title)
        if workspace_id:
            workspace_id = str(workspace_id).strip()
            self._ensure_workspace(workspace_id, workspace_title)
        else:
            workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
            self.kernel.create_workspace(workspace_id, workspace_title)
        session = self._create_session_record(
            user_id=user_id,
            workspace_id=workspace_id,
            title=title or workspace_title,
            description=description,
            active_room=active_room,
            active_persona=active_persona,
        )
        self.kernel.store.append_transcript(
            workspace_id,
            "system",
            "lobby",
            f"Session created: {session['title']}",
            speaker="System",
            session_id=session["session_id"],
        )
        self.store.update_user(
            user_id,
            {
                "last_active_workspace_id": workspace_id,
                "last_active_session_id": session["session_id"],
                "updated_at": self.utc_now(),
            },
        )
        return session

    def list_sessions(self, user_id: str, workspace_id: Optional[str] = None) -> list[Dict[str, Any]]:
        return self.sessions.list_sessions_for_user(user_id, workspace_id=workspace_id)

    def list_user_workspaces(self, user_id: str) -> list[Dict[str, Any]]:
        sessions = self.sessions.list_sessions_for_user(user_id)
        workspaces: Dict[str, Dict[str, Any]] = {}
        index = self.kernel.list_workspaces()
        labels = {str(row.get("workspace_id") or ""): str(row.get("label") or "") for row in index.get("workspaces", []) if isinstance(row, dict)}
        descriptions = {
            str(row.get("workspace_id") or ""): str(row.get("description") or "")
            for row in index.get("workspaces", [])
            if isinstance(row, dict)
        }
        for session in sessions:
            workspace_id = str(session.get("active_workspace_id") or "").strip()
            if not workspace_id:
                continue
            entry = workspaces.setdefault(
                workspace_id,
                {
                    "workspace_id": workspace_id,
                    "label": labels.get(workspace_id) or workspace_id,
                    "description": descriptions.get(workspace_id) or "",
                    "session_count": 0,
                    "last_active_at": "",
                    "last_session_id": "",
                },
            )
            entry["session_count"] += 1
            session_active_at = str(session.get("last_active_at") or session.get("updated_at") or "")
            if session_active_at >= str(entry.get("last_active_at") or ""):
                entry["last_active_at"] = session_active_at
                entry["last_session_id"] = str(session.get("session_id") or "")
        rows = sorted(workspaces.values(), key=lambda item: (str(item.get("last_active_at") or ""), str(item.get("workspace_id") or "")), reverse=True)
        return rows

    def latest_session_for_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.fetch_session_for_user(user_id)

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
        role = self._role_for_pin(pin)
        record = self.store.insert_user(
            {
                "user_id": user_id,
                "name": name_text,
                "display_name": display_text,
                "pin_code": pin,
                "role": role,
                "face_photo_data": face_photo_data,
                "onboarding_complete": True,
                "default_workspace_id": workspace_id,
                "last_active_workspace_id": workspace_id,
                "last_active_session_id": "",
                "created_at": now,
                "updated_at": now,
            }
        )
        self._sync_user_folder(record)
        session = self._create_session_record(
            user_id=user_id,
            workspace_id=workspace_id,
            title=display_text,
            description="Initial onboarding session.",
        )
        self.store.update_user(
            user_id,
            {
                "last_active_session_id": session["session_id"],
                "last_active_workspace_id": workspace_id,
                "updated_at": now,
            },
        )

        state = self.kernel.get_state(workspace_id)
        return {
            "user": self._decorate_user(record),
            "session": session,
            "session_id": session["session_id"],
            "workspace_id": workspace_id,
            "workspace_state": state,
            "mode": "onboarding_complete",
        }

    def ensure_admin_user(self) -> Dict[str, Any]:
        record = self.store.fetch_user_by_pin(self.ADMIN_PIN)
        if record is not None:
            if str(record.get("role") or "").strip().lower() != self.ADMIN_ROLE:
                record = self.store.update_user(
                    str(record["user_id"]),
                    {
                        "role": self.ADMIN_ROLE,
                        "updated_at": self.utc_now(),
                    },
                )
                self._sync_user_folder(record)
            return self._decorate_user(record)
        result = self.onboard_user(
            name=self.DEFAULT_ADMIN_NAME,
            display_name=self.DEFAULT_ADMIN_DISPLAY_NAME,
            pin_code=self.ADMIN_PIN,
        )
        return dict(result["user"])

    def enter_lobby(self, *, pin_code: str) -> Dict[str, Any]:
        pin = self._normalize_pin(pin_code)
        record = self.store.fetch_user_by_pin(pin)
        if record is None:
            raise HTTPException(status_code=401, detail="Invalid PIN code.")

        workspace_id = str(record.get("last_active_workspace_id") or record.get("default_workspace_id") or "").strip()
        if not workspace_id:
            raise HTTPException(status_code=409, detail="User profile is missing a workspace link.")

        workspace_state = self._ensure_workspace(workspace_id, record.get("display_name") or record.get("name") or "Workspace")
        last_active_session_id = str(record.get("last_active_session_id") or "").strip()
        session = self.sessions.fetch_session(last_active_session_id) if last_active_session_id else None
        if session is None:
            session = self.sessions.fetch_session_for_user(record["user_id"], workspace_id=workspace_id)
        if session is None:
            session = self._create_session_record(
                user_id=record["user_id"],
                workspace_id=workspace_id,
                title=str(record.get("display_name") or record.get("name") or "Session"),
                description="Restored session.",
            )
        else:
            session = self._activate_session(record["user_id"], session["session_id"])
        updated = self.store.update_user(
            record["user_id"],
            {
                "last_active_workspace_id": workspace_id,
                "last_active_session_id": session["session_id"],
                "updated_at": self.utc_now(),
            },
        )
        self._sync_user_folder(updated)

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

    def get_user(self, user_id: str) -> Dict[str, Any]:
        record = self.store.fetch_user(str(user_id or "").strip())
        if record is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return self._decorate_user(record)

    def list_users(self) -> list[Dict[str, Any]]:
        rows = self.store.list_users()
        users: list[Dict[str, Any]] = []
        for row in rows:
            decorated = self._decorate_user(row)
            sessions = self.sessions.list_sessions_for_user(str(row.get("user_id") or "").strip())
            workspace_ids = {
                str(row.get("default_workspace_id") or "").strip(),
                str(row.get("last_active_workspace_id") or "").strip(),
            }
            workspace_ids.update(str(session.get("active_workspace_id") or "").strip() for session in sessions)
            workspace_ids.discard("")
            decorated["session_count"] = len(sessions)
            decorated["workspace_count"] = len(workspace_ids)
            users.append(decorated)
        return users

    def get_user_admin_detail(self, user_id: str) -> Dict[str, Any]:
        user = self.get_user(user_id)
        sessions = self.sessions.list_sessions_for_user(str(user["user_id"]))
        workspaces = self.list_user_workspaces(str(user["user_id"]))
        workspace_ids = [str(item.get("workspace_id") or "").strip() for item in workspaces if str(item.get("workspace_id") or "").strip()]
        artifact_rows = []
        try:
            from office_app.server.archive_service import ArchiveService

            archive_service = ArchiveService(workspaces_dir=self.kernel.store.workspaces_dir, utc_now_fn=self.utc_now)
            artifact_rows = archive_service.list_artifacts_across_workspaces(workspace_ids, include_archived=True)
        except Exception:
            artifact_rows = []
        folder = self._user_folder_path(user)
        profile_path = folder / "profile.json"
        return {
            "user": user,
            "sessions": sessions,
            "workspaces": workspaces,
            "artifacts": artifact_rows,
            "user_folder": str(folder),
            "profile_path": str(profile_path) if profile_path.exists() else "",
        }

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

    def get_user_for_session(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        user_id = str(session.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found.")
        record = self.store.fetch_user(user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return self._decorate_user(record)

    def get_session_transcript(self, *, user_id: str, session_id: str, limit: int = 400) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if str(session.get("user_id") or "").strip() != str(user_id or "").strip():
            raise HTTPException(status_code=404, detail="Session not found.")
        workspace_id = str(session.get("active_workspace_id") or "").strip()
        entries = self.kernel.store.load_transcript(workspace_id, limit=limit, session_id=session_id)
        return {
            "user_id": user_id,
            "session": session,
            "workspace_id": workspace_id,
            "count": len(entries),
            "entries": entries,
        }

    def create_session_from_current(self, session_id: str, *, title: str, description: str = "") -> Dict[str, Any]:
        current_session = self.get_session(session_id)
        user_id = str(current_session.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found.")
        return self.create_session(
            user_id=user_id,
            title=title,
            description=description,
            workspace_id=str(current_session.get("active_workspace_id") or "").strip() or None,
            workspace_label=title,
        )

    def activate_workspace(self, *, user_id: str, workspace_id: str) -> Dict[str, Any]:
        workspace_id = str(workspace_id or "").strip()
        if not workspace_id:
            raise HTTPException(status_code=400, detail="Workspace ID required.")
        workspace_state = self._ensure_workspace(workspace_id, workspace_id)
        workspace_label = str(workspace_state.get("workspace_id") or workspace_id)
        session = self.sessions.fetch_session_for_user(user_id, workspace_id=workspace_id)
        if session is None:
            session = self.create_session(
                user_id=user_id,
                title=workspace_label,
                description=f"Workspace session for {workspace_label}.",
                workspace_id=workspace_id,
                workspace_label=workspace_label,
            )
        else:
            session = self._activate_session(user_id, str(session["session_id"]))
        self.store.update_user(
            user_id,
            {
                "last_active_workspace_id": workspace_id,
                "last_active_session_id": session["session_id"],
                "updated_at": self.utc_now(),
            },
        )
        return {
            "workspace_id": workspace_id,
            "session": session,
            "workspace_state": self.kernel.get_state(workspace_id),
        }

    def select_session_for_user(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        user_id = str(session.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found.")
        return self._activate_session(user_id, session_id)

    def delete_session(self, *, user_id: str, session_id: str) -> Dict[str, Any]:
        target_session = self.get_session(session_id)
        target_user_id = str(target_session.get("user_id") or "").strip()
        if target_user_id != str(user_id or "").strip():
            raise HTTPException(status_code=404, detail="Session not found.")

        workspace_id = str(target_session.get("active_workspace_id") or "").strip()
        if not workspace_id:
            raise HTTPException(status_code=404, detail="Session not found.")

        user_record = self.store.fetch_user(user_id)
        if user_record is None:
            raise HTTPException(status_code=404, detail="User not found.")

        current_active_session_id = str(user_record.get("last_active_session_id") or "").strip()
        remaining_sessions = [
            row
            for row in self.sessions.list_sessions_for_user(user_id, workspace_id=workspace_id)
            if str(row.get("session_id") or "").strip() != session_id
        ]

        deleted = self.sessions.delete_session(session_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Session not found.")

        session_dir = self.kernel.store.workspace_dir(workspace_id) / "sessions" / session_id
        shutil.rmtree(session_dir, ignore_errors=True)

        replacement_session: Optional[Dict[str, Any]] = None
        created_replacement_session = False
        if current_active_session_id == session_id:
            if remaining_sessions:
                replacement_session = self._activate_session(user_id, str(remaining_sessions[0]["session_id"]))
            else:
                workspace_label = self._workspace_label_for(workspace_id)
                replacement_session = self.create_session(
                    user_id=user_id,
                    title="New Session",
                    description="Fresh session.",
                    workspace_id=workspace_id,
                    workspace_label=workspace_label,
                    active_room="lobby",
                    active_persona="Receptionist",
                )
                created_replacement_session = True
                replacement_session = self._activate_session(user_id, str(replacement_session["session_id"]))

        active_session = replacement_session or self.sessions.fetch_session(
            current_active_session_id
        )
        if active_session is None:
            active_session = self.sessions.fetch_session_for_user(user_id, workspace_id=workspace_id)

        if active_session is None:
            active_session = self.create_session(
                user_id=user_id,
                title="New Session",
                description="Fresh session.",
                workspace_id=workspace_id,
                workspace_label=self._workspace_label_for(workspace_id),
                active_room="lobby",
                active_persona="Receptionist",
            )
            active_session = self._activate_session(user_id, str(active_session["session_id"]))

        final_remaining_count = len(self.sessions.list_sessions_for_user(user_id, workspace_id=workspace_id))
        try:
            workspace_state = self.kernel.get_state(str(active_session.get("active_workspace_id") or workspace_id))
        except HTTPException:
            workspace_state = {}

        return {
            "deleted_session": deleted,
            "session": active_session,
            "session_id": str(active_session.get("session_id") or ""),
            "workspace_id": str(active_session.get("active_workspace_id") or workspace_id),
            "workspace_state": workspace_state,
            "replacement_session": replacement_session,
            "remaining_count": final_remaining_count,
            "created_replacement_session": created_replacement_session,
        }

    def delete_user(self, *, user_id: str) -> Dict[str, Any]:
        record = self.store.fetch_user(str(user_id or "").strip())
        if record is None:
            raise HTTPException(status_code=404, detail="User not found.")

        sessions = self.sessions.list_sessions_for_user(str(record["user_id"]))
        workspace_ids = {
            str(record.get("default_workspace_id") or "").strip(),
            str(record.get("last_active_workspace_id") or "").strip(),
        }
        workspace_ids.update(str(session.get("active_workspace_id") or "").strip() for session in sessions)
        workspace_ids.discard("")

        deleted = self.store.delete_user(str(record["user_id"]))
        if deleted is None:
            raise HTTPException(status_code=404, detail="User not found.")

        for session in sessions:
            workspace_id = str(session.get("active_workspace_id") or "").strip()
            session_id = str(session.get("session_id") or "").strip()
            if workspace_id and session_id:
                session_dir = self.kernel.store.workspace_dir(workspace_id) / "sessions" / session_id
                shutil.rmtree(session_dir, ignore_errors=True)

        shutil.rmtree(self._user_folder_path(record), ignore_errors=True)

        removed_workspaces: list[str] = []
        for workspace_id in sorted(workspace_ids):
            if self.sessions.list_sessions_for_workspace(workspace_id):
                continue
            if self.store.count_users_for_workspace(workspace_id) > 0:
                continue
            shutil.rmtree(self.kernel.store.workspace_dir(workspace_id), ignore_errors=True)
            self.kernel.store.unregister_workspace(workspace_id)
            removed_workspaces.append(workspace_id)

        return {
            "deleted_user": self._decorate_user(record),
            "deleted_session_count": len(sessions),
            "removed_workspaces": removed_workspaces,
        }

    def rename_session(
        self,
        *,
        user_id: str,
        session_id: str,
        title: str,
        description: str = "",
    ) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if str(session.get("user_id") or "").strip() != str(user_id or "").strip():
            raise HTTPException(status_code=404, detail="Session not found.")

        normalized_title = self._normalize_text(title) or "New Session"
        normalized_description = self._normalize_text(description) or normalized_title
        updated = self.sessions.update_session(
            session_id,
            {
                "title": normalized_title,
                "description": normalized_description,
                "updated_at": self.utc_now(),
                "last_active_at": self.utc_now(),
            },
        )
        self.store.update_user(
            user_id,
            {
                "last_active_workspace_id": str(updated.get("active_workspace_id") or ""),
                "last_active_session_id": str(updated.get("session_id") or ""),
                "updated_at": self.utc_now(),
            },
        )
        self._restore_session_room(updated)
        return {
            "session": updated,
            "session_id": str(updated.get("session_id") or ""),
            "workspace_id": str(updated.get("active_workspace_id") or ""),
        }
