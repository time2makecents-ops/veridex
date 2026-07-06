from __future__ import annotations

from typing import Any, Dict, List

from office_app.server.handlers.dependencies import HandlerDeps


def _work_context_text(rows: List[Dict[str, Any]], *, status: str) -> str:
    if not rows:
        return f"No {status} work context is saved for this workspace."
    lines = [f"{status.title()} work context:"]
    for idx, row in enumerate(rows, start=1):
        title = str(row.get("title") or "Untitled work").strip()
        summary = str(row.get("summary") or "").strip()
        room = str(row.get("active_room") or "").strip()
        persona = str(row.get("active_persona") or "").strip()
        location = f" ({room}/{persona})" if room or persona else ""
        detail = f" - {summary}" if summary else ""
        lines.append(f"{idx}. {title}{detail}{location}")
    return "\n".join(lines)


def build_work_context_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_work_context_save(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        title = str(args.get("title") or "").strip()
        summary = str(args.get("summary") or title).strip()
        replace_active_manual = bool(args.get("replace_active_manual"))
        if not title:
            raise deps.error_missing_required_field("title")
        session_id = str(args.get("session_id") or "").strip()
        try:
            state = deps.kernel.get_state(workspace_id) if deps.kernel is not None else {}
        except Exception:
            state = {}
        source_suffix = deps.utc_now().replace(":", "").replace("-", "").replace(".", "")
        source_id = f"{session_id or 'workspace'}:manual:current" if replace_active_manual else f"{session_id or 'workspace'}:manual:{source_suffix}"
        context = deps.work_context_service.upsert_context(
            workspace_id=workspace_id,
            source_type="manual",
            source_id=source_id,
            title=title,
            summary=summary,
            status="active",
            session_id=session_id,
            active_room=str(state.get("active_room") or "").strip(),
            active_persona=str(state.get("active_persona") or "").strip(),
            refs={"kind": "manual_active_work", "mode": "replace_current" if replace_active_manual else "append"},
        )
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "context": context,
            },
            "content": [{"type": "text", "text": f"{'Updated' if replace_active_manual else 'Saved'} active work context: {context.get('title') or title}"}],
        }

    def handle_work_context_list(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        status = str(args.get("status") or "active").strip().lower() or "active"
        limit = int(args.get("limit", 10))
        rows = deps.work_context_service.list_contexts(workspace_id, status=status, limit=limit)
        response_text = _work_context_text(rows, status=status)
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "status": status,
                "count": len(rows),
                "contexts": rows,
            },
            "content": [{"type": "text", "text": response_text}],
        }

    def handle_work_context_complete(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = args["workspace_id"]
        all_active = bool(args.get("all_active"))
        active_index = int(args.get("active_index") or 0)
        context_id = str(args.get("context_id") or "").strip()
        if not all_active and active_index < 1 and not context_id:
            raise deps.error_missing_required_field("all_active")
        if context_id:
            summary = str(args.get("summary") or "User completed selected work context.").strip()
            selected = deps.work_context_service.complete_context_by_id(
                workspace_id=workspace_id,
                context_id=context_id,
                summary=summary,
            )
            completed = [selected] if selected else []
        elif active_index > 0:
            summary = str(args.get("summary") or "User completed selected work context.").strip()
            selected = deps.work_context_service.complete_active_context_by_index(
                workspace_id=workspace_id,
                active_index=active_index,
                summary=summary,
            )
            completed = [selected] if selected else []
        else:
            summary = str(args.get("summary") or "User cleared active work context.").strip()
            completed = deps.work_context_service.complete_active_contexts(workspace_id=workspace_id, summary=summary)
        count = len(completed)
        item_word = "item" if count == 1 else "items"
        text = f"Completed work context {active_index}." if active_index > 0 and count else f"Completed {count} work context {item_word}."
        if context_id and count:
            text = "Completed work context."
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "completed_count": count,
                "active_index": active_index or None,
                "context_id": context_id or None,
                "contexts": completed,
            },
            "content": [{"type": "text", "text": text}],
        }

    return {
        "office.work_context_save": handle_work_context_save,
        "office.work_context_list": handle_work_context_list,
        "office.work_context_complete": handle_work_context_complete,
    }
