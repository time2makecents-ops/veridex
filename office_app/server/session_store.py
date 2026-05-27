from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional


SESSION_COLUMNS = (
    "session_id",
    "user_id",
    "title",
    "description",
    "active_workspace_id",
    "active_room",
    "active_persona",
    "created_at",
    "updated_at",
    "last_active_at",
)


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.table_name = "sessions_v2"
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
                CREATE TABLE IF NOT EXISTS sessions_v2 (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    active_workspace_id TEXT NOT NULL,
                    active_room TEXT NOT NULL DEFAULT 'lobby',
                    active_persona TEXT NOT NULL DEFAULT 'Receptionist',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
                """
            )
            existing_columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({self.table_name})").fetchall()}
            if "active_room" not in existing_columns:
                conn.execute(f"ALTER TABLE {self.table_name} ADD COLUMN active_room TEXT NOT NULL DEFAULT 'lobby'")
            if "active_persona" not in existing_columns:
                conn.execute(f"ALTER TABLE {self.table_name} ADD COLUMN active_persona TEXT NOT NULL DEFAULT 'Receptionist'")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_v2_user "
                "ON sessions_v2(user_id, last_active_at DESC, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_v2_active_workspace "
                "ON sessions_v2(active_workspace_id)"
            )
            self._migrate_legacy_sessions(conn)
            conn.commit()

    def _legacy_table_exists(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchone()
        return row is not None

    def _migrate_legacy_sessions(self, conn: sqlite3.Connection) -> None:
        if not self._legacy_table_exists(conn):
            return
        existing_v2 = conn.execute("SELECT COUNT(*) AS count FROM sessions_v2").fetchone()
        if existing_v2 and int(existing_v2["count"] or 0) > 0:
            return
        legacy_rows = conn.execute("SELECT * FROM sessions").fetchall()
        if not legacy_rows:
            return
        for row in legacy_rows:
            session_id = str(row["session_id"])
            active_workspace_id = str(row["active_workspace_id"])
            created_at = str(row["created_at"])
            updated_at = str(row["updated_at"])
            title = f"Session {session_id[-4:]}" if session_id else active_workspace_id
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions_v2 (
                    session_id, user_id, title, description, active_workspace_id, active_room, active_persona, created_at, updated_at, last_active_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    row["user_id"],
                    title,
                    "",
                    active_workspace_id,
                    "lobby",
                    "Receptionist",
                    created_at,
                    updated_at,
                    updated_at,
                ),
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in SESSION_COLUMNS}

    def insert_session(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload.setdefault("title", f"Session {str(payload.get('session_id') or '')[-4:]}")
        payload.setdefault("description", "")
        payload.setdefault("active_room", "lobby")
        payload.setdefault("active_persona", "Receptionist")
        payload.setdefault("last_active_at", payload.get("updated_at"))
        if not payload.get("last_active_at"):
            payload["last_active_at"] = payload["updated_at"]
        columns = ", ".join(f'"{column}"' for column in SESSION_COLUMNS)
        placeholders = ", ".join("?" for _ in SESSION_COLUMNS)
        values = [payload[column] for column in SESSION_COLUMNS]

        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()

        fetched = self.fetch_session(payload["session_id"])
        if fetched is None:
            raise LookupError(f"Session not found after insert: {payload['session_id']}")
        return fetched

    def fetch_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM sessions_v2
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def fetch_session_for_user(self, user_id: str, workspace_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            if workspace_id:
                row = conn.execute(
                    """
                    SELECT *
                    FROM sessions_v2
                    WHERE user_id = ? AND active_workspace_id = ?
                    ORDER BY last_active_at DESC, updated_at DESC
                    LIMIT 1
                    """,
                    (user_id, workspace_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT *
                    FROM sessions_v2
                    WHERE user_id = ?
                    ORDER BY last_active_at DESC, updated_at DESC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_sessions_for_user(self, user_id: str, workspace_id: Optional[str] = None) -> list[Dict[str, Any]]:
        with self._connection() as conn:
            if workspace_id:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM sessions_v2
                    WHERE user_id = ? AND active_workspace_id = ?
                    ORDER BY last_active_at DESC, updated_at DESC
                    """,
                    (user_id, workspace_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM sessions_v2
                    WHERE user_id = ?
                    ORDER BY last_active_at DESC, updated_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_sessions_for_workspace(self, workspace_id: str) -> list[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sessions_v2
                WHERE active_workspace_id = ?
                ORDER BY last_active_at DESC, updated_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in updates.items():
            if key not in SESSION_COLUMNS or key == "session_id":
                continue
            normalized[key] = value

        if not normalized:
            fetched = self.fetch_session(session_id)
            if fetched is None:
                raise LookupError(f"Session not found: {session_id}")
            return fetched

        assignments = ", ".join(f'"{column}" = ?' for column in normalized.keys())
        params = list(normalized.values()) + [session_id]

        with self._connection() as conn:
            result = conn.execute(
                f"""
                UPDATE {self.table_name}
                SET {assignments}
                WHERE session_id = ?
                """,
                params,
            )
            if result.rowcount == 0:
                raise LookupError(f"Session not found: {session_id}")
            conn.commit()

        fetched = self.fetch_session(session_id)
        if fetched is None:
            raise LookupError(f"Session not found after update: {session_id}")
        return fetched

    def delete_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        existing = self.fetch_session(session_id)
        if existing is None:
            return None

        with self._connection() as conn:
            result = conn.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE session_id = ?
                """,
                (session_id,),
            )
            if result.rowcount == 0:
                raise LookupError(f"Session not found: {session_id}")
            conn.commit()

        return existing
