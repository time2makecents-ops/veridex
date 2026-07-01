from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


FILE_COLUMNS = (
    "file_id",
    "workspace_id",
    "scope",
    "scope_ref",
    "uploaded_by_user_id",
    "uploaded_by_session_id",
    "original_name",
    "stored_name",
    "storage_path",
    "mime_type",
    "byte_size",
    "sha256",
    "kind",
    "description",
    "created_at",
    "updated_at",
)


class WorkspaceFileStore:
    def __init__(self, db_path: Path, storage_root: Path, utc_now_fn):
        self.db_path = Path(db_path)
        self.storage_root = Path(storage_root)
        self.utc_now = utc_now_fn
        self.storage_root.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS workspace_files (
                    file_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'workspace',
                    scope_ref TEXT NOT NULL DEFAULT '',
                    uploaded_by_user_id TEXT,
                    uploaded_by_session_id TEXT,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'generic',
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(workspace_files)").fetchall()
            }
            migrations = [
                ("scope", "ALTER TABLE workspace_files ADD COLUMN scope TEXT NOT NULL DEFAULT 'workspace'"),
                ("scope_ref", "ALTER TABLE workspace_files ADD COLUMN scope_ref TEXT NOT NULL DEFAULT ''"),
                ("uploaded_by_user_id", "ALTER TABLE workspace_files ADD COLUMN uploaded_by_user_id TEXT"),
                ("uploaded_by_session_id", "ALTER TABLE workspace_files ADD COLUMN uploaded_by_session_id TEXT"),
                ("description", "ALTER TABLE workspace_files ADD COLUMN description TEXT"),
            ]
            for column_name, ddl in migrations:
                if column_name not in existing_columns:
                    conn.execute(ddl)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspace_files_workspace_created "
                "ON workspace_files(workspace_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspace_files_workspace_kind "
                "ON workspace_files(workspace_id, kind)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspace_files_scope "
                "ON workspace_files(workspace_id, scope, scope_ref)"
            )
            conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
        return {key: row[key] for key in FILE_COLUMNS}

    @staticmethod
    def _safe_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
        cleaned = cleaned.strip("._-")
        return cleaned or "file"

    def files_dir(self, workspace_id: str, scope: str = "workspace", scope_ref: str = "") -> Path:
        path = self.storage_root / "workspaces" / workspace_id / "files" / scope
        if scope_ref:
            path = path / self._safe_name(scope_ref)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _decode_payload(
        *,
        content_text: Optional[str] = None,
        content_base64: Optional[str] = None,
        data_url: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        if data_url:
            raw = data_url.strip()
            if raw.startswith("data:") and "," in raw:
                header, payload = raw.split(",", 1)
                mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
                return base64.b64decode(payload), mime_type
        if content_base64:
            return base64.b64decode(content_base64), "application/octet-stream"
        text = content_text or ""
        return text.encode("utf-8"), "text/plain"

    def insert_file(self, record: Dict[str, Any], content_bytes: bytes) -> Dict[str, Any]:
        payload = dict(record)
        payload["file_id"] = payload.get("file_id") or f"file_{uuid.uuid4().hex[:12]}"
        original_name = str(payload.get("original_name") or "file").strip()
        stored_name = str(payload.get("stored_name") or f"{payload['file_id']}_{self._safe_name(original_name)}")
        workspace_id = str(payload["workspace_id"])
        scope = str(payload.get("scope") or "workspace").strip().lower() or "workspace"
        scope_ref = str(payload.get("scope_ref") or "").strip()
        file_path = self.files_dir(workspace_id, scope=scope, scope_ref=scope_ref) / stored_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content_bytes)

        sha256 = hashlib.sha256(content_bytes).hexdigest()
        row = {
            "file_id": payload["file_id"],
            "workspace_id": workspace_id,
            "scope": scope,
            "scope_ref": scope_ref,
            "uploaded_by_user_id": payload.get("uploaded_by_user_id"),
            "uploaded_by_session_id": payload.get("uploaded_by_session_id"),
            "original_name": original_name,
            "stored_name": stored_name,
            "storage_path": str(file_path),
            "mime_type": str(payload.get("mime_type") or "application/octet-stream"),
            "byte_size": len(content_bytes),
            "sha256": sha256,
            "kind": str(payload.get("kind") or "generic"),
            "description": payload.get("description"),
            "created_at": payload.get("created_at") or self.utc_now(),
            "updated_at": payload.get("updated_at") or self.utc_now(),
        }

        columns = ", ".join(f'"{column}"' for column in FILE_COLUMNS)
        placeholders = ", ".join("?" for _ in FILE_COLUMNS)
        values = [row[column] for column in FILE_COLUMNS]

        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO workspace_files ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()

        fetched = self.fetch_file(row["workspace_id"], row["file_id"])
        if fetched is None:
            raise LookupError(f"File not found after insert: {row['file_id']}")
        return fetched

    def fetch_file(self, workspace_id: str, file_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM workspace_files
                WHERE workspace_id = ? AND file_id = ?
                """,
                (workspace_id, file_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_files(self, workspace_id: str, scope: Optional[str] = None, scope_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        clauses = ["workspace_id = ?"]
        params: List[Any] = [workspace_id]
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if scope_ref:
            clauses.append("scope_ref = ?")
            params.append(scope_ref)
        sql = f"""
            SELECT *
            FROM workspace_files
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC, file_id DESC
        """
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def file_bytes(self, workspace_id: str, file_id: str) -> Tuple[Dict[str, Any], bytes]:
        record = self.fetch_file(workspace_id, file_id)
        if record is None:
            raise FileNotFoundError(file_id)
        file_path = Path(record["storage_path"])
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))
        return record, file_path.read_bytes()


class WorkspaceFileService:
    def __init__(self, *, kernel, runtime_dir: Path, utc_now_fn):
        self.kernel = kernel
        self.runtime_dir = Path(runtime_dir)
        self.utc_now = utc_now_fn
        self.db_path = self.runtime_dir / "veridex.db"
        self.store = WorkspaceFileStore(self.db_path, self.runtime_dir, utc_now_fn)

    def _ensure_workspace(self, workspace_id: str) -> None:
        self.kernel.bootstrap_workspace(workspace_id)

    def upload_file(
        self,
        *,
        workspace_id: str,
        original_name: str,
        content_text: Optional[str] = None,
        content_base64: Optional[str] = None,
        data_url: Optional[str] = None,
        mime_type: Optional[str] = None,
        kind: str = "generic",
        description: Optional[str] = None,
        uploaded_by_user_id: Optional[str] = None,
        uploaded_by_session_id: Optional[str] = None,
        scope: str = "workspace",
        scope_ref: str = "",
    ) -> Dict[str, Any]:
        self._ensure_workspace(workspace_id)
        content_bytes, detected_mime = self.store._decode_payload(
            content_text=content_text,
            content_base64=content_base64,
            data_url=data_url,
        )
        final_mime = mime_type or detected_mime or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        record = self.store.insert_file(
            {
                "workspace_id": workspace_id,
                "scope": scope,
                "scope_ref": scope_ref,
                "uploaded_by_user_id": uploaded_by_user_id,
                "uploaded_by_session_id": uploaded_by_session_id,
                "original_name": original_name,
                "mime_type": final_mime,
                "kind": kind,
                "description": description,
                "created_at": self.utc_now(),
                "updated_at": self.utc_now(),
            },
            content_bytes,
        )
        record["download_url"] = f"/files/{record['file_id']}/download?workspace_id={workspace_id}&scope={record['scope']}"
        return record

    def list_files(self, workspace_id: str, scope: Optional[str] = None, scope_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_workspace(workspace_id)
        rows = self.store.list_files(workspace_id, scope=scope, scope_ref=scope_ref)
        for row in rows:
            row["download_url"] = f"/files/{row['file_id']}/download?workspace_id={workspace_id}&scope={row.get('scope') or 'workspace'}"
        return rows

    def get_file(self, workspace_id: str, file_id: str) -> Dict[str, Any]:
        self._ensure_workspace(workspace_id)
        record = self.store.fetch_file(workspace_id, file_id)
        if record is None:
            raise FileNotFoundError(file_id)
        record["download_url"] = f"/files/{record['file_id']}/download?workspace_id={workspace_id}&scope={record.get('scope') or 'workspace'}"
        return record

    def file_bytes(self, workspace_id: str, file_id: str) -> Tuple[Dict[str, Any], bytes]:
        self._ensure_workspace(workspace_id)
        return self.store.file_bytes(workspace_id, file_id)


class PrivateFileService(WorkspaceFileService):
    def __init__(self, *, kernel, runtime_dir: Path, utc_now_fn):
        self.kernel = kernel
        self.runtime_dir = Path(runtime_dir)
        self.utc_now = utc_now_fn
        self.db_path = self.runtime_dir / "private_files.db"
        self.store = WorkspaceFileStore(self.db_path, self.runtime_dir / "private_files", utc_now_fn)

    def upload_file(self, **kwargs) -> Dict[str, Any]:
        kwargs["scope"] = "private"
        kwargs["scope_ref"] = kwargs.get("scope_ref") or "private"
        record = super().upload_file(**kwargs)
        record["download_url"] = f"/private-files/{record['file_id']}/download?workspace_id={record['workspace_id']}"
        return record

    def list_files(self, workspace_id: str, scope: Optional[str] = None, scope_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = super().list_files(workspace_id, scope=scope or "private", scope_ref=scope_ref or "private")
        for row in rows:
            row["download_url"] = f"/private-files/{row['file_id']}/download?workspace_id={workspace_id}"
        return rows

    def get_file(self, workspace_id: str, file_id: str) -> Dict[str, Any]:
        record = super().get_file(workspace_id, file_id)
        record["download_url"] = f"/private-files/{record['file_id']}/download?workspace_id={workspace_id}"
        return record
