from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException

from office_app.server.artifact_request_helpers import (
    artifact_summary_text,
    artifact_workspace_ids,
    normalize_artifact_scope,
    require_artifact_workspace,
)

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
    def _artifact_list_text(rows: list[Dict[str, Any]], retrieval_scope: str) -> str:
        scope_text = "all workspaces" if retrieval_scope == "archive_global" else "this workspace"
        lines = [f"Found {len(rows)} artifact(s) ({scope_text})."]
        for index, row in enumerate(rows[:10], start=1):
            title = str(row.get("display_name") or row.get("title") or row.get("artifact_id") or f"Artifact {index}").strip()
            artifact_id = str(row.get("artifact_id") or "").strip()
            artifact_type = str(row.get("artifact_type") or row.get("type") or "").strip()
            preview = str(row.get("content_preview") or row.get("content") or "").strip()
            preview = " ".join(preview.split())
            if len(preview) > 120:
                preview = preview[:117].rstrip() + "..."
            descriptor = title
            if artifact_type and artifact_type.lower() != title.lower():
                descriptor = f"{artifact_type}: {descriptor}"
            if artifact_id and artifact_id != title:
                descriptor = f"{descriptor} ({artifact_id})"
            if preview:
                descriptor = f"{descriptor} - {preview}"
            lines.append(f"{index}. {descriptor}")
        return "\n".join(lines)

    def handle_artifact_create(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)

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
            "content": [{"type": "text", "text": artifact_summary_text(record, "Created")}],
        }

    def handle_artifact_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        retrieval_scope = normalize_artifact_scope(args=args, workspace_id=workspace_id, kernel=deps.kernel)
        if retrieval_scope == "archive_global":
            obj = deps.archive_service.get_artifact_across_workspaces(
                artifact_workspace_ids(workspace_id=workspace_id, kernel=deps.kernel),
                artifact_id,
            )
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
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
        include_archived = _parse_bool(args.get("include_archived"), False)
        retrieval_scope = normalize_artifact_scope(args=args, workspace_id=workspace_id, kernel=deps.kernel)
        if retrieval_scope == "archive_global":
            rows = deps.archive_service.list_artifacts_across_workspaces(
                artifact_workspace_ids(workspace_id=workspace_id, kernel=deps.kernel),
                include_archived=True,
            )
        else:
            rows = deps.archive_service.list_artifacts(workspace_id, include_archived=include_archived)
        for row in rows:
            preview = str(row.get("content_preview") or row.get("content") or "").strip()
            if preview and not row.get("content_preview"):
                row["content_preview"] = preview
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "count": len(rows),
                "retrieval_scope": retrieval_scope,
                "include_archived": include_archived,
                "artifacts": rows,
            },
            "content": [{"type": "text", "text": _artifact_list_text(rows, retrieval_scope)}],
        }

    def handle_artifact_update(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
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
            "content": [{"type": "text", "text": artifact_summary_text(record, "Updated")}],
        }

    def handle_artifact_append(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
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
            "content": [{"type": "text", "text": artifact_summary_text(record, "Appended to")}],
        }

    def handle_artifact_archive(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        record = deps.archive_service.archive_artifact(workspace_id=workspace_id, artifact_id=artifact_id)
        return {
            "structuredContent": record,
            "content": [{"type": "text", "text": artifact_summary_text(record, "Archived")}],
        }

    def handle_artifact_delete(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        record = deps.archive_service.delete_artifact(workspace_id=workspace_id, artifact_id=artifact_id)
        metadata = record.get("metadata") if isinstance(record, dict) else {}
        if isinstance(metadata, dict):
            memory_kind = str(metadata.get("memory_kind") or "").strip().lower()
            target_room = str(metadata.get("target_room") or "").strip()
            if memory_kind in {"room_behavior", "persona_behavior"} and target_room:
                try:
                    if memory_kind == "persona_behavior":
                        deps.receptionist_context_service.forget_persona_behavior_refs(
                            workspace_id=workspace_id,
                            room_id=target_room,
                            artifact_id=artifact_id,
                        )
                    else:
                        deps.receptionist_context_service.forget_room_behavior_refs(
                            workspace_id=workspace_id,
                            room_id=target_room,
                            artifact_id=artifact_id,
                        )
                except Exception:
                    pass

        response_text = f"Deleted artifact {record.get('display_name') or record.get('title')} ({artifact_id})."
        return {
            "structuredContent": {
                **record,
                "deleted": True,
                "workspace_id": workspace_id,
            },
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_archive_store_text(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)

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
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
        retrieval_scope = normalize_artifact_scope(args=args, workspace_id=workspace_id, kernel=deps.kernel)
        if retrieval_scope == "archive_global":
            rows = deps.archive_service.list_artifacts_across_workspaces(
                artifact_workspace_ids(workspace_id=workspace_id, kernel=deps.kernel),
                include_archived=True,
            )
        else:
            rows = deps.archive_service.list_artifacts(workspace_id, include_archived=True)
        for row in rows:
            preview = str(row.get("content_preview") or row.get("content") or "").strip()
            if preview and not row.get("content_preview"):
                row["content_preview"] = preview
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "count": len(rows),
                "retrieval_scope": retrieval_scope,
                "artifacts": rows,
            },
            "content": [{"type": "text", "text": _artifact_list_text(rows, retrieval_scope)}],
        }

    def handle_archive_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        require_artifact_workspace(workspace_id=workspace_id, kernel=deps.kernel)
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")

        retrieval_scope = normalize_artifact_scope(args=args, workspace_id=workspace_id, kernel=deps.kernel)
        if retrieval_scope == "archive_global":
            obj = deps.archive_service.get_artifact_across_workspaces(
                artifact_workspace_ids(workspace_id=workspace_id, kernel=deps.kernel),
                artifact_id,
            )
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
        retrieval_scope = normalize_artifact_scope(args=args, workspace_id=workspace_id, kernel=deps.kernel)
        if retrieval_scope == "archive_global":
            rows = deps.archive_service.list_artifacts_across_workspaces(
                artifact_workspace_ids(workspace_id=workspace_id, kernel=deps.kernel),
                include_archived=True,
            )
        else:
            rows = deps.archive_service.list_artifacts(workspace_id, include_archived=True)
        for row in rows:
            preview = str(row.get("content_preview") or row.get("content") or "").strip()
            if preview and not row.get("content_preview"):
                row["content_preview"] = preview
        return deps.nancy_service.artifacts_list_response(workspace_id, retrieval_scope=retrieval_scope)

    def handle_nancy_artifact_open(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        artifact_id = str(args.get("artifact_id", "")).strip()
        if not artifact_id:
            raise deps.error_missing_required_field("artifact_id")
        retrieval_scope = normalize_artifact_scope(args=args, workspace_id=workspace_id, kernel=deps.kernel)
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
        "office.artifact_delete": handle_artifact_delete,
        "office.archive_store_text": handle_archive_store_text,
        "office.archive_list": handle_archive_list,
        "office.archive_get": handle_archive_get,
        "office.nancy_artifacts_list": handle_nancy_artifacts_list,
        "office.nancy_artifact_open": handle_nancy_artifact_open,
        "office.nancy_workspace_briefing": handle_nancy_workspace_briefing,
    }
