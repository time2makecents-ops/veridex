from __future__ import annotations

from typing import Any, Dict


def request_text_from_response(response: Dict[str, Any]) -> str:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("response_text", "text", "message"):
            value = structured.get(key)
            if isinstance(value, str) and value.strip():
                return value
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
        structured["workspace_id"] = workspace_id
        structured["session_id"] = session_id
        enriched["structuredContent"] = structured
    else:
        enriched["structuredContent"] = {
            "workspace_id": workspace_id,
            "session_id": session_id,
        }
    enriched["workspace_id"] = workspace_id
    enriched["session_id"] = session_id
    return enriched
