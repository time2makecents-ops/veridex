from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException

from .dependencies import HandlerDeps


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def build_artifact_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def _normalize_artifact_scope(args: Dict[str, Any], workspace_id: str) -> str:
        scope = str(args.get("retrieval_scope") or args.get("scope") or "workspace").strip().lower()
        scope = scope.replace("-", "_")
        if scope in {"global", "archive", "archive_global", "all", "all_project", "all_projects"}:
            return "archive_global"

        state = deps.kernel.get_state(workspace_id)
        active_room = str(state.get("active_room") or "").strip().lower()
        if active_room == "records_archive":
            return "archive_global"
        return "workspace"

    def _artifact_workspace_ids(workspace_id: str) -> list[str]:
        idx = deps.kernel.list_workspaces()
        workspace_ids: list[str] = []
        for row in idx.get("workspaces", []):
            candidate = str(row.get("workspace_id") or "").strip()
            if candidate and candidate not in workspace_ids:
                workspace_ids.append(candidate)
        if workspace_id and workspace_id not in workspace_ids:
            workspace_ids.insert(0, workspace_id)
        return workspace_ids

    def _require_artifact_workspace(workspace_id: str) -> Dict[str, Any]:
        return deps.kernel.get_state(workspace_id)

    def _artifact_summary_text(record: Dict[str, Any], action: str) -> str:
        return f"{action} artifact {record['artifact_id']} ({record.get('display_name') or record.get('title')})."

    def handle_artifact_create(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)

        artifact_type = str(args.get("type") or args.get("artifact_type") or "").strip()
        title = str(args.get("title") or "").strip()
        content = str(args.get("content") or "")
        format_value = str(args.get("format") or "text/plain").strip() or "text/plain"
        status = str(args.get("status") or "active").strip() or "active"
        created_by = str(args.get("created_by") or "user").strip() or "user"
        metadata = args.get("metadata")
        source_refs = args.get("source_refs")

        record = deps.archive_service.create_artifact(
            workspace_id=workspace_id,
            type=artifact_type,
            title=title,
            content=content,
            format=format_value,
            status=status,
            created_by=created_by,
            metadata=metadata,
            source_refs=source_refs,
        )
        return {
            "structuredContent": record,
            "content": [{"type": "text", "text": _artifact_summary_text(record, "Created")}],
        }

    def handle_artifact_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        retrieval_scope = _normalize_artifact_scope(args, workspace_id)
        if retrieval_scope == "archive_global":
            obj = deps.archive_service.get_artifact_across_workspaces(_artifact_workspace_ids(workspace_id), artifact_id)
        else:
            obj = deps.archive_service.get_artifact(workspace_id, artifact_id)
        preview = obj.get("content_preview", "")
        return {
            "structuredContent": {
                **obj,
                "retrieval_scope": retrieval_scope,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Artifact {obj['artifact_id']} - {obj.get('display_name') or obj.get('title')}\n"
                        f"Workspace: {obj.get('workspace_id')}\n\n{preview}"
                    ),
                }
            ],
        }

    def handle_artifact_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        include_archived = _parse_bool(args.get("include_archived"), False)
        retrieval_scope = _normalize_artifact_scope(args, workspace_id)
        if retrieval_scope == "archive_global":
            rows = deps.archive_service.list_artifacts_across_workspaces(
                _artifact_workspace_ids(workspace_id),
                include_archived=True,
            )
        else:
            rows = deps.archive_service.list_artifacts(workspace_id, include_archived=include_archived)
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "count": len(rows),
                "retrieval_scope": retrieval_scope,
                "include_archived": include_archived,
                "artifacts": rows,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Found {len(rows)} artifact(s) "
                        f"({'all workspaces' if retrieval_scope == 'archive_global' else 'this workspace'})."
                    ),
                }
            ],
        }

    def handle_artifact_update(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        updated_fields = {
            "title": args.get("title"),
            "content": args.get("content"),
            "format": args.get("format"),
            "status": args.get("status"),
            "metadata": args.get("metadata"),
            "source_refs": args.get("source_refs"),
        }
        if all(value is None for value in updated_fields.values()):
            raise HTTPException(status_code=400, detail="Provide at least one field to update.")

        record = deps.archive_service.update_artifact(workspace_id=workspace_id, artifact_id=artifact_id, **updated_fields)
        return {
            "structuredContent": record,
            "content": [{"type": "text", "text": _artifact_summary_text(record, "Updated")}],
        }

    def handle_artifact_append(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        content = args.get("content")
        if content is None:
            content = args.get("append_text")
        if content is None:
            raise deps.error_missing_required_field("content")

        separator_value = args.get("separator")
        separator = "\n" if separator_value in (None, "") else str(separator_value)
        record = deps.archive_service.append_to_artifact(
            workspace_id=workspace_id,
            artifact_id=artifact_id,
            content=content,
            separator=separator,
            metadata=args.get("metadata"),
            source_refs=args.get("source_refs"),
        )
        return {
            "structuredContent": record,
            "content": [{"type": "text", "text": _artifact_summary_text(record, "Appended to")}],
        }

    def handle_artifact_archive(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        record = deps.archive_service.archive_artifact(workspace_id=workspace_id, artifact_id=artifact_id)
        return {
            "structuredContent": record,
            "content": [{"type": "text", "text": _artifact_summary_text(record, "Archived")}],
        }

    def handle_archive_store_text(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)

        name = str(args.get("name", "")).strip()
        if not name:
            raise deps.error_missing_required_field("name")

        content = str(args.get("content", ""))
        artifact_type = str(args.get("artifact_type", "document")).strip() or "document"

        state = deps.kernel.get_state(workspace_id)
        source_room = str(args.get("source_room") or state.get("active_room", "lobby"))
        source_persona = str(args.get("source_persona") or state.get("active_persona", "Receptionist"))

        record = deps.archive_service.store_text_artifact(
            workspace_id=workspace_id,
            name=name,
            content=content,
            artifact_type=artifact_type,
            source_room=source_room,
            source_persona=source_persona,
        )

        deps.append_incident(
            severity="LOW",
            clazz="ARCHIVE_STORE",
            rule_or_gate="Records Archive",
            command="office.archive_store_text",
            input_ref=json.dumps({"workspace_id": workspace_id, "name": name}),
            output_ref=record["artifact_id"],
            evidence_path=str(deps.archive_service.db_path),
            notes=f"Stored artifact {record['artifact_id']}.",
            state_sha256=deps.stable_state_sha(state),
        )

        try:
            deps.store.append_transcript(
                workspace_id,
                "system",
                state.get("active_room", "records_archive"),
                f"Artifact stored: {record.get('display_name') or record.get('title')} ({record['artifact_id']})",
            )
        except Exception:
            pass

        return {
            "structuredContent": record,
            "content": [{"type": "text", "text": f"Records Archive stored {record.get('display_name') or record.get('title')} as {record['artifact_id']}."}],
        }

    def handle_archive_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        retrieval_scope = _normalize_artifact_scope(args, workspace_id)
        if retrieval_scope == "archive_global":
            rows = deps.archive_service.list_artifacts_across_workspaces(_artifact_workspace_ids(workspace_id), include_archived=True)
        else:
            rows = deps.archive_service.list_artifacts(workspace_id, include_archived=True)
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "count": len(rows),
                "retrieval_scope": retrieval_scope,
                "artifacts": rows,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Found {len(rows)} artifact(s) "
                        f"({'all workspaces' if retrieval_scope == 'archive_global' else 'this workspace'})."
                    ),
                }
            ],
        }

    def handle_archive_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        _require_artifact_workspace(workspace_id)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        retrieval_scope = _normalize_artifact_scope(args, workspace_id)
        if retrieval_scope == "archive_global":
            obj = deps.archive_service.get_artifact_across_workspaces(_artifact_workspace_ids(workspace_id), artifact_id)
        else:
            obj = deps.archive_service.get_artifact(workspace_id, artifact_id)
        preview = obj.get("content_preview", "")
        return {
            "structuredContent": {
                **obj,
                "retrieval_scope": retrieval_scope,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Artifact {obj['artifact_id']} - {obj['display_name']}\n"
                        f"Workspace: {obj.get('workspace_id')}\n\n{preview}"
                    ),
                }
            ],
        }

    def handle_nancy_artifacts_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        retrieval_scope = _normalize_artifact_scope(args, workspace_id)
        return deps.nancy_service.artifacts_list_response(workspace_id, retrieval_scope=retrieval_scope)

    def handle_nancy_artifact_open(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")
        retrieval_scope = _normalize_artifact_scope(args, workspace_id)
        return deps.nancy_service.artifact_open_response(workspace_id, artifact_id, retrieval_scope=retrieval_scope)

    def handle_nancy_workspace_briefing(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        return deps.nancy_service.workspace_briefing_response(workspace_id)

    return {
        "office.artifact_create": handle_artifact_create,
        "office.artifact_get": handle_artifact_get,
        "office.artifact_list": handle_artifact_list,
        "office.artifact_update": handle_artifact_update,
        "office.artifact_append": handle_artifact_append,
        "office.artifact_archive": handle_artifact_archive,
        "office.archive_store_text": handle_archive_store_text,
        "office.archive_list": handle_archive_list,
        "office.archive_get": handle_archive_get,
        "office.nancy_artifacts_list": handle_nancy_artifacts_list,
        "office.nancy_artifact_open": handle_nancy_artifact_open,
        "office.nancy_workspace_briefing": handle_nancy_workspace_briefing,
    }
