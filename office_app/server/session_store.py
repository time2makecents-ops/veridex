from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional


SESSION_COLUMNS = (
    "session_id",
    "user_id",
    "active_workspace_id",
    "created_at",
    "updated_at",
)


class SessionStore:
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
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE,
                    active_workspace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_active_workspace "
                "ON sessions(active_workspace_id)"
            )
            conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in SESSION_COLUMNS}

    def insert_session(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        columns = ", ".join(f'"{column}"' for column in SESSION_COLUMNS)
        placeholders = ", ".join("?" for _ in SESSION_COLUMNS)
        values = [payload[column] for column in SESSION_COLUMNS]

        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO sessions ({columns}) VALUES ({placeholders})",
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
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def fetch_session_for_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM sessions
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

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
                UPDATE sessions
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
