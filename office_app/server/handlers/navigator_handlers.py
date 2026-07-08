from __future__ import annotations

from typing import Any, Dict

from .dependencies import HandlerDeps


def _report_text(report: Dict[str, Any]) -> str:
    health = report.get("health") if isinstance(report.get("health"), dict) else {}
    tools = report.get("tools") if isinstance(report.get("tools"), dict) else {}
    config = report.get("config") if isinstance(report.get("config"), dict) else {}
    workspace = report.get("workspace") if isinstance(report.get("workspace"), dict) else {}
    missing = tools.get("missing_expected") or []
    incidents = report.get("incidents") if isinstance(report.get("incidents"), list) else []
    status = "healthy" if health.get("ok") else "not healthy"
    missing_text = ", ".join(str(item) for item in missing) if missing else "none"
    config_text = (
        f"SerpAPI={bool(config.get('serpapi_ready'))}, "
        f"Google Search={bool(config.get('google_custom_search_ready'))}, "
        f"Google OAuth={bool(config.get('google_oauth_configured'))}"
    )
    return (
        f"Navigator status report: backend is {status}. "
        f"Active room is {workspace.get('active_room') or 'unknown'} as {workspace.get('active_persona') or 'unknown'}. "
        f"Registered tools: {tools.get('count', 0)}. Missing expected tools: {missing_text}. "
        f"Config readiness: {config_text}. Recent incidents: {len(incidents)}."
    )


def _recent_errors_text(result: Dict[str, Any]) -> str:
    incidents = result.get("incidents") if isinstance(result.get("incidents"), list) else []
    backend = ((result.get("logs") or {}).get("backend") if isinstance(result.get("logs"), dict) else []) or []
    frontend = ((result.get("logs") or {}).get("frontend") if isinstance(result.get("logs"), dict) else []) or []
    if not incidents and not backend and not frontend:
        return "Navigator found no recent incidents or log lines to report."
    return (
        f"Navigator found {len(incidents)} recent incident(s), "
        f"{len(backend)} backend log line(s), and {len(frontend)} frontend log line(s)."
    )


def _check_text(result: Dict[str, Any]) -> str:
    check_name = str(result.get("check_name") or "unknown")
    status = str(result.get("status") or "unknown")
    if status == "rejected":
        return str(result.get("summary") or f"Navigator rejected check {check_name}.")
    exit_code = result.get("exit_code")
    duration = result.get("duration_seconds")
    return f"Navigator check {check_name} {status}. Exit code: {exit_code}. Duration: {duration}s."


def _recommendations_text(result: Dict[str, Any]) -> str:
    recommendations = result.get("recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        return ""
    lines = []
    for index, recommendation in enumerate(recommendations[:4], start=1):
        if not isinstance(recommendation, dict):
            continue
        label = str(recommendation.get("label") or recommendation.get("action_id") or "").strip()
        action_id = str(recommendation.get("action_id") or "").strip()
        check_name = str(recommendation.get("check_name") or "").strip()
        if not label:
            continue
        suffix = f" ({action_id}{', ' + check_name if check_name else ''})" if action_id else ""
        lines.append(f"{index}. {label}{suffix}.")
    if not lines:
        return ""
    return " Recommendations:\n" + "\n".join(lines)


def build_navigator_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    def handle_status_report(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.navigator_status_report", args)
        session_id = str(args.get("session_id") or "").strip() or None
        report = deps.navigator_diagnostics_service.status_report(workspace_id, session_id=session_id)
        return {
            "structuredContent": {
                "speaker": "Navigator",
                "workspace_id": workspace_id,
                "session_id": session_id or "",
                "report": report,
            },
            "content": [{"type": "text", "text": _report_text(report)}],
        }

    def handle_recent_errors(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.navigator_recent_errors", args)
        session_id = str(args.get("session_id") or "").strip() or None
        result = deps.navigator_diagnostics_service.recent_errors(workspace_id, session_id=session_id)
        return {
            "structuredContent": {
                "speaker": "Navigator",
                "workspace_id": workspace_id,
                "session_id": session_id or "",
                "errors": result,
            },
            "content": [{"type": "text", "text": _recent_errors_text(result)}],
        }

    def handle_explain_error(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.navigator_explain_error", args)
        session_id = str(args.get("session_id") or "").strip() or None
        error_text = str(args.get("error_text") or args.get("text") or "").strip()
        result = deps.navigator_diagnostics_service.explain_error(
            workspace_id,
            session_id=session_id,
            error_text=error_text,
        )
        text = f"{result['summary']} Next step: {result['next_step']}{_recommendations_text(result)}"
        return {
            "structuredContent": {
                "speaker": "Navigator",
                "workspace_id": workspace_id,
                "session_id": session_id or "",
                "diagnostic": result,
            },
            "content": [{"type": "text", "text": text}],
        }

    def handle_run_check(args: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = deps.resolve_workspace_id("office.navigator_run_check", args)
        session_id = str(args.get("session_id") or "").strip() or None
        check_name = str(args.get("check_name") or "").strip()
        result = deps.navigator_diagnostics_service.run_check(
            workspace_id,
            session_id=session_id,
            check_name=check_name,
        )
        return {
            "structuredContent": {
                "speaker": "Navigator",
                "workspace_id": workspace_id,
                "session_id": session_id or "",
                "check": result,
            },
            "content": [{"type": "text", "text": _check_text(result)}],
        }

    return {
        "office.navigator_status_report": handle_status_report,
        "office.navigator_recent_errors": handle_recent_errors,
        "office.navigator_explain_error": handle_explain_error,
        "office.navigator_run_check": handle_run_check,
    }
