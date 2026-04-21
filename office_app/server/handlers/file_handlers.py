from __future__ import annotations

from typing import Any, Dict

from fastapi.responses import FileResponse

from .dependencies import HandlerDeps


def build_file_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def _resolve_file_workspace(args: Dict[str, Any]) -> str:
        tool = "office.file_upload"
        workspace_id = str(args.get("workspace_id", "")).strip()
        session_id = str(args.get("session_id", "")).strip()
        if session_id:
            return deps.resolve_workspace_id(tool, {"session_id": session_id, "workspace_id": workspace_id})
        if workspace_id:
            return workspace_id
        return deps.resolve_workspace_id(tool, args)

    def handle_file_upload(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _resolve_file_workspace(args)
        original_name = str(args.get("name") or args.get("filename") or args.get("file_name") or "").strip()
        if not original_name:
            raise deps.error_missing_required_field("name")
        scope = str(args.get("scope") or "workspace").strip().lower() or "workspace"
        scope_ref = str(args.get("scope_ref") or "").strip()
        service = deps.private_file_service if scope == "private" else deps.workspace_file_service
        record = service.upload_file(
            workspace_id=workspace_id,
            original_name=original_name,
            content_text=args.get("content_text"),
            content_base64=args.get("content_base64"),
            data_url=args.get("data_url"),
            mime_type=str(args.get("mime_type") or "").strip() or None,
            kind=str(args.get("kind") or "generic").strip() or "generic",
            scope=scope,
            scope_ref=scope_ref or scope,
            description=args.get("description"),
            uploaded_by_user_id=str(args.get("uploaded_by_user_id") or "").strip() or None,
            uploaded_by_session_id=str(args.get("session_id") or "").strip() or None,
        )
        return {
            **record,
            "structuredContent": record,
            "content": [{"type": "text", "text": f"Uploaded file {record['original_name']} as {record['file_id']}."}],
        }

    def handle_file_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _resolve_file_workspace(args)
        scope = str(args.get("scope") or "").strip().lower() or None
        scope_ref = str(args.get("scope_ref") or "").strip() or None
        service = deps.private_file_service if scope == "private" else deps.workspace_file_service
        rows = service.list_files(workspace_id, scope=scope, scope_ref=scope_ref)
        return {
            "workspace_id": workspace_id,
            "count": len(rows),
            "files": rows,
            "structuredContent": {
                "workspace_id": workspace_id,
                "count": len(rows),
                "files": rows,
            },
            "content": [{"type": "text", "text": f"Found {len(rows)} file(s)."}],
        }

    def handle_file_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _resolve_file_workspace(args)
        file_id = str(args.get("file_id") or "").strip()
        if not file_id:
            raise deps.error_missing_required_field("file_id")
        scope = str(args.get("scope") or "").strip().lower() or "workspace"
        service = deps.private_file_service if scope == "private" else deps.workspace_file_service
        record = service.get_file(workspace_id, file_id)
        return {
            **record,
            "structuredContent": record,
            "content": [{"type": "text", "text": f"File {record['file_id']} - {record['original_name']}."}],
        }

    def handle_file_download_response(workspace_id: str, file_id: str, scope: str = "workspace"):
        service = deps.private_file_service if scope == "private" else deps.workspace_file_service
        record = service.get_file(workspace_id, file_id)
        return FileResponse(
            path=record["storage_path"],
            filename=record["original_name"],
            media_type=record["mime_type"] or "application/octet-stream",
        )

    def handle_receptionist_context_get(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.receptionist_context_get", args)
        context = deps.receptionist_context_service.get_context(workspace_id)
        return {
            "structuredContent": context,
            "content": [{"type": "text", "text": f"Loaded receptionist context for {workspace_id}."}],
        }

    def handle_private_file_upload(args: Dict[str, Any]) -> Dict[str, Any]:
        args = dict(args)
        args["scope"] = "private"
        return handle_file_upload(args)

    def handle_private_file_list(args: Dict[str, Any]) -> Dict[str, Any]:
        args = dict(args)
        args["scope"] = "private"
        return handle_file_list(args)

    def handle_private_file_get(args: Dict[str, Any]) -> Dict[str, Any]:
        args = dict(args)
        args["scope"] = "private"
        return handle_file_get(args)

    def handle_receptionist_context_update(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.receptionist_context_update", args)
        updates = {
            "room_directory": args.get("room_directory"),
            "persona_directory": args.get("persona_directory"),
            "receptionist_script": args.get("receptionist_script"),
            "policy_summary": args.get("policy_summary"),
            "known_user_profile": args.get("known_user_profile"),
            "session_summary_text": args.get("session_summary_text"),
            "recent_turns": args.get("recent_turns"),
            "current_prompt_state": args.get("current_prompt_state"),
        }
        context = deps.receptionist_context_service.update_context(workspace_id, updates)
        return {
            "structuredContent": context,
            "content": [{"type": "text", "text": f"Updated receptionist context for {workspace_id}."}],
        }

    return {
        "office.file_upload": handle_file_upload,
        "office.file_list": handle_file_list,
        "office.file_get": handle_file_get,
        "office.file_download": handle_file_get,
        "office.private_file_upload": handle_private_file_upload,
        "office.private_file_list": handle_private_file_list,
        "office.private_file_get": handle_private_file_get,
        "office.receptionist_context_get": handle_receptionist_context_get,
        "office.receptionist_context_update": handle_receptionist_context_update,
        "__file_download_response__": handle_file_download_response,
    }
