from __future__ import annotations

from datetime import datetime, timezone
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from fastapi import HTTPException

from office_app.server.artifact_store import ArtifactStore
from office_app.server.errors import error_missing_required_field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ArtifactService:
    def __init__(
        self,
        runtime_dir: Path = Path("office_app/runtime"),
        utc_now_fn: Callable[[], str] = utc_now_iso,
    ):
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runtime_dir / "veridex.db"
        self.utc_now = utc_now_fn
        self.store = ArtifactStore(self.db_path)

    @staticmethod
    def _normalize_text(value: Any, fallback: str = "") -> str:
        text = str(value if value is not None else fallback)
        return text.strip() if text.strip() or fallback == "" else fallback

    @staticmethod
    def _merge_metadata(existing: Any, incoming: Any) -> Any:
        if incoming is None:
            return existing
        if isinstance(existing, dict) and isinstance(incoming, dict):
            merged = dict(existing)
            merged.update(incoming)
            return merged
        return incoming

    @staticmethod
    def _merge_source_refs(existing: Any, incoming: Any) -> Any:
        if incoming is None:
            return existing
        if not isinstance(existing, list):
            existing = []
        if not isinstance(incoming, list):
            incoming = [incoming]
        merged = list(existing)
        for item in incoming:
            if item not in merged:
                merged.append(item)
        return merged

    @staticmethod
    def _decorate(record: Dict[str, Any]) -> Dict[str, Any]:
        decorated = dict(record)
        decorated.setdefault("display_name", decorated.get("title"))
        decorated.setdefault("artifact_type", decorated.get("type"))
        content = str(decorated.get("content", ""))
        decorated.setdefault("content_preview", content[:2000])
        return decorated

    def _require_record(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        record = self.store.fetch_record(workspace_id, artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
        return record

    def create_artifact(
        self,
        *,
        workspace_id: str,
        type: str,
        title: str,
        content: Any = "",
        format: str = "text/plain",
        status: str = "active",
        created_by: str = "user",
        metadata: Any = None,
        source_refs: Any = None,
    ) -> Dict[str, Any]:
        title_text = self._normalize_text(title)
        type_text = self._normalize_text(type)
        if not title_text:
            raise error_missing_required_field("title")
        if not type_text:
            raise error_missing_required_field("type")

        artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        now = self.utc_now()
        status_text = self._normalize_text(status, "active") or "active"
        record = {
            "artifact_id": artifact_id,
            "workspace_id": workspace_id,
            "type": type_text,
            "title": title_text,
            "content": str(content or ""),
            "format": self._normalize_text(format, "text/plain") or "text/plain",
            "status": status_text,
            "created_by": self._normalize_text(created_by, "user") or "user",
            "created_at": now,
            "updated_at": now,
            "metadata": metadata if metadata is not None else {},
            "version": 1,
            "source_refs": source_refs if source_refs is not None else [],
            "archived": status_text.lower() == "archived",
        }
        created = self.store.insert_record(record)
        return self._decorate(created)

    def get_artifact(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        record = self._require_record(workspace_id, artifact_id)
        return self._decorate(record)

    def list_artifacts(self, workspace_id: str, *, include_archived: bool = False) -> List[Dict[str, Any]]:
        rows = self.store.list_records(workspace_id, include_archived=include_archived)
        return [self._decorate(row) for row in rows]

    def list_artifacts_across_workspaces(
        self,
        workspace_ids: Iterable[str],
        *,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for workspace_id in workspace_ids:
            for row in self.store.list_records(workspace_id, include_archived=include_archived):
                key = f"{row['workspace_id']}::{row['artifact_id']}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append(self._decorate(row))
        rows.sort(key=lambda row: (row.get("updated_at") or row.get("created_at") or "", row.get("artifact_id") or ""), reverse=True)
        return rows

    def get_artifact_across_workspaces(self, workspace_ids: Iterable[str], artifact_id: str) -> Dict[str, Any]:
        for workspace_id in workspace_ids:
            record = self.store.fetch_record(workspace_id, artifact_id)
            if record is not None:
                return self._decorate(record)
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")

    def update_artifact(
        self,
        *,
        workspace_id: str,
        artifact_id: str,
        title: Optional[str] = None,
        content: Any = None,
        format: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Any = None,
        source_refs: Any = None,
    ) -> Dict[str, Any]:
        current = self._require_record(workspace_id, artifact_id)
        if current.get("archived"):
            raise HTTPException(status_code=409, detail=f"Artifact is archived: {artifact_id}")

        updates: Dict[str, Any] = {"updated_at": self.utc_now(), "version": int(current["version"]) + 1}

        if title is not None:
            title_text = self._normalize_text(title)
            if not title_text:
                raise error_missing_required_field("title")
            updates["title"] = title_text
        if content is not None:
            updates["content"] = str(content)
        if format is not None:
            updates["format"] = self._normalize_text(format, current.get("format", "text/plain")) or current.get("format", "text/plain")
        if status is not None:
            status_text = self._normalize_text(status, current.get("status", "active")) or current.get("status", "active")
            updates["status"] = status_text
            if status_text.lower() == "archived":
                updates["archived"] = True
        if metadata is not None:
            updates["metadata"] = self._merge_metadata(current.get("metadata", {}), metadata)
        if source_refs is not None:
            updates["source_refs"] = source_refs

        updated = self.store.update_record(workspace_id, artifact_id, updates)
        return self._decorate(updated)

    def append_to_artifact(
        self,
        *,
        workspace_id: str,
        artifact_id: str,
        content: Any,
        separator: str = "\n",
        metadata: Any = None,
        source_refs: Any = None,
    ) -> Dict[str, Any]:
        current = self._require_record(workspace_id, artifact_id)
        if current.get("archived"):
            raise HTTPException(status_code=409, detail=f"Artifact is archived: {artifact_id}")

        current_content = str(current.get("content", ""))
        incoming = str(content or "")
        next_content = incoming if not current_content else f"{current_content}{separator}{incoming}"

        updates: Dict[str, Any] = {
            "content": next_content,
            "updated_at": self.utc_now(),
            "version": int(current["version"]) + 1,
        }
        if metadata is not None:
            updates["metadata"] = self._merge_metadata(current.get("metadata", {}), metadata)
        if source_refs is not None:
            updates["source_refs"] = self._merge_source_refs(current.get("source_refs", []), source_refs)

        updated = self.store.update_record(workspace_id, artifact_id, updates)
        return self._decorate(updated)

    def archive_artifact(self, *, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        current = self._require_record(workspace_id, artifact_id)
        if current.get("archived"):
            return self._decorate(current)

        updated = self.store.update_record(
            workspace_id,
            artifact_id,
            {
                "status": "archived",
                "archived": True,
                "updated_at": self.utc_now(),
                "version": int(current["version"]) + 1,
            },
        )
        return self._decorate(updated)

    def delete_artifact(self, *, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        current = self._require_record(workspace_id, artifact_id)
        deleted = self.store.delete_record(workspace_id, artifact_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
        return self._decorate(deleted)

    def store_text_artifact(
        self,
        *,
        workspace_id: str,
        name: str,
        content: str,
        artifact_type: str = "document",
        source_room: str = "records_archive",
        source_persona: str = "Archivist",
        tags: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "source_room": source_room,
            "source_persona": source_persona,
        }
        if tags is not None:
            metadata["tags"] = tags
        record = self.create_artifact(
            workspace_id=workspace_id,
            type=artifact_type,
            title=name,
            content=content,
            format="text/plain",
            status="active",
            created_by=created_by,
            metadata=metadata,
            source_refs=[],
        )
        return record

    def artifacts_dir(self, workspace_id: str) -> Path:
        path = self.runtime_dir / "artifacts" / workspace_id
        path.mkdir(parents=True, exist_ok=True)
        return path
