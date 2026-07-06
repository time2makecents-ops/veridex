from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from office_app.server.model_router import ModelRoutingError
from office_app.server.ocr_service import OcrServiceError
from office_app.server.search_service import SearchServiceError

from .dependencies import HandlerDeps


def build_ai_handlers(deps: HandlerDeps) -> Dict[str, Any]:
    NUMBERED_LIST_PLAN_RE = re.compile(r"\bcomplete numbered list of\s+(\d{1,2})\b", re.IGNORECASE)
    NUMBERED_ITEM_RE = re.compile(r"(?m)^\s*\d+\.")
    BULLET_ITEM_RE = re.compile(r"(?m)^\s*[-*]\s+")
    YES_NO_START_RE = re.compile(r"^\s*(yes|no)\b", re.IGNORECASE)
    RISK_CONTEXT_RE = re.compile(
        r"\b(alcohol|liquor|bar|bars|pub|pubs|tavern|taverns|nightclub|nightclubs|medical|health|legal|law|"
        r"finance|financial|investment|insurance|hiring|employment|privacy|security|tax|real estate|food safety|regulated)\b",
        re.IGNORECASE,
    )
    RISKY_TACTIC_RE = re.compile(
        r"\b(loyalty programs?|reward(?:s|ed)?|points?|discounts?|coupons?|punch cards?|free drinks?|free items?|"
        r"complimentary|buy\s+\d+.*get\s+\d+|incentives?|guaranteed returns?|medical claims?|legal advice)\b",
        re.IGNORECASE,
    )
    CAUTION_ALREADY_RE = re.compile(
        r"\b(compliance note|caution|verify (?:the )?(?:applicable |local )?rules|review local|ensure compliance|"
        r"regulated|policy-sensitive|legal requirements)\b",
        re.IGNORECASE,
    )
    OREGON_CONTEXT_RE = re.compile(r"\b(oregon|olcc)\b", re.IGNORECASE)
    USER_REQUEST_RE = re.compile(r"^\s*User request:\s*(.+?)(?:\n\s*\n|$)", re.IGNORECASE | re.DOTALL)
    GENERIC_RISK_INSTRUCTION_RE = re.compile(
        r"\bIf (?:any recommendation|the recommendation|the answer|this suggestion).*?"
        r"(?:risk|caution|rules|requirements|regulated|policy-sensitive).*?(?:\.|$)",
        re.IGNORECASE,
    )
    GENERIC_RISK_PHRASE_RE = re.compile(
        r"\blegal,\s*regulatory,\s*safety,\s*financial(?:,\s*employment)?(?:,\s*privacy)?,?\s*or\s*policy\s*risk\b",
        re.IGNORECASE,
    )
    YES_NO_QUESTION_RE = re.compile(
        r"^(?:does|do|did|is|are|was|were|has|have|had|can|could|will|would|should)\b",
        re.IGNORECASE,
    )
    COMPARISON_RE = re.compile(
        r"\b(vs\.?|versus|compare|comparison|difference between|better than|better for)\b",
        re.IGNORECASE,
    )
    SINGLE_CHOICE_RE = re.compile(
        r"\b(which one|what one|most effective one|most powerful one|strongest one|best one|best fit|single best|pick one)\b",
        re.IGNORECASE,
    )
    SINGLE_CHOICE_BEST_WAY_RE = re.compile(
        r"^(?:what|which)\s+(?:is\s+)?(?:the\s+)?best way\b",
        re.IGNORECASE,
    )
    FACTUAL_ENTITY_RE = re.compile(
        r"\b(what can you tell me about|tell me about|information about|who is|what do you know about)\b",
        re.IGNORECASE,
    )
    LABELED_FIELD_RE = re.compile(
        r"(?ims)^\s*([A-Za-z][A-Za-z ]{1,32})\s*:\s*(.+?)(?=^\s*[A-Za-z][A-Za-z ]{1,32}\s*:|\Z)"
    )
    UNCERTAINTY_PREFIXES = (
        "i do not",
        "i don't",
        "i could not",
        "i can't",
        "not from the information i have",
        "based on the information i have",
        "based on the available information",
        "the available results do not",
        "the search results do not",
        "search results do not",
        "the evidence provided does not",
    )

    def _combined_context_text(context: Dict[str, Any]) -> str:
        parts: List[str] = []
        room_memory = str(context.get("room_behavior_memory_text") or "").strip()
        if room_memory:
            parts.append(room_memory)
        session_facts = str(context.get("session_facts_text") or "").strip()
        if session_facts:
            parts.append(session_facts)
        summary = str(context.get("session_summary_text") or "").strip()
        if summary:
            parts.append(summary)
        recent_turns = context.get("recent_turns_text")
        if isinstance(recent_turns, list):
            parts.extend(str(turn or "").strip() for turn in recent_turns if str(turn or "").strip())
        history = str(context.get("conversation_history_text") or "").strip()
        if history:
            parts.append(history)
        work_context = str(context.get("active_work_context_text") or "").strip()
        if work_context:
            parts.append(work_context)
        return "\n".join(parts)

    def _risk_detection_prompt_text(user_prompt: str) -> str:
        text = str(user_prompt or "").strip()
        match = USER_REQUEST_RE.search(text)
        if match:
            return re.sub(r"\s+", " ", match.group(1).strip())
        text = GENERIC_RISK_INSTRUCTION_RE.sub("", text)
        text = GENERIC_RISK_PHRASE_RE.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    def _room_behavior_memory_text(*, workspace_id: str, refs: Any) -> str:
        if deps.archive_service is None or not isinstance(refs, list):
            return ""
        lines: List[str] = []
        seen: set[Tuple[str, str]] = set()
        for ref in refs[-20:]:
            if not isinstance(ref, dict):
                continue
            artifact_id = str(ref.get("artifact_id") or "").strip()
            artifact_workspace_id = str(ref.get("workspace_id") or workspace_id).strip() or workspace_id
            key = (artifact_workspace_id, artifact_id)
            if not artifact_id or key in seen:
                continue
            seen.add(key)
            try:
                record = deps.archive_service.get_artifact(artifact_workspace_id, artifact_id)
            except Exception:
                continue
            metadata = record.get("metadata")
            content = re.sub(r"\s+", " ", str(record.get("content") or "").strip())
            if not content:
                continue
            lowered = content.lower()
            if (
                (isinstance(metadata, dict) and str(metadata.get("memory_kind") or "").strip().lower() in {"persona_behavior", "persona_style"})
                or "how to win friends and influence people" in lowered
                or "dale carnegie" in lowered
                or "48 laws of power" in lowered
                or "in mind" in lowered
                or "from now on" in lowered
                or "filter your advice" in lowered
                or "answer my sales questions" in lowered
            ):
                continue
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)

    def _persona_style_guidance_text(content: str) -> str:
        lowered = re.sub(r"\s+", " ", str(content or "").strip().lower())
        if not lowered:
            return ""
        if "how to win friends and influence people" in lowered or "dale carnegie" in lowered:
            return (
                "Use a friendly, empathetic, relationship-first style. "
                "Prioritize trust, encouragement, and practical interpersonal advice."
            )
        if "48 laws of power" in lowered:
            return (
                "Use a strategic, power-aware style. "
                "Prioritize positioning, perception, and careful leverage."
            )
        cleaned = re.sub(r"\bthe book\b.*?(?:in mind|as a guide|when giving advice)\b", "", str(content), flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:how to win friends and influence people|dale carnegie|48 laws of power)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;?!")
        if not cleaned:
            return ""
        if len(cleaned) > 220:
            cleaned = cleaned[:217].rstrip() + "..."
        return cleaned

    def _persona_behavior_memory_text(*, refs: Any) -> str:
        if deps.archive_service is None or not isinstance(refs, list):
            return ""
        lines: List[str] = []
        seen: set[Tuple[str, str]] = set()
        for ref in refs[-20:]:
            if not isinstance(ref, dict):
                continue
            artifact_id = str(ref.get("artifact_id") or "").strip()
            artifact_workspace_id = str(ref.get("workspace_id") or workspace_id).strip() or workspace_id
            key = (artifact_workspace_id, artifact_id)
            if not artifact_id or key in seen:
                continue
            seen.add(key)
            try:
                record = deps.archive_service.get_artifact(artifact_workspace_id, artifact_id)
            except Exception:
                continue
            metadata = record.get("metadata")
            content = _persona_style_guidance_text(str(record.get("content") or "").strip())
            lowered = str(record.get("content") or "").strip().lower()
            is_persona_kind = isinstance(metadata, dict) and str(metadata.get("memory_kind") or "").strip().lower() in {"persona_behavior", "persona_style"}
            is_persona_style = any(
                marker in lowered
                for marker in (
                    "how to win friends and influence people",
                    "dale carnegie",
                    "48 laws of power",
                    "persona",
                    "style",
                    "tone",
                    "voice",
                    "advice",
                    "in mind",
                    "from now on",
                    "filter your advice",
                    "answer my sales questions",
                )
            )
            if not is_persona_kind and not is_persona_style:
                continue
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)

    def _active_work_context_text(rows: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for row in rows[:8]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "Untitled work").strip()
            summary = str(row.get("summary") or "").strip()
            room = str(row.get("active_room") or "").strip()
            persona = str(row.get("active_persona") or "").strip()
            location = f" ({room}/{persona})" if room or persona else ""
            detail = f" - {summary}" if summary else ""
            lines.append(f"- {title}{detail}{location}")
        return "\n".join(lines)

    def _active_work_context_rows(*, workspace_id: str) -> List[Dict[str, Any]]:
        service = deps.work_context_service
        if service is None:
            return []
        try:
            rows = service.list_contexts(workspace_id, status="active", limit=8)
        except Exception:
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _risk_caution_note(*, user_prompt: str, context: Dict[str, Any], response_text: str) -> str:
        if not response_text.strip():
            return response_text
        prompt_text = _risk_detection_prompt_text(user_prompt)
        context_text = _combined_context_text(context)
        prompt_has_risk = RISK_CONTEXT_RE.search(prompt_text) is not None
        prompt_looks_like_followup = bool(
            re.search(
                r"\b(it|that|those|them|this|which one|what one|why that|that one|the one|one)\b",
                prompt_text,
                re.IGNORECASE,
            )
            and len(prompt_text.split()) <= 10
        )
        context_has_risk = RISK_CONTEXT_RE.search(context_text) is not None
        if not prompt_has_risk and not (prompt_looks_like_followup and context_has_risk):
            return response_text
        if not RISKY_TACTIC_RE.search(response_text):
            return response_text
        if CAUTION_ALREADY_RE.search(response_text):
            return response_text
        combined_text = "\n".join([prompt_text, context_text]).strip()
        specific_to_oregon = bool(OREGON_CONTEXT_RE.search(combined_text))
        note = (
            "Compliance note: This suggestion may involve regulated or policy-sensitive details. "
            "Verify the applicable local rules before implementing incentives, claims, or offers."
        )
        if specific_to_oregon:
            note += " If this is in Oregon, verify OLCC rules before using alcohol-based incentives."
        return f"{response_text.rstrip()}\n\n{note}"

    def _format_model_failure_message(exc: ModelRoutingError) -> str:
        attempts = [str(item).strip() for item in exc.attempts if str(item).strip()]
        if not attempts:
            return str(exc)
        attempts_text = "; ".join(attempts[:4])
        if len(attempts) > 4:
            attempts_text += f"; plus {len(attempts) - 4} more"
        return f"{exc} Attempts: {attempts_text}"

    def _planned_numbered_list_count(user_prompt: str) -> Optional[int]:
        match = NUMBERED_LIST_PLAN_RE.search(user_prompt)
        if not match:
            return None
        count = int(match.group(1))
        return count if 2 <= count <= 20 else None

    def _effective_user_request_text(user_prompt: str) -> str:
        text = str(user_prompt or "").strip()
        match = USER_REQUEST_RE.search(text)
        if match:
            return re.sub(r"\s+", " ", match.group(1).strip())
        return re.sub(r"\s+", " ", text).strip()

    def _numbered_item_count(response_text: str) -> int:
        return len(NUMBERED_ITEM_RE.findall(response_text or ""))

    def _answer_completeness_contract(user_prompt: str) -> Optional[Dict[str, Any]]:
        request_text = _effective_user_request_text(user_prompt)
        lowered = request_text.lower()
        if not request_text:
            return None
        if _planned_numbered_list_count(user_prompt) is not None:
            return {
                "kind": "numbered_list",
                "request_text": request_text,
                "expected_count": _planned_numbered_list_count(user_prompt),
            }
        if YES_NO_QUESTION_RE.match(lowered):
            return {
                "kind": "yes_no",
                "request_text": request_text,
                "grounded": "Search results:" in user_prompt,
            }
        if SINGLE_CHOICE_RE.search(lowered) or SINGLE_CHOICE_BEST_WAY_RE.search(lowered):
            return {
                "kind": "single_choice",
                "request_text": request_text,
            }
        if COMPARISON_RE.search(lowered):
            return {
                "kind": "comparison",
                "request_text": request_text,
            }
        if "Search results:" in user_prompt and FACTUAL_ENTITY_RE.search(lowered):
            return {
                "kind": "grounded_entity_summary",
                "request_text": request_text,
                "grounded": True,
            }
        return None

    def _structured_contract_prompt(*, user_prompt: str, contract: Optional[Dict[str, Any]]) -> str:
        if not contract:
            return user_prompt
        kind = str(contract.get("kind") or "")
        if kind == "numbered_list":
            expected_count = int(contract.get("expected_count") or 0)
            if expected_count <= 0:
                return user_prompt
            return (
                f"{user_prompt}\n\n"
                "Internal answer contract:\n"
                f"- Return a complete numbered list with exactly {expected_count} items.\n"
                "- Each item must be substantive.\n"
                "- Do not stop early.\n"
                "- Do not include setup text before item 1."
            )
        if kind == "yes_no":
            grounding_rule = (
                "- Use only the grounded facts provided. If those facts do not support a direct answer, say Uncertain.\n"
                if contract.get("grounded")
                else ""
            )
            return (
                f"{user_prompt}\n\n"
                "Internal answer contract:\n"
                "Return plain text using exactly these labeled lines:\n"
                "Direct answer: Yes, No, or Uncertain\n"
                "Reason: one or two concise sentences\n"
                "Caveat: brief caution or none\n"
                f"{grounding_rule}"
                "Do not add any other labels or preamble."
            )
        if kind == "single_choice":
            return (
                f"{user_prompt}\n\n"
                "Internal answer contract:\n"
                "Return plain text using exactly these labeled lines:\n"
                "Direct answer: one single best option only\n"
                "Reason: one or two concise sentences\n"
                "Caveat: brief caution or none\n"
                "Do not include multiple options."
            )
        if kind == "comparison":
            return (
                f"{user_prompt}\n\n"
                "Internal answer contract:\n"
                "Return plain text using exactly these labeled lines:\n"
                "Summary: one sentence that answers the comparison directly\n"
                "Side A: concise points for the first side\n"
                "Side B: concise points for the second side\n"
                "Recommendation: brief recommendation or none"
            )
        if kind == "grounded_entity_summary":
            return (
                f"{user_prompt}\n\n"
                "Internal answer contract:\n"
                "Return plain text using exactly these labeled lines:\n"
                "Summary: grounded summary only\n"
                "Evidence: one or two grounded facts from the provided results\n"
                "Unknowns: what is still not verified, or none\n"
                "Use only grounded facts from the provided results. Do not infer unsupported specifics."
            )
        return user_prompt

    def _parse_labeled_fields(response_text: str) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        for label, value in LABELED_FIELD_RE.findall(str(response_text or "")):
            normalized_label = re.sub(r"\s+", " ", str(label).strip().lower())
            cleaned_value = re.sub(r"\s+", " ", str(value).strip())
            if normalized_label and cleaned_value and normalized_label not in fields:
                fields[normalized_label] = cleaned_value
        return fields

    def _ensure_terminal_punctuation(text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        if cleaned.endswith((".", "!", "?")):
            return cleaned
        return f"{cleaned}."

    def _render_structured_contract_response(contract: Optional[Dict[str, Any]], response_text: str) -> str:
        if not contract:
            return response_text
        kind = str(contract.get("kind") or "")
        if kind == "numbered_list":
            return response_text
        fields = _parse_labeled_fields(response_text)
        if not fields:
            return response_text
        if kind == "yes_no":
            direct_answer = str(fields.get("direct answer") or "").strip()
            reason = str(fields.get("reason") or "").strip()
            caveat = str(fields.get("caveat") or "").strip()
            parts: List[str] = []
            if direct_answer and direct_answer.lower() != "uncertain":
                parts.append(_ensure_terminal_punctuation(direct_answer))
            elif reason:
                parts.append(_ensure_terminal_punctuation(reason))
                reason = ""
            elif direct_answer:
                parts.append(_ensure_terminal_punctuation(direct_answer))
            if reason:
                parts.append(_ensure_terminal_punctuation(reason))
            if caveat and caveat.lower() != "none":
                parts.append(_ensure_terminal_punctuation(caveat))
            return " ".join(part for part in parts if part).strip() or response_text
        if kind == "single_choice":
            direct_answer = str(fields.get("direct answer") or "").strip()
            reason = str(fields.get("reason") or "").strip()
            caveat = str(fields.get("caveat") or "").strip()
            parts = [
                _ensure_terminal_punctuation(direct_answer),
                _ensure_terminal_punctuation(reason),
            ]
            if caveat and caveat.lower() != "none":
                parts.append(_ensure_terminal_punctuation(caveat))
            rendered = " ".join(part for part in parts if part).strip()
            return rendered or response_text
        if kind == "comparison":
            summary = str(fields.get("summary") or "").strip()
            side_a = str(fields.get("side a") or "").strip()
            side_b = str(fields.get("side b") or "").strip()
            recommendation = str(fields.get("recommendation") or "").strip()
            sections = [
                _ensure_terminal_punctuation(summary),
                _ensure_terminal_punctuation(side_a),
                _ensure_terminal_punctuation(side_b),
            ]
            if recommendation and recommendation.lower() != "none":
                sections.append(_ensure_terminal_punctuation(recommendation))
            rendered_sections = [section for section in sections if section]
            return "\n\n".join(rendered_sections).strip() or response_text
        if kind == "grounded_entity_summary":
            summary = str(fields.get("summary") or "").strip()
            evidence = str(fields.get("evidence") or "").strip()
            unknowns = str(fields.get("unknowns") or "").strip()
            parts = [
                _ensure_terminal_punctuation(summary),
                _ensure_terminal_punctuation(evidence),
            ]
            if unknowns and unknowns.lower() != "none":
                parts.append(_ensure_terminal_punctuation(unknowns))
            rendered = " ".join(part for part in parts if part).strip()
            return rendered or response_text
        return response_text

    def _response_satisfies_contract(contract: Dict[str, Any], response_text: str) -> bool:
        text = str(response_text or "").strip()
        if not text:
            return False
        kind = str(contract.get("kind") or "")
        lowered = text.lower()
        if kind == "yes_no":
            if YES_NO_START_RE.search(text):
                return True
            return any(lowered.startswith(prefix) for prefix in UNCERTAINTY_PREFIXES)
        if kind == "single_choice":
            if _numbered_item_count(text) > 1:
                return False
            if BULLET_ITEM_RE.search(text):
                return False
            first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip().lower()
            if re.search(r"\b(options?|answers?|choices?|factors?)\s+(?:are|include)\b", first_sentence):
                return False
            if "," in first_sentence:
                return False
            if re.search(r"\b(?:and|or)\b", first_sentence):
                return False
            return True
        if kind == "comparison":
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            return len(paragraphs) >= 3
        if kind == "grounded_entity_summary":
            return len(text.split()) >= 6
        return True

    def _completeness_retry_prompt(*, user_prompt: str, response_text: str, contract: Dict[str, Any]) -> str:
        kind = str(contract.get("kind") or "")
        request_text = str(contract.get("request_text") or user_prompt).strip()
        if kind == "yes_no":
            return (
                "The previous response did not answer the question directly enough.\n\n"
                f"Original request:\n{request_text}\n\n"
                f"Previous response:\n{response_text.strip()}\n\n"
                "Answer the question directly in the first word: Yes or No. "
                "If the available information does not support a direct yes/no answer, start with a brief uncertainty statement instead of guessing. "
                "Then give one or two concise sentences of reasoning."
            )
        if kind == "single_choice":
            return (
                "The previous response did not give a single best answer first.\n\n"
                f"Original request:\n{request_text}\n\n"
                f"Previous response:\n{response_text.strip()}\n\n"
                "Answer with one single best option in the first sentence, then give a brief reason. "
                "Do not return a list of multiple options unless the user explicitly asked for a list."
            )
        if kind == "comparison":
            return (
                "The previous response did not complete the comparison clearly enough.\n\n"
                f"Original request:\n{request_text}\n\n"
                f"Previous response:\n{response_text.strip()}\n\n"
                "Answer with a direct one-sentence summary first, then clearly cover each side, then a brief recommendation if useful."
            )
        if kind == "grounded_entity_summary":
            return (
                "The previous response did not produce a complete grounded summary.\n\n"
                f"Original request:\n{request_text}\n\n"
                f"Previous response:\n{response_text.strip()}\n\n"
                "Use only grounded facts from the provided search results or documents. "
                "State what is verified, then state what remains unverified. Do not guess."
            )
        return user_prompt

    def _incomplete_direct_answer_failure_message(contract: Dict[str, Any]) -> str:
        kind = str(contract.get("kind") or "")
        if kind == "yes_no" and contract.get("grounded"):
            return "I could not produce a complete grounded yes/no answer from the available information without guessing."
        if kind == "grounded_entity_summary" and contract.get("grounded"):
            return "I could not produce a complete grounded summary from the available information without guessing."
        return "I could not produce a complete direct answer. Please retry the question."

    def _list_completion_retry_prompt(*, user_prompt: str, response_text: str, expected_count: int) -> str:
        return (
            "The previous response did not complete the requested numbered list.\n\n"
            f"Original request and answer plan:\n{user_prompt}\n\n"
            f"Partial response:\n{response_text.strip()}\n\n"
            f"Return a complete numbered list with {expected_count} items. "
            "Keep any correct existing item, continue through the final item, and do not add an apology."
        )

    def _incomplete_list_failure_message(
        *,
        expected_count: int,
        actual_count: int,
        retry_error: Optional[ModelRoutingError] = None,
    ) -> str:
        message = (
            f"The AI returned an incomplete list ({actual_count} of {expected_count} requested items), "
            "so I did not treat it as a final answer."
        )
        if retry_error is not None:
            message += f" Automatic retry failed. {_format_model_failure_message(retry_error)}"
        else:
            message += " Automatic retry also returned an incomplete answer. Please retry the request."
        return message

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
                "Do not invent unsupported factual details about a specific company, entity, or person. If verified grounding is missing, say so directly instead of guessing. "
                "Apply active-room behavior memory as durable room-specific instructions when present. "
                "Apply persona behavior memory as style guidance when present, but do not echo the source book or memory label unless the user explicitly asks about it. "
                "Use active work context as durable cross-room continuity for current tasks, but do not expose internal context IDs unless the user asks for saved context details. "
                "Use the provided session conversation history as the current chat thread. Use session facts as transient thread-local context for details stated earlier in this session, such as location or organization, but do not turn them into durable room memory unless the user explicitly asks you to remember them. When the user asks a follow-up, comparison, pronoun-based question, 'what about ...', or 'how about ...', resolve it against the immediately relevant prior turns instead of treating it as a blank new chat. For broad help or capability questions like 'what can you help me with here?', answer from the active room and persona instead of continuing the previous topic. Do not ask for details already present in recent context. If the user asks a reflective follow-up like 'how did you come to that conclusion?' or 'what makes you say that?', explain the immediately previous answer instead of asking the user for more context. "
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
            "recent_turns": receptionist_context.get("recent_turns", []),
            "conversation_history_text": receptionist_context.get("conversation_history_text", ""),
            "session_facts": receptionist_context.get("session_facts", []),
            "session_facts_text": receptionist_context.get("session_facts_text", ""),
            "room_behavior_memory_refs": receptionist_context.get("room_behavior_memory_refs", []),
            "persona_behavior_memory_refs": receptionist_context.get("persona_behavior_memory_refs", []),
        }
        context["room_behavior_memory_text"] = _room_behavior_memory_text(
            workspace_id=workspace_id,
            refs=context.get("room_behavior_memory_refs"),
        )
        context["persona_behavior_memory_text"] = _persona_behavior_memory_text(
            refs=list(context.get("persona_behavior_memory_refs") or []) + list(context.get("room_behavior_memory_refs") or []),
        )
        context["active_work_context"] = _active_work_context_rows(workspace_id=workspace_id)
        context["active_work_context_text"] = _active_work_context_text(context["active_work_context"])

        settings = args.get("settings")
        if not isinstance(settings, dict):
            settings = {}

        task_type = str(args.get("task_type") or "conversation").strip() or "conversation"

        answer_contract = _answer_completeness_contract(user_prompt)
        generation_prompt = _structured_contract_prompt(user_prompt=user_prompt, contract=answer_contract)

        try:
            result = deps.model_router.generate_response(
                system_prompt=system_prompt,
                user_prompt=generation_prompt,
                context=context,
                settings=settings,
                task_type=task_type,
            )
        except ModelRoutingError as exc:
            message = _format_model_failure_message(exc)
            raise HTTPException(
                status_code=503,
                detail={
                    "message": message,
                    "attempts": exc.attempts,
                    "workspace_id": workspace_id,
                    "task_type": task_type,
                },
            ) from exc

        expected_list_count = _planned_numbered_list_count(user_prompt)
        response_text = _render_structured_contract_response(answer_contract, result.text)
        if expected_list_count is not None and _numbered_item_count(response_text) < expected_list_count:
            original_count = _numbered_item_count(response_text)
            retry_prompt = _list_completion_retry_prompt(
                user_prompt=user_prompt,
                response_text=response_text,
                expected_count=expected_list_count,
            )
            try:
                retry = deps.model_router.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=retry_prompt,
                    context=context,
                    settings=settings,
                    task_type=task_type,
                )
                result = retry
                response_text = _render_structured_contract_response(answer_contract, retry.text)
                retry_count = _numbered_item_count(response_text)
                if retry_count < expected_list_count:
                    response_text = _incomplete_list_failure_message(
                        expected_count=expected_list_count,
                        actual_count=retry_count,
                    )
            except ModelRoutingError as exc:
                response_text = _incomplete_list_failure_message(
                    expected_count=expected_list_count,
                    actual_count=original_count,
                    retry_error=exc,
                )
        elif answer_contract is not None and not _response_satisfies_contract(answer_contract, response_text):
            retry_prompt = _completeness_retry_prompt(
                user_prompt=user_prompt,
                response_text=response_text,
                contract=answer_contract,
            )
            try:
                retry = deps.model_router.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=_structured_contract_prompt(user_prompt=retry_prompt, contract=answer_contract),
                    context=context,
                    settings=settings,
                    task_type=task_type,
                )
                result = retry
                response_text = _render_structured_contract_response(answer_contract, retry.text)
                if not _response_satisfies_contract(answer_contract, response_text):
                    response_text = _incomplete_direct_answer_failure_message(answer_contract)
            except ModelRoutingError:
                response_text = _incomplete_direct_answer_failure_message(answer_contract)

        response_text = _risk_caution_note(
            user_prompt=user_prompt,
            context=context,
            response_text=response_text,
        )
        structured = {
            "workspace_id": workspace_id,
            "provider": result.provider,
            "model": result.model,
            "task_type": result.task_type,
            "fallback_used": result.fallback_used,
            "attempts": result.attempts,
            "response_text": response_text,
        }
        return {
            "structuredContent": structured,
            "content": [{"type": "text", "text": response_text}],
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
