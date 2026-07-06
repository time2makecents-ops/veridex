from __future__ import annotations

from typing import Any, Dict


def pending_break_room_joke(state: Dict[str, Any], session_id: str) -> Dict[str, Any] | None:
    if not session_id:
        return None
    pending_map = state.get("pending_break_room_jokes")
    if not isinstance(pending_map, dict):
        return None
    pending = pending_map.get(session_id)
    return pending if isinstance(pending, dict) else None


def pending_room_navigation(state: Dict[str, Any]) -> Dict[str, Any] | None:
    pending = state.get("pending_room_navigation")
    return pending if isinstance(pending, dict) else None


def pending_session_rename(state: Dict[str, Any], session_id: str) -> Dict[str, Any] | None:
    if not session_id:
        return None
    pending_map = state.get("pending_session_rename_by_session")
    if not isinstance(pending_map, dict):
        return None
    pending = pending_map.get(session_id)
    return pending if isinstance(pending, dict) else None


def pending_session_list(state: Dict[str, Any], session_id: str) -> Dict[str, Any] | None:
    if not session_id:
        return None
    pending_map = state.get("pending_session_list_by_session")
    if not isinstance(pending_map, dict):
        return None
    pending = pending_map.get(session_id)
    return pending if isinstance(pending, dict) else None


def normalize_artifact_scope(*, args: Dict[str, Any], workspace_id: str, kernel: Any) -> str:
    scope = str(args.get("retrieval_scope") or args.get("scope") or "workspace").strip().lower()
    scope = scope.replace("-", "_")
    if scope in {"global", "archive", "archive_global", "all", "all_project", "all_projects"}:
        return "archive_global"

    state = kernel.get_state(workspace_id)
    active_room = str(state.get("active_room") or "").strip().lower()
    if active_room == "records_archive":
        return "archive_global"
    return "workspace"


def artifact_workspace_ids(*, workspace_id: str, kernel: Any) -> list[str]:
    idx = kernel.list_workspaces()
    workspace_ids: list[str] = []
    for row in idx.get("workspaces", []):
        candidate = str(row.get("workspace_id") or "").strip()
        if candidate and candidate not in workspace_ids:
            workspace_ids.append(candidate)
    if workspace_id and workspace_id not in workspace_ids:
        workspace_ids.insert(0, workspace_id)
    return workspace_ids


def require_artifact_workspace(*, workspace_id: str, kernel: Any) -> Dict[str, Any]:
    return kernel.get_state(workspace_id)


def artifact_summary_text(record: Dict[str, Any], action: str) -> str:
    return f"{action} artifact {record['artifact_id']} ({record.get('display_name') or record.get('title')})."


def resolve_file_workspace(*, args: Dict[str, Any], resolve_workspace_id) -> str:
    tool = "office.file_upload"
    workspace_id = str(args.get("workspace_id", "")).strip()
    session_id = str(args.get("session_id", "")).strip()
    if session_id:
        return resolve_workspace_id(tool, {"session_id": session_id, "workspace_id": workspace_id})
    if workspace_id:
        return workspace_id
    return resolve_workspace_id(tool, args)
