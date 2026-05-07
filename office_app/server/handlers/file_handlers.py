from __future__ import annotations

from typing import Any, Dict

from fastapi.responses import FileResponse

from office_app.server.artifact_request_helpers import resolve_file_workspace
from office_app.server.room_router import validate_room

from .dependencies import HandlerDeps


def build_file_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_file_upload(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = resolve_file_workspace(args=args, resolve_workspace_id=deps.resolve_workspace_id)
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
        workspace_id = resolve_file_workspace(args=args, resolve_workspace_id=deps.resolve_workspace_id)
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
        workspace_id = resolve_file_workspace(args=args, resolve_workspace_id=deps.resolve_workspace_id)
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

    def handle_room_memory_remember(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.room_memory_remember", args)
        instruction = str(args.get("instruction") or args.get("content") or "").strip()
        if not instruction:
            raise deps.error_missing_required_field("instruction")

        state = deps.kernel.get_state(workspace_id)
        room_id = str(args.get("room_id") or state.get("active_room") or "lobby").strip()
        room = validate_room(room_id)
        room_id = str(room["id"])
        room_title = str(room.get("title") or room_id)
        source_room = str(state.get("active_room") or "lobby")
        source_persona = str(state.get("active_persona") or "Receptionist")
        session_id = str(args.get("session_id") or "").strip() or None

        record = deps.archive_service.create_artifact(
            workspace_id=workspace_id,
            type="room_behavior_memory",
            title=f"{room_title} behavior memory",
            content=instruction,
            format="text/plain",
            status="active",
            created_by="user",
            metadata={
                "memory_kind": "room_behavior",
                "target_room": room_id,
                "target_room_title": room_title,
                "source_room": source_room,
                "source_persona": source_persona,
                "session_id": session_id,
            },
            source_refs=[],
        )
        ref_result = deps.receptionist_context_service.remember_room_behavior_ref(
            workspace_id=workspace_id,
            room_id=room_id,
            artifact_id=str(record["artifact_id"]),
            artifact_workspace_id=workspace_id,
            preview=instruction,
        )
        structured = {
            "workspace_id": workspace_id,
            "room_id": room_id,
            "room_title": room_title,
            "artifact": record,
            "room_behavior_memory_refs": ref_result["room_behavior_memory_refs"],
        }
        return {
            "structuredContent": structured,
            "content": [
                {
                    "type": "text",
                    "text": f"Saved behavior memory for {room_title} in Records Archive as {record['artifact_id']}.",
                }
            ],
        }

    def handle_room_memory_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.room_memory_list", args)
        state = deps.kernel.get_state(workspace_id)
        room_id = str(args.get("room_id") or state.get("active_room") or "lobby").strip()
        room = validate_room(room_id)
        room_id = str(room["id"])
        room_title = str(room.get("title") or room_id)
        refs = deps.receptionist_context_service.room_behavior_memory_refs(
            workspace_id=workspace_id,
            room_id=room_id,
        )
        items = []
        for ref in refs:
            artifact_id = str(ref.get("artifact_id") or "").strip()
            if not artifact_id:
                continue
            artifact_workspace_id = str(ref.get("workspace_id") or workspace_id).strip() or workspace_id
            try:
                artifact = deps.archive_service.get_artifact(artifact_workspace_id, artifact_id)
            except Exception:
                continue
            items.append(
                {
                    "artifact_id": artifact_id,
                    "title": artifact.get("title"),
                    "content": artifact.get("content"),
                    "description": str(artifact.get("content") or "").strip(),
                    "metadata": artifact.get("metadata"),
                    "linked_at": ref.get("linked_at"),
                }
            )
        structured = {
            "workspace_id": workspace_id,
            "room_id": room_id,
            "room_title": room_title,
            "count": len(items),
            "items": items,
        }
        lines = [f"{idx}. {item['title']} - {item['description']}" for idx, item in enumerate(items, start=1)]
        text = "\n".join(lines) if lines else f"No room behavior memory objects are saved for {room_title}."
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": text}],
        }

    def handle_room_memory_forget(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.room_memory_forget", args)
        state = deps.kernel.get_state(workspace_id)
        room_id = str(args.get("room_id") or state.get("active_room") or "lobby").strip()
        if room_id in {"*", "all"}:
            room_title = "all rooms"
        else:
            room = validate_room(room_id)
            room_id = str(room["id"])
            room_title = str(room.get("title") or room_id)
        match_text = str(args.get("match_text") or "").strip()
        artifact_id = str(args.get("artifact_id") or "").strip() or None
        result = deps.receptionist_context_service.forget_room_behavior_refs(
            workspace_id=workspace_id,
            room_id=room_id,
            artifact_id=artifact_id,
            match_text=match_text,
        )
        structured = {
            **result,
            "room_title": room_title,
        }
        return {
            "structuredContent": structured,
            "content": [
                {
                    "type": "text",
                    "text": f"Removed {result['removed_count']} behavior memory reference(s) for {structured['room_title']}.",
                }
            ],
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
        "office.room_memory_remember": handle_room_memory_remember,
        "office.room_memory_list": handle_room_memory_list,
        "office.room_memory_forget": handle_room_memory_forget,
        "__file_download_response__": handle_file_download_response,
    }
