from __future__ import annotations

import re
from urllib.parse import urlparse
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

GROUNDED_FOLLOWUP_CUE_RE = (
    re.compile(r"\b(?:it|its|they|them|their|this|that|those|these)\b", re.IGNORECASE),
    re.compile(r"\bagain\b", re.IGNORECASE),
    re.compile(
        r"\b(?:does|do|did|is|are|was|were|can|could|should|would|has|have|had)\s+"
        r"(?:it|they|them|their|this|that|those|these)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:what|where|when|who|which|how)\s+(?:is|are|was|were|do|does|did|can|could|should|would|has|have|had)\s+"
        r"(?:it|they|them|their|this|that|those|these)\b",
        re.IGNORECASE,
    ),
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
    if not any(pattern.search(question) for pattern in GROUNDED_FOLLOWUP_CUE_RE):
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


HOURS_QUESTION_RE = re.compile(r"\b(hours?|open|opening|closing|close|when\s+(?:is|are)\s+(?:it|they)\s+open)\b", re.IGNORECASE)
RESULT_PROVENANCE_RE = re.compile(r"\b(?:what|which)\s+(?:search\s+)?(?:result|source)\s+said\b", re.IGNORECASE)
TIME_TOKEN_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)
HOURS_EVIDENCE_RE = re.compile(
    r"(?:hours?|open|mon|monday|tue|tuesday|wed|wednesday|thu|thursday|fri|friday|sat|saturday|sun|sunday|daily).{0,120}?\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b.{0,120}",
    re.IGNORECASE,
)
LOCATION_QUESTION_RE = re.compile(r"\b(where|located|location|address|state|city|based)\b", re.IGNORECASE)
LOCATION_EVIDENCE_RE = re.compile(
    r"\b(?:located\s+(?:in|at)|in|at|address:?)[^.\n]{0,140}",
    re.IGNORECASE,
)
CONTACT_QUESTION_RE = re.compile(r"\b(phone|call|contact|number|email)\b", re.IGNORECASE)
CONTACT_EVIDENCE_RE = re.compile(
    r"\b(?:phone|call|contact|tel|telephone|email)\b[^.\n]{0,140}",
    re.IGNORECASE,
)
WEBSITE_QUESTION_RE = re.compile(r"\b(website|site|url|web\s*site|webpage)\b", re.IGNORECASE)
WEBSITE_EVIDENCE_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
FOUNDING_QUESTION_RE = re.compile(r"\b(founded|started|established|opened|launch(?:ed)?)\b", re.IGNORECASE)
FOUNDING_EVIDENCE_RE = re.compile(
    r"\b(?:founded|started|established|opened|launched)\b[^.\n]{0,140}",
    re.IGNORECASE,
)
OWNER_QUESTION_RE = re.compile(r"\b(owner|owns|owned by|founder)\b", re.IGNORECASE)
OWNER_EVIDENCE_RE = re.compile(
    r"\b(?:owner|owns|owned by|founder)\b[^.\n]{0,140}",
    re.IGNORECASE,
)
PRICE_QUESTION_RE = re.compile(r"\b(price|pricing|cost|expensive|cheap)\b", re.IGNORECASE)
PRICE_EVIDENCE_RE = re.compile(
    r"\b(?:price|pricing|cost|\$\d)\b[^.\n]{0,140}",
    re.IGNORECASE,
)

ATTRIBUTE_RULES = (
    ("hours", HOURS_QUESTION_RE, HOURS_EVIDENCE_RE),
    ("location", LOCATION_QUESTION_RE, LOCATION_EVIDENCE_RE),
    ("contact", CONTACT_QUESTION_RE, CONTACT_EVIDENCE_RE),
    ("website", WEBSITE_QUESTION_RE, WEBSITE_EVIDENCE_RE),
    ("founding", FOUNDING_QUESTION_RE, FOUNDING_EVIDENCE_RE),
    ("ownership", OWNER_QUESTION_RE, OWNER_EVIDENCE_RE),
    ("pricing", PRICE_QUESTION_RE, PRICE_EVIDENCE_RE),
)

ENTITY_SUMMARY_REQUEST_RE = re.compile(
    r"^(?:what\s+can\s+you\s+tell\s+me\s+about|tell\s+me\s+about|what\s+do\s+you\s+know\s+about|information\s+about|who\s+is|who's)\s+(.+?)\??$",
    re.IGNORECASE,
)


def _context_results(search_context: Dict[str, Any]) -> List[Dict[str, str]]:
    results = search_context.get("results")
    rows: List[Dict[str, str]] = []
    if not isinstance(results, list):
        return rows
    for item in results[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": str(item.get("title") or "").strip(),
                "source": str(item.get("source") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("snippet") or item.get("address") or "").strip(),
            }
        )
    return rows


