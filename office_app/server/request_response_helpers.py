from __future__ import annotations

from typing import Any, Dict


def request_text_from_response(response: Dict[str, Any]) -> str:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("response_text", "text", "message"):
            value = structured.get(key)
            if isinstance(value, str) and value.strip():
                return value
        items = structured.get("items")
        if isinstance(items, list) and items:
            lines = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                index = item.get("index")
                description = item.get("description") or item.get("title") or item.get("content")
                if isinstance(index, int) and index > 0 and isinstance(description, str) and description.strip():
                    lines.append(f"{index}. {description.strip()}")
            if lines:
                return "\n".join(lines)
    content = response.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    return ""


def make_tool_text_conversational(response: Dict[str, Any], capability: str) -> Dict[str, Any]:
    text = request_text_from_response(response)
    if not text or not capability.startswith(("search.", "document.")):
        return response
    if text.startswith(("I need ", "No ", "Web results", "Review-oriented results", "Place results")):
        next_text = text
    elif capability == "document.ocr":
        next_text = f"Here is the extracted text:\n\n{text}"
    else:
        next_text = f"Here is what I found:\n\n{text}"
    updated = dict(response)
    structured = dict(updated.get("structuredContent") or {})
    structured["response_text"] = next_text
    updated["structuredContent"] = structured
    updated["content"] = [{"type": "text", "text": next_text}]
    return updated


def attach_request_context(response: Dict[str, Any], *, workspace_id: str, session_id: str) -> Dict[str, Any]:
    enriched = dict(response)
    structured = enriched.get("structuredContent")
    if isinstance(structured, dict):
        structured = dict(structured)
        effective_workspace_id = str(structured.get("workspace_id") or workspace_id).strip() or workspace_id
        effective_session_id = str(structured.get("session_id") or session_id).strip() or session_id
        structured["workspace_id"] = effective_workspace_id
        structured["session_id"] = effective_session_id
        enriched["structuredContent"] = structured
    else:
        effective_workspace_id = workspace_id
        effective_session_id = session_id
        enriched["structuredContent"] = {
            "workspace_id": effective_workspace_id,
            "session_id": effective_session_id,
        }
    enriched["workspace_id"] = effective_workspace_id
    enriched["session_id"] = effective_session_id
    return enriched
