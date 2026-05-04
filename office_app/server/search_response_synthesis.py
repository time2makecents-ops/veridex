from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def tool_result_brief(response: Dict[str, Any]) -> str:
    structured = response.get("structuredContent")
    if not isinstance(structured, dict):
        return request_text_from_response(response)[:2500]
    summary = str(structured.get("summary_text") or request_text_from_response(response) or "").strip()
    results = structured.get("results")
    lines = [summary] if summary else []
    if isinstance(results, list):
        for index, item in enumerate(results[:5], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            source = str(item.get("source") or "").strip()
            snippet = str(item.get("snippet") or item.get("address") or "").strip()
            url = str(item.get("url") or "").strip()
            row = f"{index}. {title}".strip()
            if source:
                row += f" ({source})"
            if snippet:
                row += f": {snippet[:350]}"
            if url:
                row += f" URL: {url}"
            lines.append(row)
    return "\n".join(line for line in lines if line).strip()[:3500]


def synthesize_search_response(
    *,
    routed: Dict[str, Any],
    result: Dict[str, Any],
    workspace_id: str,
    session_id: str,
    user_profile: Optional[Dict[str, Any]],
    kernel: Any,
    router: Any,
    request_text_from_response: Callable[[Dict[str, Any]], str],
) -> Dict[str, Any]:
    if not str(routed.get("capability") or "").startswith("search."):
        return result
    brief = tool_result_brief(result)
    if not brief or brief.startswith(("I need ", "No ")):
        return result
    state = kernel.get_state(workspace_id)
    system_prompt = (
        f"You are Veridex. The active room is {state.get('active_room', 'lobby')}. "
        f"The active persona is {state.get('active_persona', 'Receptionist')}. "
        "Answer like a helpful conversational assistant. Use the search results below as evidence, not as raw output. "
        "Answer the user's question directly in the first sentence. "
        "For recommendation searches, name the best options you can infer from the results instead of describing Tripadvisor, Yelp, or other sources as resources. "
        "Do not lead with source names unless the source itself is the answer. "
        "If results are list pages, extract the named places from titles/snippets and say that the ranking is based on available search snippets. "
        "Mention important uncertainty briefly and include links when useful. "
        "Use recent turns only for clear follow-ups. Do not claim background work or future messages."
    )
    user_prompt = (
        f"User request: {routed.get('request', '')}\n\n"
        f"Search results:\n{brief}\n\n"
        "Write the response the user should see."
    )
    args: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "session_id": session_id,
        "task_type": "conversation",
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "context": {
            "workspace_id": workspace_id,
            "active_room": state.get("active_room", "lobby"),
            "active_persona": state.get("active_persona", "Receptionist"),
            "tool_result": brief,
        },
        "settings": {
            "temperature": 0.3,
            "max_output_tokens": 700,
            "provider_by_task_type": {"conversation": "gemini"},
        },
    }
    if user_profile:
        args["user_profile"] = user_profile
    try:
        synthesized = router.dispatch_capability("ai.respond", args, preferred_tool="office.ai_generate")
    except Exception:
        return result
    text = request_text_from_response(synthesized)
    if not text:
        return result
    updated = dict(result)
    structured = dict(updated.get("structuredContent") or {})
    structured["raw_tool_summary"] = structured.get("summary_text") or request_text_from_response(result)
    structured["response_text"] = text
    updated["structuredContent"] = structured
    updated["content"] = [{"type": "text", "text": text}]
    return updated