def _search_context_evidence_text(search_context: Dict[str, Any]) -> str:
    parts: List[str] = []
    for item in _context_results(search_context):
        for value in (item.get("title"), item.get("snippet"), item.get("url")):
            text = str(value or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def build_grounded_search_context(*, routed: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        return {}
    return {
        "request": str(routed.get("request") or "").strip(),
        "entity_subject": str(routed.get("entity_subject") or "").strip(),
        "capability": str(routed.get("capability") or "").strip(),
        "provider": str(structured.get("provider") or "").strip(),
        "summary_text": str(structured.get("summary_text") or "").strip(),
        "response_text": str(structured.get("response_text") or "").strip(),
        "results": _context_results(structured),
    }


def _compact_snippet(snippet: str, max_chars: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(snippet or "").strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _result_label(result: Dict[str, str]) -> str:
    title = str(result.get("title") or "").strip()
    source = str(result.get("source") or "").strip()
    if title and source:
        return f"{title} ({source})"
    return title or source or "that result"


def _result_source_site(result: Dict[str, Any]) -> str:
    source = str(result.get("source") or "").strip()
    url = str(result.get("url") or "").strip()
    domain = ""
    if url:
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
    if source and domain and source.casefold() != domain.casefold():
        return f"{source} ({domain})"
    return source or domain or ""


def _search_source_sites(results: List[Dict[str, Any]]) -> List[str]:
    sites: List[str] = []
    seen = set()
    for item in results[:5]:
        if not isinstance(item, dict):
            continue
        site = _result_source_site(item)
        if not site:
            continue
        normalized = site.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        sites.append(site)
    return sites


def _normalize_time_token(value: str) -> str:
    token = re.sub(r"[.\s]+", "", str(value or "").strip().lower())
    token = token.replace("a.m", "am").replace("p.m", "pm")
    return token


def _display_time_token(value: str) -> str:
    normalized = _normalize_time_token(value)
    match = re.match(r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?(?P<meridiem>am|pm)$", normalized)
    if not match:
        return str(value or "").strip()
    hour = match.group("hour")
    minute = match.group("minute")
    meridiem = match.group("meridiem").upper()
    return f"{hour}{':' + minute if minute else ''} {meridiem}"


def _find_result_with_time(results: List[Dict[str, str]], token: str) -> Optional[Dict[str, str]]:
    normalized = _normalize_time_token(token)
    for item in results:
        snippet_tokenized = _normalize_time_token(item.get("snippet") or "")
        if normalized and normalized in snippet_tokenized:
            return item
    return None


def _find_hours_result(results: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    for item in results:
        snippet = str(item.get("snippet") or "").strip()
        if snippet and HOURS_EVIDENCE_RE.search(snippet):
            return item
    return None


def _find_attribute_result(results: List[Dict[str, str]], evidence_re: re.Pattern[str]) -> Optional[Dict[str, str]]:
    for item in results:
        haystack = " ".join(
            part for part in (str(item.get("title") or "").strip(), str(item.get("snippet") or "").strip()) if part
        )
        if haystack and evidence_re.search(haystack):
            return item
    return None


def _followup_terms(question_text: str, entity_subject: str = "") -> List[str]:
    lowered = str(question_text or "").lower()
    tokens = re.findall(r"[a-z0-9]{3,}", lowered)
    stopwords = {
        "about",
        "again",
        "are",
        "can",
        "company",
        "did",
        "does",
        "for",
        "from",
        "have",
        "here",
        "info",
        "information",
        "into",
        "its",
        "just",
        "result",
        "said",
        "search",
        "source",
        "tell",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "those",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "you",
    }
    subject_tokens = set(re.findall(r"[a-z0-9]{3,}", str(entity_subject or "").lower()))
    terms = [token for token in tokens if token not in stopwords and token not in subject_tokens]
    return list(dict.fromkeys(terms))


def _score_result_for_terms(result: Dict[str, str], terms: List[str]) -> int:
    if not terms:
        return 0
    haystack = " ".join(
        part.lower() for part in (str(result.get("title") or "").strip(), str(result.get("snippet") or "").strip()) if part
    )
    score = 0
    for term in terms:
        if term in haystack:
            score += 1
    return score


def _find_generic_result(results: List[Dict[str, str]], question_text: str, entity_subject: str = "") -> Optional[Dict[str, str]]:
    terms = _followup_terms(question_text, entity_subject=entity_subject)
    if not terms:
        return None
    best_result: Optional[Dict[str, str]] = None
    best_score = 0
    for item in results:
        score = _score_result_for_terms(item, terms)
        if score > best_score:
            best_score = score
            best_result = item
    if best_score <= 0:
        return None
    return best_result


def _normalize_subject_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return text.strip(" .,:;?!\"'")


def _explicit_entity_summary_subject(question_text: str) -> str:
    match = ENTITY_SUMMARY_REQUEST_RE.match(str(question_text or "").strip())
    if not match:
        return ""
    return _normalize_subject_text(match.group(1))


def _has_grounded_followup_cue(question_text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(question_text or "").strip())
    if not lowered:
        return False
    return any(pattern.search(lowered) for pattern in GROUNDED_FOLLOWUP_CUE_RE)


def _looks_like_grounded_search_followup(question_text: str, entity_subject: str = "") -> bool:
    lowered = re.sub(r"\s+", " ", str(question_text or "").strip().lower())
    if not lowered:
        return False
    if RESULT_PROVENANCE_RE.search(lowered):
        return True
    if not _has_grounded_followup_cue(lowered):
        return False
    if any(rule_re.search(lowered) for _, rule_re, _ in ATTRIBUTE_RULES):
        return True
    if len(lowered.split()) <= 12 and re.search(r"\b(it|they|their|them|there|again|this|that|those|these)\b", lowered):
        return True
    return False


def grounded_search_followup_response(question_text: str, search_context: Dict[str, Any]) -> Optional[str]:
    question = str(question_text or "").strip()
    if not question or not isinstance(search_context, dict):
        return None

    results = _context_results(search_context)
    if not results:
        return None
    entity_subject = str(search_context.get("entity_subject") or "").strip()
    explicit_summary_subject = _explicit_entity_summary_subject(question)
    normalized_entity_subject = _normalize_subject_text(entity_subject)
    if explicit_summary_subject and normalized_entity_subject and (
        explicit_summary_subject == normalized_entity_subject
        or explicit_summary_subject.startswith(normalized_entity_subject)
        or normalized_entity_subject.startswith(explicit_summary_subject)
    ):
        preserved_response = str(search_context.get("response_text") or "").strip()
        if preserved_response:
            return preserved_response
        matched = _find_generic_result(results, question, entity_subject=entity_subject) or results[0]
        return f"The preserved result I have is {_result_label(matched)}: {_compact_snippet(matched.get('snippet') or matched.get('url') or '')}"
    if not _looks_like_grounded_search_followup(question, entity_subject=entity_subject):
        return None

    evidence_text = _search_context_evidence_text(search_context)
    entity_followup = grounded_entity_followup_response(question, evidence_text)
    if entity_followup is not None:
        return entity_followup

    if RESULT_PROVENANCE_RE.search(question):
        quoted_groups = re.findall(r'"([^"]+)"|\'([^\']+)\'', question)
        flattened_terms = [next((part for part in group if part), "").strip() for group in quoted_groups]
        time_terms = TIME_TOKEN_RE.findall(question)
        if time_terms:
            target = time_terms[0]
            matched_target = _find_result_with_time(results, target)
            if matched_target is not None:
                return (
                    f"The preserved result that mentions {_display_time_token(target)} is "
                    f"{_result_label(matched_target)}: {_compact_snippet(matched_target.get('snippet') or '')}"
                )
            alternate = None
            for term in time_terms[1:]:
                alternate = _find_result_with_time(results, term)
                if alternate is not None:
                    break
            if alternate is not None:
                wanted = _display_time_token(time_terms[0])
                found = _display_time_token(time_terms[1])
                return (
                    f"I do not have a preserved search result snippet that says {wanted}. "
                    f"The preserved result I have says {found}: {_result_label(alternate)}: "
                    f"{_compact_snippet(alternate.get('snippet') or '')}. "
                    f"So the {wanted} wording came from my earlier answer, not grounded search evidence."
                )
            wanted = _display_time_token(time_terms[0])
            return (
                f"I do not have a preserved search result snippet that says {wanted}. "
                "That wording did not come from grounded search evidence I still have."
            )
        for term in [term for term in flattened_terms if term]:
            if not TIME_TOKEN_RE.search(term):
                continue
            matched = _find_result_with_time(results, term)
            if matched is not None:
                return (
                    f"The preserved result that mentions {_display_time_token(term)} is "
                    f"{_result_label(matched)}: {_compact_snippet(matched.get('snippet') or '')}"
                )
        return "I do not have a preserved search result snippet that matches that phrasing."

    for attribute_name, question_re, evidence_re in ATTRIBUTE_RULES:
        if question_re.search(question) is None:
            continue
        matched = _find_attribute_result(results, evidence_re)
        if matched is None:
            return f"I do not have a preserved search result snippet that answers that {attribute_name} question."
        return f"The preserved result I have for that is {_result_label(matched)}: {_compact_snippet(matched.get('snippet') or matched.get('url') or '')}"

    matched = _find_generic_result(results, question, entity_subject=entity_subject)
    if matched is not None:
        return f"The preserved result I have that best matches that is {_result_label(matched)}: {_compact_snippet(matched.get('snippet') or matched.get('url') or '')}"

    if re.match(r"^(?:what|where|when|who|how|is|are|does|did|can)\b", question, re.IGNORECASE):
        return "I do not have a preserved search result snippet that clearly answers that follow-up."

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
    source_sites = _search_source_sites(structured.get("results") or [])
    if source_sites:
        structured["source_sites"] = source_sites
        if "sources:" not in text.lower() and "source sites:" not in text.lower():
            text = f"{text.rstrip()}\n\nSources: {', '.join(source_sites[:3])}."
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
