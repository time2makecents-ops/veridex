from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from office_app.server.model_router import ModelRoutingError
from office_app.server.ocr_service import OcrServiceError
from office_app.server.search_service import SearchServiceError

from .dependencies import HandlerDeps


def build_ai_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def _resolve_ocr_file_record(
        *,
        workspace_id: str,
        file_id: str,
        file_name: str,
        scope: str,
        session_id: Optional[str],
    ) -> Tuple[Dict[str, Any], bytes]:
        if file_id:
            service = deps.private_file_service if scope == "private" else deps.workspace_file_service
            return service.file_bytes(workspace_id, file_id)

        normalized_name = file_name.strip().lower()
        if not normalized_name:
            raise deps.error_missing_required_field("file_id")

        state = deps.kernel.get_state(workspace_id)
        active_room = str(state.get("active_room") or "").strip()

        def _list_scope(service: Any, scope_name: Optional[str], scope_ref: Optional[str]) -> List[Dict[str, Any]]:
            if scope_name == "private" and not scope_ref:
                rows = service.store.list_files(workspace_id)
                return [row for row in rows if str(row.get("scope") or "").strip().lower() == "private"]
            return service.list_files(workspace_id, scope=scope_name, scope_ref=scope_ref)

        search_plan: List[Tuple[Any, Optional[str], Optional[str]]] = []
        explicit_scope = scope if scope and scope != "workspace" else ""
        if explicit_scope:
            if explicit_scope == "room":
                search_plan.append((deps.workspace_file_service, "room", active_room or None))
            elif explicit_scope == "session":
                search_plan.append((deps.workspace_file_service, "session", session_id or None))
            elif explicit_scope == "public":
                search_plan.append((deps.workspace_file_service, "public", "public"))
            elif explicit_scope == "private":
                search_plan.append((deps.private_file_service, "private", None))
            else:
                search_plan.append((deps.workspace_file_service, explicit_scope, None))
        else:
            if active_room:
                search_plan.append((deps.workspace_file_service, "room", active_room))
            if session_id:
                search_plan.append((deps.workspace_file_service, "session", session_id))
            search_plan.extend(
                [
                    (deps.workspace_file_service, "public", "public"),
                    (deps.workspace_file_service, "workspace", None),
                    (deps.private_file_service, "private", None),
                ]
            )

        seen_specs = set()
        for service, scope_name, scope_ref in search_plan:
            spec = (id(service), scope_name or "", scope_ref or "")
            if spec in seen_specs:
                continue
            seen_specs.add(spec)
            rows = _list_scope(service, scope_name, scope_ref)
            for row in rows:
                if str(row.get("original_name") or "").strip().lower() == normalized_name:
                    return service.file_bytes(workspace_id, str(row["file_id"]))
        raise FileNotFoundError(file_name)

    def handle_ai_generate(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = str(args.get("workspace_id", "")).strip()
        if not workspace_id:
            raise deps.error_missing_required_field("workspace_id")

        try:
            state = deps.kernel.get_state(workspace_id)
        except HTTPException:
            deps.kernel.bootstrap_workspace(workspace_id)
            state = deps.kernel.get_state(workspace_id)

        user_prompt = str(args.get("user_prompt") or args.get("request") or args.get("text") or "").strip()
        if not user_prompt:
            raise deps.error_missing_required_field("user_prompt")

        system_prompt = str(args.get("system_prompt") or "").strip()
        if not system_prompt:
            system_prompt = (
                f"You are Veridex. The active workspace is {workspace_id}. "
                f"The active room is {state.get('active_room', 'lobby')}. "
                f"The active persona is {state.get('active_persona', 'Receptionist')}. "
                "If the user asks about uploading or downloading files or images, answer with the Veridex file workflow and do not redirect them to IT unless they explicitly ask for troubleshooting. "
                "Never expose raw JSON, internal tool names, hidden schemas, or backend metadata in your response. "
                "Use recent turns only when the user is clearly asking a follow-up, using pronouns, or referring to a prior topic. For broad help or capability questions like 'what can you help me with here?', answer from the active room and persona instead of continuing the previous topic. Do not ask for details already present in recent context. "
                "Do not claim you are searching, processing, working in the background, or that you will send results later. You can only answer with information available in this response. If a tool or missing detail is needed, say so directly. "
                "Respond clearly, concisely, and stay within Veridex governance."
            )

        context = args.get("context")
        if not isinstance(context, dict):
            context = {
                "workspace_id": workspace_id,
                "active_room": state.get("active_room", "lobby"),
                "active_persona": state.get("active_persona", "Receptionist"),
            }
        receptionist_context = deps.receptionist_context_service.build_model_context(
            workspace_id=workspace_id,
            session_id=str(args.get("session_id") or "").strip() or None,
        )
        context = {
            **context,
            "workspace_id": workspace_id,
            "active_room": receptionist_context.get("active_room", state.get("active_room", "lobby")),
            "active_persona": receptionist_context.get("active_persona", state.get("active_persona", "Receptionist")),
            "session_id": receptionist_context.get("session_id"),
            "session_summary_text": receptionist_context.get("session_summary_text", ""),
            "recent_turns_text": receptionist_context.get("recent_turns_text", []),
        }

        settings = args.get("settings")
        if not isinstance(settings, dict):
            settings = {}

        task_type = str(args.get("task_type") or "conversation").strip() or "conversation"

        try:
            result = deps.model_router.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context=context,
                settings=settings,
                task_type=task_type,
            )
        except ModelRoutingError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": str(exc),
                    "attempts": exc.attempts,
                    "workspace_id": workspace_id,
                    "task_type": task_type,
                },
            ) from exc

        structured = {
            "workspace_id": workspace_id,
            "provider": result.provider,
            "model": result.model,
            "task_type": result.task_type,
            "fallback_used": result.fallback_used,
            "attempts": result.attempts,
            "response_text": result.text,
        }
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": result.text}],
        }

    def _workspace_id(args: Dict[str, Any], tool_name: str) -> str:
        workspace_id = str(args.get("workspace_id") or "").strip()
        if not workspace_id:
            raise deps.error_missing_required_field("workspace_id")
        return workspace_id

    def handle_search_web(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _workspace_id(args, "office.search_web")
        query = str(args.get("query") or args.get("request") or args.get("text") or "").strip()
        if not query:
            raise deps.error_missing_required_field("query")
        try:
            result = deps.search_service.search_web(
                query=query,
                limit=max(1, min(int(args.get("limit") or 5), 8)),
                recency_days=int(args["recency_days"]) if args.get("recency_days") is not None else None,
            )
        except SearchServiceError as exc:
            raise HTTPException(status_code=502, detail={"message": str(exc), "capability": "search.web"}) from exc
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                **result,
            },
            "content": [{"type": "text", "text": result["summary_text"]}],
        }

    def handle_search_reviews(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _workspace_id(args, "office.search_reviews")
        query = str(args.get("query") or args.get("request") or args.get("text") or "").strip()
        if not query:
            raise deps.error_missing_required_field("query")
        try:
            result = deps.search_service.search_reviews(
                query=query,
                location=str(args.get("location") or "").strip() or None,
                time_window=str(args.get("time_window") or "").strip() or None,
                limit=max(1, min(int(args.get("limit") or 5), 8)),
            )
        except SearchServiceError as exc:
            raise HTTPException(status_code=502, detail={"message": str(exc), "capability": "search.reviews"}) from exc
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                **result,
            },
            "content": [{"type": "text", "text": result["summary_text"]}],
        }

    def handle_search_places(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _workspace_id(args, "office.search_places")
        query = str(args.get("query") or args.get("request") or args.get("text") or "").strip()
        if not query:
            raise deps.error_missing_required_field("query")
        try:
            needs_location_raw = args.get("needs_location")
            needs_location = needs_location_raw is True or str(needs_location_raw).strip().lower() in {"1", "true", "yes"}
            result = deps.search_service.search_places(
                query=query,
                location=str(args.get("location") or "").strip() or None,
                category=str(args.get("category") or "").strip() or None,
                needs_location=needs_location,
                limit=max(1, min(int(args.get("limit") or 5), 8)),
            )
        except SearchServiceError as exc:
            raise HTTPException(status_code=502, detail={"message": str(exc), "capability": "search.places"}) from exc
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                **result,
            },
            "content": [{"type": "text", "text": result["summary_text"]}],
        }

    def handle_ocr_extract(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = _workspace_id(args, "office.ocr_extract")
        file_id = str(args.get("file_id") or "").strip()
        file_name = str(args.get("file_name") or args.get("name") or "").strip()
        if not file_id and not file_name:
            raise deps.error_missing_required_field("file_id")
        scope = str(args.get("scope") or "workspace").strip().lower() or "workspace"
        session_id = str(args.get("session_id") or "").strip() or None
        try:
            record, content_bytes = _resolve_ocr_file_record(
                workspace_id=workspace_id,
                file_id=file_id,
                file_name=file_name,
                scope=scope,
                session_id=session_id,
            )
            result = deps.ocr_service.extract_text(
                file_name=str(record.get("original_name") or file_name or file_id),
                mime_type=str(record.get("mime_type") or "").strip() or None,
                content_bytes=content_bytes,
            )
        except FileNotFoundError as exc:
            missing_target = file_id or file_name
            raise HTTPException(status_code=404, detail={"message": f"File not found: {missing_target}", "capability": "document.ocr"}) from exc
        except OcrServiceError as exc:
            raise HTTPException(status_code=502, detail={"message": str(exc), "capability": "document.ocr"}) from exc
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "file_id": record.get("file_id"),
                "original_name": record.get("original_name"),
                **result,
            },
            "content": [{"type": "text", "text": result["text"]}],
        }

    return {
        "office.ai_generate": handle_ai_generate,
        "office.search_web": handle_search_web,
        "office.search_reviews": handle_search_reviews,
        "office.search_places": handle_search_places,
        "office.ocr_extract": handle_ocr_extract,
    }
