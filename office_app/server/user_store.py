from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional


USER_COLUMNS = (
    "user_id",
    "name",
    "display_name",
    "pin_code",
    "role",
    "face_photo_data",
    "onboarding_complete",
    "default_workspace_id",
    "last_active_workspace_id",
    "last_active_session_id",
    "created_at",
    "updated_at",
)


class UserStore:
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
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    pin_code TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'user',
                    face_photo_data TEXT,
                    onboarding_complete INTEGER NOT NULL DEFAULT 0,
                    default_workspace_id TEXT NOT NULL,
                    last_active_workspace_id TEXT NOT NULL,
                    last_active_session_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (onboarding_complete IN (0, 1))
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "role" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            if "face_photo_data" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN face_photo_data TEXT")
            if "last_active_session_id" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN last_active_session_id TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_last_active_workspace "
                "ON users(last_active_workspace_id)"
            )
            conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
        record = {key: row[key] for key in USER_COLUMNS}
        record["onboarding_complete"] = bool(record["onboarding_complete"])
        return record

    def insert_user(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        columns = ", ".join(f'"{column}"' for column in USER_COLUMNS)
        placeholders = ", ".join("?" for _ in USER_COLUMNS)
        values = [payload[column] for column in USER_COLUMNS]

        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO users ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()

        fetched = self.fetch_user(payload["user_id"])
        if fetched is None:
            raise LookupError(f"User not found after insert: {payload['user_id']}")
        return fetched

    def fetch_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def fetch_user_by_pin(self, pin_code: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM users
                WHERE pin_code = ?
                """,
                (pin_code,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in updates.items():
            if key not in USER_COLUMNS or key == "user_id":
                continue
            if key == "onboarding_complete":
                normalized[key] = 1 if bool(value) else 0
            else:
                normalized[key] = value

        if not normalized:
            fetched = self.fetch_user(user_id)
            if fetched is None:
                raise LookupError(f"User not found: {user_id}")
            return fetched

        assignments = ", ".join(f'"{column}" = ?' for column in normalized.keys())
        params = list(normalized.values()) + [user_id]

        with self._connection() as conn:
            result = conn.execute(
                f"""
                UPDATE users
                SET {assignments}
                WHERE user_id = ?
                """,
                params,
            )
            if result.rowcount == 0:
                raise LookupError(f"User not found: {user_id}")
            conn.commit()

        fetched = self.fetch_user(user_id)
        if fetched is None:
            raise LookupError(f"User not found after update: {user_id}")
        return fetched

    def list_users(self) -> list[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM users
                ORDER BY updated_at DESC, created_at DESC, display_name ASC
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count_users_for_workspace(self, workspace_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM users
                WHERE default_workspace_id = ?
                   OR last_active_workspace_id = ?
                """,
                (workspace_id, workspace_id),
            ).fetchone()
        return int(row["count"] or 0) if row is not None else 0

    def delete_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        existing = self.fetch_user(user_id)
        if existing is None:
            return None

        with self._connection() as conn:
            result = conn.execute(
                """
                DELETE FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            )
            if result.rowcount == 0:
                raise LookupError(f"User not found: {user_id}")
            conn.commit()

        return existing
