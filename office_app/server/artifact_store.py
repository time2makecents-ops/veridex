from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional


ARTIFACT_COLUMNS = (
    "artifact_id",
    "workspace_id",
    "type",
    "title",
    "content",
    "format",
    "status",
    "created_by",
    "created_at",
    "updated_at",
    "metadata",
    "version",
    "source_refs",
    "archived",
)

UPDATABLE_COLUMNS = {
    "type",
    "title",
    "content",
    "format",
    "status",
    "updated_at",
    "metadata",
    "version",
    "source_refs",
    "archived",
}


class ArtifactStore:
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

    @staticmethod
    def _dump_json(value: Any, fallback: str) -> str:
        if value is None:
            return fallback
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return fallback
            try:
                json.loads(stripped)
                return stripped
            except json.JSONDecodeError:
                return json.dumps(value)
        return json.dumps(value)

    @staticmethod
    def _load_json(value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return fallback
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except json.JSONDecodeError:
            return fallback

    def _ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    "type" TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    "format" TEXT NOT NULL DEFAULT 'text/plain',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    version INTEGER NOT NULL DEFAULT 1,
                    source_refs TEXT NOT NULL DEFAULT '[]',
                    archived INTEGER NOT NULL DEFAULT 0,
                    CHECK (archived IN (0, 1))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_workspace_updated "
                "ON artifacts(workspace_id, archived, updated_at DESC, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_workspace_type "
                "ON artifacts(workspace_id, \"type\")"
            )
            conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> Dict[str, Any]:
        record = {key: row[key] for key in ARTIFACT_COLUMNS}
        record["metadata"] = self._load_json(record["metadata"], {})
        record["source_refs"] = self._load_json(record["source_refs"], [])
        record["version"] = int(record["version"])
        record["archived"] = bool(record["archived"])
        return record

    def fetch_record(self, workspace_id: str, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM artifacts
                WHERE workspace_id = ? AND artifact_id = ?
                """,
                (workspace_id, artifact_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_records(self, workspace_id: str, *, include_archived: bool = False) -> List[Dict[str, Any]]:
        sql = """
            SELECT *
            FROM artifacts
            WHERE workspace_id = ?
        """
        params: List[Any] = [workspace_id]
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY updated_at DESC, created_at DESC, artifact_id DESC"

        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def insert_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload["metadata"] = self._dump_json(payload.get("metadata"), "{}")
        payload["source_refs"] = self._dump_json(payload.get("source_refs"), "[]")
        payload["archived"] = 1 if bool(payload.get("archived", False)) else 0

        columns = ", ".join(f'"{column}"' for column in ARTIFACT_COLUMNS)
        placeholders = ", ".join("?" for _ in ARTIFACT_COLUMNS)
        values = [payload[column] for column in ARTIFACT_COLUMNS]

        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO artifacts ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()

        fetched = self.fetch_record(str(payload["workspace_id"]), str(payload["artifact_id"]))
        if fetched is None:
            raise LookupError(f"Artifact not found after insert: {payload['artifact_id']}")
        return fetched

    def update_record(self, workspace_id: str, artifact_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in updates.items():
            if key not in UPDATABLE_COLUMNS:
                continue
            if key in {"metadata", "source_refs"}:
                fallback = "{}" if key == "metadata" else "[]"
                normalized[key] = self._dump_json(value, fallback)
            elif key == "archived":
                normalized[key] = 1 if bool(value) else 0
            else:
                normalized[key] = value

        if not normalized:
            fetched = self.fetch_record(workspace_id, artifact_id)
            if fetched is None:
                raise LookupError(f"Artifact not found: {artifact_id}")
            return fetched

        assignments = ", ".join(f'"{column}" = ?' for column in normalized.keys())
        params = list(normalized.values()) + [workspace_id, artifact_id]

        with self._connection() as conn:
            result = conn.execute(
                f"""
                UPDATE artifacts
                SET {assignments}
                WHERE workspace_id = ? AND artifact_id = ?
                """,
                params,
            )
            if result.rowcount == 0:
                raise LookupError(f"Artifact not found: {artifact_id}")
            conn.commit()

        fetched = self.fetch_record(workspace_id, artifact_id)
        if fetched is None:
            raise LookupError(f"Artifact not found after update: {artifact_id}")
        return fetched
