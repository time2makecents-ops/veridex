from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

from office_app.server.model_router import ModelRoutingError

from .dependencies import HandlerDeps


def build_ai_handlers(deps: HandlerDeps) -> Dict[str, Any]:
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
            user_profile=args.get("user_profile") if isinstance(args.get("user_profile"), dict) else None,
            session_id=str(args.get("session_id") or "").strip() or None,
        )
        if isinstance(args.get("user_profile"), dict):
            deps.receptionist_context_service.update_context(
                workspace_id,
                {"known_user_profile": args.get("user_profile")},
            )
        context = {
            **context,
            "receptionist_context": receptionist_context,
            "room_directory_text": receptionist_context.get("room_directory_text", ""),
            "known_user_profile_text": receptionist_context.get("known_user_profile_text", ""),
            "session_summary_text": receptionist_context.get("session_summary_text", ""),
            "recent_turns_text": receptionist_context.get("recent_turns_text", []),
            "prompt_state_text": receptionist_context.get("prompt_state_text", ""),
            "behavior_rules": receptionist_context.get("behavior_rules", []),
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

    def _not_configured(tool_name: str, capability: str):
        def handler(args: Dict[str, Any]) -> Dict[str, Any]:
            raise HTTPException(
                status_code=501,
                detail={
                    "message": f"{tool_name} is defined in Veridex but not configured yet.",
                    "capability": capability,
                },
            )

        return handler

    return {
        "office.ai_generate": handle_ai_generate,
        "office.search_web": _not_configured("office.search_web", "search.web"),
        "office.search_reviews": _not_configured("office.search_reviews", "search.reviews"),
        "office.search_places": _not_configured("office.search_places", "search.places"),
        "office.ocr_extract": _not_configured("office.ocr_extract", "document.ocr"),
    }
