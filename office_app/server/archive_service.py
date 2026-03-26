from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException


class ArchiveService:
    def __init__(self, workspaces_dir: Path, utc_now_fn):
        self.workspaces_dir = Path(workspaces_dir)
        self.utc_now = utc_now_fn

    def workspace_dir(self, workspace_id: str) -> Path:
        path = self.workspaces_dir / workspace_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifacts_dir(self, workspace_id: str) -> Path:
        path = self.workspace_dir(workspace_id) / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def index_path(self, workspace_id: str) -> Path:
        return self.artifacts_dir(workspace_id) / "index.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def _load_index(self, workspace_id: str) -> List[Dict[str, Any]]:
        data = self._read_json(self.index_path(workspace_id), [])
        return data if isinstance(data, list) else []

    def _save_index(self, workspace_id: str, rows: List[Dict[str, Any]]) -> None:
        self._write_json(self.index_path(workspace_id), rows)

    def _slug(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "artifact"

    def store_text_artifact(
        self,
        *,
        workspace_id: str,
        name: str,
        content: str,
        artifact_type: str = "document",
        source_room: str = "records_archive",
        source_persona: str = "Archivist",
        tags: List[str] | None = None,
    ) -> Dict[str, Any]:
        artifact_id = f"art_{uuid.uuid4().hex[:8]}"
        slug = self._slug(name)
        stored_filename = f"{artifact_id}_{slug}.txt"
        file_path = self.artifacts_dir(workspace_id) / stored_filename
        file_path.write_text(content, encoding="utf-8")

        record = {
            "artifact_id": artifact_id,
            "workspace_id": workspace_id,
            "display_name": name,
            "stored_filename": stored_filename,
            "artifact_type": artifact_type,
            "source_room": source_room,
            "source_persona": source_persona,
            "created_at": self.utc_now(),
            "tags": tags or [],
            "status": "stored",
            "content_preview": content[:2000],
        }

        rows = self._load_index(workspace_id)
        rows.append(record)
        self._save_index(workspace_id, rows)
        return record

    def list_artifacts(self, workspace_id: str) -> List[Dict[str, Any]]:
        return list(self._load_index(workspace_id))

    def get_artifact(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        rows = self._load_index(workspace_id)
        for row in rows:
            if row.get("artifact_id") == artifact_id:
                file_path = self.artifacts_dir(workspace_id) / str(row.get("stored_filename"))
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    obj = dict(row)
                    obj["content"] = content
                    obj["content_preview"] = content[:2000]
                    return obj
                raise HTTPException(status_code=404, detail=f"Artifact file missing for {artifact_id}")
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")