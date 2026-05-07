from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


ENTITY_FOLLOWUP_RULES = (
    {
        "topic": "music_events",
        "question_re": re.compile(r"\b(?:live\s+music|music|events?|shows?|concerts?|venue)\b", re.IGNORECASE),
        "evidence_patterns": (
            ("music venue/arcade", re.compile(r"\b(music venue\s*/\s*arcade)\b", re.IGNORECASE)),
            ("music venue", re.compile(r"\b(music venue)\b", re.IGNORECASE)),
            ("live music", re.compile(r"\b(live music)\b", re.IGNORECASE)),
            ("music hall", re.compile(r"\b(music hall)\b", re.IGNORECASE)),
            ("concert venue", re.compile(r"\b(concert venue)\b", re.IGNORECASE)),
            ("events", re.compile(r"\b(events?)\b", re.IGNORECASE)),
            ("shows", re.compile(r"\b(shows?)\b", re.IGNORECASE)),
            ("concerts", re.compile(r"\b(concerts?)\b", re.IGNORECASE)),
            ("venue", re.compile(r"\b(venue)\b", re.IGNORECASE)),
        ),
        "negative_response": "I did not find live music or event terms in the grounded search results I have here.",
    },
)


def _result_text_for_evidence(response: Dict[str, Any]) -> str:
    structured = response.get("structuredContent")
    if not isinstance(structured, dict):
        return ""
    parts = [str(structured.get("summary_text") or "").strip()]
    results = structured.get("results")
    if isinstance(results, list):
        for item in results[:5]:
            if not isinstance(item, dict):
                continue
            parts.append(str(item.get("title") or "").strip())
            parts.append(str(item.get("snippet") or item.get("address") or "").strip())
    return "\n".join(part for part in parts if part)


def extract_grounded_entity_evidence(response: Dict[str, Any]) -> Dict[str, Any]:
    evidence_text = _result_text_for_evidence(response)
    profile: Dict[str, Any] = {
        "evidence_text": evidence_text,
        "topics": {},
    }
    for rule in ENTITY_FOLLOWUP_RULES:
        matches: List[str] = []
        seen = set()
        for canonical, pattern in rule["evidence_patterns"]:
            for match in pattern.finditer(evidence_text):
                phrase = re.sub(r"\s+", " ", match.group(1).strip()).lower()
                if phrase in seen:
                    continue
                seen.add(phrase)
                matches.append(phrase)
        if matches:
            profile["topics"][str(rule["topic"])] = {
                "best_match": matches[0],
                "matches": matches,
            }
    return profile


def grounded_entity_evidence_summary(response: Dict[str, Any], entity_subject: str) -> str:
    profile = extract_grounded_entity_evidence(response)
    subject = str(entity_subject or "it").strip() or "it"
    music_profile = profile["topics"].get("music_events") if isinstance(profile.get("topics"), dict) else None
    if not isinstance(music_profile, dict):
        return ""
    best_match = str(music_profile.get("best_match") or "").strip().lower()
    if not best_match:
        return ""
    if best_match in {"events", "event", "shows", "show", "concerts", "concert"}:
        return f"Search results mention {best_match} for {subject}."
    if best_match == "venue":
        return f"Search results mention {subject} as a venue."
    article = "an" if best_match[:1] in {"a", "e", "i", "o", "u"} else "a"
    return f"Search results describe {subject} as {article} {best_match}."


def grounded_entity_followup_response(question_text: str, evidence_text: str) -> Optional[str]:
    question = str(question_text or "").strip()
    evidence = str(evidence_text or "").strip()
    if not question or not evidence:
        return None
    for rule in ENTITY_FOLLOWUP_RULES:
        if rule["question_re"].search(question) is None:
            continue
        best_match = ""
        for _canonical, pattern in rule["evidence_patterns"]:
            match = pattern.search(evidence)
            if match:
                best_match = re.sub(r"\s+", " ", match.group(1).strip()).lower()
                break
        if not best_match:
            return str(rule["negative_response"])
        if best_match == "venue":
            return (
                "Search results mention it as a venue, which suggests it may host music or events, "
                "but I did not see an explicit live-music phrase. Check the current event calendar for specific dates."
            )
        return (
            f"Yes, search results describe it as a {best_match}, which suggests live music or events. "
            "Check the current event calendar for specific dates."
        )
    return None


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
    grounding_rule = ""
    grounded_evidence_summary = ""
    grounded_evidence_profile: Dict[str, Any] = {}
    if routed.get("grounding_required"):
        grounding_rule = (
            "For factual entity or company lookups, use only the returned search facts. "
            "If the results are thin or ambiguous, say you could not verify enough to answer fully. "
            "Do not add unsupported details. "
        )
        grounded_evidence_profile = extract_grounded_entity_evidence(result)
        grounded_evidence_summary = grounded_entity_evidence_summary(result, str(routed.get("entity_subject") or "it"))
    system_prompt = (
        f"You are Veridex. The active room is {state.get('active_room', 'lobby')}. "
        f"The active persona is {state.get('active_persona', 'Receptionist')}. "
        "Answer like a helpful conversational assistant. Use the search results below as evidence, not as raw output. "
        "Answer the user's question directly in the first sentence. "
        "For recommendation searches, name the best options you can infer from the results instead of describing Tripadvisor, Yelp, or other sources as resources. "
        "Do not lead with source names unless the source itself is the answer. "
        "If results are list pages, extract the named places from titles/snippets and say that the ranking is based on available search snippets. "
        "Mention important uncertainty briefly and include links when useful. "
        f"{grounded_evidence_summary} "
        f"{grounding_rule}"
        "Use recent turns only for clear follow-ups. Do not claim background work or future messages."
    )
    user_prompt = (
        f"User request: {routed.get('request', '')}\n\n"
        f"{grounded_evidence_summary}\n\n"
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
    if grounded_evidence_profile:
        structured["grounding_evidence_profile"] = grounded_evidence_profile
    if grounded_evidence_summary:
        structured["grounding_evidence_text"] = grounded_evidence_summary
        if grounded_evidence_summary.lower() not in text.lower():
            text = f"{grounded_evidence_summary} {text}".strip()
    structured["response_text"] = text
    updated["structuredContent"] = structured
    updated["content"] = [{"type": "text", "text": text}]
    return updated
