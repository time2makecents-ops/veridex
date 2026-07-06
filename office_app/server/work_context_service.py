from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip())
    return normalized.strip("_")[:96] or "context"


class WorkContextService:
    def __init__(self, *, store: Any, utc_now_fn: Callable[[], str]):
        self.store = store
        self.utc_now = utc_now_fn

    def _path(self, workspace_id: str) -> Path:
        return self.store.workspace_dir(workspace_id) / "work_context.json"

    def _load(self, workspace_id: str) -> Dict[str, Any]:
        obj = _read_json(self._path(workspace_id), {"contexts": []})
        if not isinstance(obj, dict):
            return {"contexts": []}
        rows = obj.get("contexts")
        if not isinstance(rows, list):
            obj["contexts"] = []
        return obj

    def _save(self, workspace_id: str, obj: Dict[str, Any]) -> None:
        _write_json(self._path(workspace_id), obj)

    @staticmethod
    def context_id_for(*, source_type: str, source_id: str) -> str:
        return f"ctx_{_slug(source_type)}_{_slug(source_id)}"

    def upsert_context(
        self,
        *,
        workspace_id: str,
        source_type: str,
        source_id: str,
        title: str,
        summary: str,
        status: str = "active",
        session_id: str = "",
        active_room: str = "",
        active_persona: str = "",
        refs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = self.utc_now()
        normalized_status = str(status or "active").strip().lower() or "active"
        if normalized_status not in {"active", "completed", "dismissed"}:
            normalized_status = "active"
        context_id = self.context_id_for(source_type=source_type, source_id=source_id)
        obj = self._load(workspace_id)
        contexts = obj["contexts"]
        existing = next((row for row in contexts if isinstance(row, dict) and row.get("context_id") == context_id), None)
        if existing is None:
            existing = {
                "context_id": context_id,
                "workspace_id": workspace_id,
                "source_type": str(source_type or "").strip(),
                "source_id": str(source_id or "").strip(),
                "created_at": now,
            }
            contexts.append(existing)
        existing.update(
            {
                "title": str(title or "").strip() or "Untitled work",
                "summary": str(summary or "").strip(),
                "status": normalized_status,
                "session_id": str(session_id or "").strip(),
                "active_room": str(active_room or "").strip(),
                "active_persona": str(active_persona or "").strip(),
                "refs": refs if isinstance(refs, dict) else {},
                "updated_at": now,
            }
        )
        self._save(workspace_id, obj)
        return dict(existing)

    def complete_context(
        self,
        *,
        workspace_id: str,
        source_type: str,
        source_id: str,
        summary: str = "",
    ) -> Optional[Dict[str, Any]]:
        context_id = self.context_id_for(source_type=source_type, source_id=source_id)
        obj = self._load(workspace_id)
        for row in obj["contexts"]:
            if not isinstance(row, dict) or row.get("context_id") != context_id:
                continue
            row["status"] = "completed"
            if summary:
                row["summary"] = str(summary).strip()
            row["updated_at"] = self.utc_now()
            self._save(workspace_id, obj)
            return dict(row)
        return None

    def complete_active_contexts(self, *, workspace_id: str, summary: str = "") -> List[Dict[str, Any]]:
        obj = self._load(workspace_id)
        now = self.utc_now()
        completed: List[Dict[str, Any]] = []
        for row in obj["contexts"]:
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "").strip().lower() != "active":
                continue
            row["status"] = "completed"
            if summary:
                row["summary"] = str(summary).strip()
            row["updated_at"] = now
            completed.append(dict(row))
        if completed:
            self._save(workspace_id, obj)
        return completed

    def complete_active_context_by_index(
        self,
        *,
        workspace_id: str,
        active_index: int,
        summary: str = "",
    ) -> Optional[Dict[str, Any]]:
        if active_index < 1:
            return None
        active_rows = self.list_contexts(workspace_id, status="active", limit=max(active_index, 10))
        if active_index > len(active_rows):
            return None
        selected_context_id = str(active_rows[active_index - 1].get("context_id") or "").strip()
        if not selected_context_id:
            return None
        obj = self._load(workspace_id)
        for row in obj["contexts"]:
            if not isinstance(row, dict) or str(row.get("context_id") or "").strip() != selected_context_id:
                continue
            row["status"] = "completed"
            if summary:
                row["summary"] = str(summary).strip()
            row["updated_at"] = self.utc_now()
            self._save(workspace_id, obj)
            return dict(row)
        return None

    def complete_context_by_id(
        self,
        *,
        workspace_id: str,
        context_id: str,
        summary: str = "",
    ) -> Optional[Dict[str, Any]]:
        normalized_context_id = str(context_id or "").strip()
        if not normalized_context_id:
            return None
        obj = self._load(workspace_id)
        for row in obj["contexts"]:
            if not isinstance(row, dict) or str(row.get("context_id") or "").strip() != normalized_context_id:
                continue
            row["status"] = "completed"
            if summary:
                row["summary"] = str(summary).strip()
            row["updated_at"] = self.utc_now()
            self._save(workspace_id, obj)
            return dict(row)
        return None

    def list_contexts(self, workspace_id: str, *, status: str = "active", limit: int = 10) -> List[Dict[str, Any]]:
        normalized_status = str(status or "active").strip().lower() or "active"
        obj = self._load(workspace_id)
        rows = [dict(row) for row in obj["contexts"] if isinstance(row, dict)]
        if normalized_status != "all":
            rows = [row for row in rows if str(row.get("status") or "").strip().lower() == normalized_status]
        rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        return rows[: max(1, int(limit or 10))]
