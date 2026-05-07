from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ConversationPlan:
    user_prompt: str
    answer_type: str
    risk_flags: Tuple[str, ...] = ()


class ConversationPlanner:
    RECENT_TURN_LIMIT = 12
    PLAIN_TEXT_STYLE_RULES = (
        "- Format for a plain text chat window: no markdown tables, no pipe tables, and no markdown bold or italics.\n"
        "- Use short paragraphs or simple numbered lists only.\n"
        "- Use normal spacing and hyphenation; avoid compressed words like highimpact, welldesigned, or repeatpurchase.\n"
        "- Do not invent study numbers, percentages, or statistics unless they are provided in the current context.\n"
    )
    NUMBERED_LIST_ITEM_RE = re.compile(r"(?m)^\s*\d+\.\s+")
    CONTEXTUAL_REFERENCE_HINTS = (
        "what about",
        "how about",
        "which one",
        "what one",
        "which level",
        "what level",
        "most effective one",
        "most powerful one",
        "the first one",
        "the last one",
        "the strongest one",
        "the best one",
        "how does that compare",
        "would that work",
        "does that work",
    )
    META_REFERENCE_PATTERNS = (
        re.compile(r"^how did you come to that conclusion\??$", re.IGNORECASE),
        re.compile(r"^why did you come to that conclusion\??$", re.IGNORECASE),
        re.compile(r"^what makes you say that\??$", re.IGNORECASE),
        re.compile(r"^why do you think that\??$", re.IGNORECASE),
        re.compile(r"^why that conclusion\??$", re.IGNORECASE),
        re.compile(r"^how did you decide that\??$", re.IGNORECASE),
        re.compile(r"^why that one\??$", re.IGNORECASE),
    )
    PRIOR_TOPIC_PATTERNS = (
        re.compile(r"\bwhat\s+is\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\bexplain\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\btell me about\s+(.+?)\??$", re.IGNORECASE),
    )
    STRATEGY_TOPIC_PATTERNS = (
        re.compile(r"\bways?\s+for\s+(.+?)\s+to\s+(.+?)(?:[,.:;!?]|$)", re.IGNORECASE),
        re.compile(r"\bbest\s+way\s+for\s+(.+?)\s+to\s+(.+?)(?:[,.:;!?]|$)", re.IGNORECASE),
        re.compile(r"\bmain ways?\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\btypes of\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\bways?\s+to\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"\bstrategies?\s+(?:for|to)\s+(.+?)\??$", re.IGNORECASE),
    )
    RISK_CONTEXT_RE = re.compile(
        r"\b(alcohol|liquor|bar|bars|medical|health|legal|law|finance|financial|investment|insurance|"
        r"hiring|employment|privacy|security|tax|real estate|food safety|regulated)\b",
        re.IGNORECASE,
    )

    def plan_model_prompt(self, request_text: str) -> ConversationPlan:
        text = re.sub(r"\s+", " ", str(request_text or "").strip())
        lowered = text.lower()
        if not text:
            return ConversationPlan(user_prompt=text, answer_type="chat")

        risk_flags = ("regulated_or_high_risk",) if self.RISK_CONTEXT_RE.search(lowered) else ()

        if self._looks_like_list_request(lowered):
            count = self._requested_count(lowered) or 5
            risk_line = (
                "- In regulated or policy-sensitive contexts, do not lead with incentives, discounts, claims, or shortcuts unless the user explicitly asks for them.\n"
                if risk_flags
                else ""
            )
            prompt = (
                f"User request: {text}\n\n"
                "Answer plan:\n"
                f"- Provide a complete numbered list of {count} substantive items unless fewer genuinely exist.\n"
                "- Put the strongest or most practical items first when ranking matters.\n"
                "- Use one concise, practical explanation per item.\n"
                "- Do not stop after the first item.\n"
                f"{self.PLAIN_TEXT_STYLE_RULES}"
                f"{risk_line}"
                "- If any recommendation touches legal, regulatory, safety, financial, or policy risk, include one brief verification caution only if the answer has not already included one.\n"
                "- If current facts are needed, say what should be searched or verified.\n\n"
                "Respond directly to the user."
            )
            return ConversationPlan(user_prompt=prompt, answer_type="list", risk_flags=risk_flags)

        if self._looks_like_choose_one_request(lowered):
            risk_line = (
                "- In regulated or policy-sensitive contexts, avoid choosing incentives, discounts, claims, or shortcuts as the top answer unless the user explicitly asks for those.\n"
                if risk_flags
                else ""
            )
            prompt = (
                f"User request: {text}\n\n"
                "Answer plan:\n"
                "- Choose one answer first.\n"
                "- State the criteria you used in one sentence.\n"
                "- Briefly compare it with the next strongest alternative.\n"
                "- If the answer depends on missing context, state the assumption and give the best provisional answer.\n"
                "- Keep the answer to 2 or 3 short paragraphs, unless the user asks for more detail.\n"
                f"{self.PLAIN_TEXT_STYLE_RULES}"
                f"{risk_line}"
                "- If the recommendation touches legal, regulatory, safety, financial, or policy risk, include one brief verification caution only if the answer has not already included one.\n\n"
                "Respond directly to the user."
            )
            return ConversationPlan(user_prompt=prompt, answer_type="recommendation", risk_flags=risk_flags)

        return ConversationPlan(user_prompt=text, answer_type="chat", risk_flags=risk_flags)

    def rewrite_followup(self, request_text: str, recent_turns: List[Dict[str, Any]]) -> Optional[ConversationPlan]:
        text = re.sub(r"\s+", " ", str(request_text or "").strip())
        lowered = text.lower()
        if not text:
            return None

        if re.search(r"\byou only listed\s+(?:1|one)\b", lowered):
            subject, _unit = self._infer_followup_subject(recent_turns)
            if subject:
                return ConversationPlan(
                    user_prompt=(
                        f"Continue the incomplete list for {subject}. "
                        "Keep the existing item 1 unless the user explicitly asks to revise it. "
                        "Provide items 2 through 5 as concise numbered lines only. "
                        "Use plain text only: no markdown tables, no pipe tables, and no markdown bold."
                    ),
                    answer_type="continuation",
                )

        meta = self._rewrite_meta_reference_followup(text, recent_turns)
        if meta:
            return ConversationPlan(user_prompt=meta, answer_type="reasoning_followup")

        analogous = self._rewrite_analogous_followup(text, recent_turns)
        if analogous:
            return ConversationPlan(user_prompt=analogous, answer_type="comparative_followup")

        contextual = self._rewrite_contextual_reference_followup(text, recent_turns)
        if contextual:
            return ConversationPlan(user_prompt=contextual, answer_type="contextual_followup")

        return None

    @staticmethod
    def _requested_count(lowered: str) -> Optional[int]:
        match = re.search(r"\b(?:top|main|best)?\s*(\d{1,2})\b", lowered)
        if not match:
            return None
        count = int(match.group(1))
        return count if 1 <= count <= 20 else None

    @staticmethod
    def _looks_like_list_request(lowered: str) -> bool:
        return bool(
            re.search(
                r"\b(main ways?|ways to|types of|kinds of|methods|strategies|approaches|options|steps|"
                r"examples|ideas|tips)\b",
                lowered,
            )
        )

    @staticmethod
    def _looks_like_choose_one_request(lowered: str) -> bool:
        return bool(re.search(r"\b(most effective|most powerful|best|strongest|which one|what one)\b", lowered))

    def _recent_assistant_turn(self, recent_turns: List[Dict[str, Any]], *, require_numbered_list: bool = False) -> Optional[str]:
        for turn in reversed(recent_turns[-self.RECENT_TURN_LIMIT :]):
            if str(turn.get("role") or "").strip().lower() != "assistant":
                continue
            text = str(turn.get("text") or "").strip()
            if text and (not require_numbered_list or self.NUMBERED_LIST_ITEM_RE.search(text)):
                return text
        return None

    @staticmethod
    def _recent_user_turns(recent_turns: List[Dict[str, Any]]) -> List[str]:
        rows: List[str] = []
        for turn in recent_turns[-ConversationPlanner.RECENT_TURN_LIMIT :]:
            if str(turn.get("role") or "").strip().lower() != "user":
                continue
            text = str(turn.get("text") or "").strip()
            if text:
                rows.append(text)
        return rows

    def _recent_user_turn_before_assistant(self, recent_turns: List[Dict[str, Any]]) -> Optional[str]:
        seen_assistant = False
        for turn in reversed(recent_turns[-self.RECENT_TURN_LIMIT :]):
            role = str(turn.get("role") or "").strip().lower()
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            if role == "assistant" and not seen_assistant:
                seen_assistant = True
                continue
            if seen_assistant and role == "user":
                return text
        return None

    @staticmethod
    def _clean_subject_text(value: str) -> str:
        text = re.sub(r"\s+", " ", value).strip(" .?!,:;")
        text = re.sub(r"^(?:a|an|the)\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"\s+(?:are|is)\s+(?:by|through|with|using|a combination of|typically|usually)\b.*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        text = re.sub(r"\s+(?:include|includes|including)\b.*$", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+(?:ranked by|based on|from this list|out of these)\b.*$", "", text, flags=re.IGNORECASE).strip()
        return text

    def _infer_strategy_subject_from_text(self, text: str) -> Optional[str]:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized:
            return None
        for pattern in self.STRATEGY_TOPIC_PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue
            groups = [self._clean_subject_text(group) for group in match.groups() if group is not None]
            groups = [group for group in groups if group]
            if not groups:
                continue
            if len(groups) >= 2 and " to " not in groups[0].lower():
                return f"{groups[0]} to {groups[1]}"
            return groups[0]
        return None

    def _infer_followup_subject(self, recent_turns: List[Dict[str, Any]]) -> Tuple[Optional[str], str]:
        assistant_text = self._recent_assistant_turn(recent_turns, require_numbered_list=True) or self._recent_assistant_turn(recent_turns) or ""
        user_text = self._recent_user_turn_before_assistant(recent_turns) or ""
        user_turns = self._recent_user_turns(recent_turns)
        combined = f"{user_text}\n{assistant_text}".lower()

        if "maslow" in combined:
            return "Maslow's hierarchy of needs", "level"

        assistant_subject = self._infer_strategy_subject_from_text(assistant_text)
        if assistant_subject:
            return assistant_subject, "option"

        for candidate_text in [user_text, *reversed(user_turns)]:
            subject = self._infer_strategy_subject_from_text(candidate_text)
            if subject:
                return subject, "option"

        for pattern in self.PRIOR_TOPIC_PATTERNS:
            match = pattern.search(user_text)
            if match:
                subject = re.sub(r"\s+", " ", match.group(1).strip(" .?!"))
                if subject:
                    return subject, "item"

        if assistant_text and self.NUMBERED_LIST_ITEM_RE.search(assistant_text):
            first_sentence = assistant_text.split("\n", 1)[0].strip()
            if first_sentence:
                return first_sentence.rstrip(".:"), "item"

        return None, "item"

    def _looks_like_contextual_followup(self, request_text: str) -> bool:
        lowered = re.sub(r"\s+", " ", request_text.strip().lower())
        if any(hint in lowered for hint in self.CONTEXTUAL_REFERENCE_HINTS):
            return True
        return len(lowered.split()) <= 8 and re.search(r"\b(it|that|those|them|one|ones|level)\b", lowered) is not None

    @staticmethod
    def _extract_ordinal_reference(lowered: str) -> Optional[str]:
        for value in ("first", "second", "third", "last"):
            if value in lowered:
                return value
        return None

    @staticmethod
    def _extract_list_items(assistant_text: str) -> List[str]:
        text = re.sub(r"\s+", " ", assistant_text.strip())
        if not text:
            return []
        numbered = re.findall(r"(?:^|\s)\d+\.\s+([^.;\n]+)", assistant_text)
        if len(numbered) >= 2:
            return [re.sub(r"\s+", " ", item.strip(" .:;-")) for item in numbered[:8] if item.strip()]

        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        working = re.sub(
            r"^.*?(?:through a combination of|include|includes|including|are by|are|is)\s+",
            "",
            first_sentence,
            flags=re.IGNORECASE,
        ).strip(" .")
        if "," not in working and " and " not in working:
            return []
        working = re.sub(r",\s*(?:and|or)\s+", ", ", working, flags=re.IGNORECASE)
        parts = [re.sub(r"^(?:by|a|an|the)\s+", "", part.strip(" .")) for part in working.split(",")]
        cleaned = [part for part in parts if len(part) >= 4 and not part.lower().startswith(("this is because", "for example", "such as"))]
        unique: List[str] = []
        seen = set()
        for item in cleaned:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique if len(unique) >= 3 else []

    def _extract_primary_claim(self, assistant_text: str, *, subject: Optional[str], unit: str) -> Optional[str]:
        text = re.sub(r"\s+", " ", assistant_text.strip())
        if not text:
            return None

        bold_match = re.search(r"\*\*(.+?)\*\*", assistant_text)
        if bold_match:
            value = re.sub(r"\s+", " ", bold_match.group(1).strip(" .,:;"))
            if subject == "Maslow's hierarchy of needs":
                return f"{value} is the most powerful single {unit} of {subject} in marketing"
            return value

        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        label = first_sentence.strip(" .,:;")
        if subject == "Maslow's hierarchy of needs" and unit == "level" and re.fullmatch(r"[A-Za-z][A-Za-z -]{1,40}", label):
            return f"{label} is the most powerful single {unit} of {subject} in marketing"
        if unit == "option" and re.fullmatch(r"[A-Za-z][A-Za-z '&-]{1,50}", label):
            return label
        return first_sentence.rstrip(".") if len(first_sentence) >= 12 else None

    @staticmethod
    def _extract_option_label(claim: str) -> str:
        text = re.sub(r"\s+", " ", str(claim or "").strip()).strip(" .")
        head = re.split(r"\s+is\s+", text, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,:;")
        return head or text

    def _rewrite_meta_reference_followup(self, request_text: str, recent_turns: List[Dict[str, Any]]) -> Optional[str]:
        if not any(pattern.match(request_text) for pattern in self.META_REFERENCE_PATTERNS):
            return None
        assistant_text = self._recent_assistant_turn(recent_turns)
        if not assistant_text:
            return None
        subject, unit = self._infer_followup_subject(recent_turns)
        claim = self._extract_primary_claim(assistant_text, subject=subject, unit=unit)
        if not claim:
            return None
        if unit == "option" and subject:
            label = self._extract_option_label(claim)
            return (
                f"Explain why you concluded that {label} is the strongest option for {subject}. "
                "Tie the explanation to the immediately previous answer, state the criteria used, "
                "and compare it briefly with the next strongest alternative. "
                "Use plain text only, not a table. Do not invent statistics or study claims. "
                "Keep the answer to 2 or 3 short paragraphs."
            )
        return (
            f"Explain why you concluded that {claim}. "
            "Tie the explanation to the immediately previous answer, state the criteria used, "
            "and compare it briefly with the next strongest alternative. "
            "Use plain text only, not a table. Do not invent statistics or study claims. "
            "Keep the answer to 2 or 3 short paragraphs."
        )

    def _rewrite_analogous_followup(self, request_text: str, recent_turns: List[Dict[str, Any]]) -> Optional[str]:
        match = re.match(r"^(?:what|how)\s+about\s+(.+?)\??$", request_text, re.IGNORECASE)
        if not match:
            return None
        target = re.sub(r"\s+", " ", match.group(1).strip(" .?!"))
        if not target or len(target) < 3:
            return None
        if re.search(r"\b(it|that|those|them|this|one|ones|level|option)\b", target, re.IGNORECASE):
            return None

        subject, _unit = self._infer_followup_subject(recent_turns)
        if not subject:
            return None

        prompt = (
            f"Apply the previous discussion about {subject} to {target}. "
            "Treat this as a follow-up in the same thread, not a brand-new unrelated question. "
            "State what carries over, what changes for the new context, and give the best practical recommendation. "
            "Use plain text only, not a table. Do not invent statistics or study claims. "
            "Keep the answer concise."
        )
        combined = f"{subject} {target}"
        if self.RISK_CONTEXT_RE.search(combined):
            prompt += (
                " If legal, regulatory, safety, financial, or policy risk matters, include one short verification caution."
            )
        return prompt

    def _rewrite_contextual_reference_followup(self, request_text: str, recent_turns: List[Dict[str, Any]]) -> Optional[str]:
        assistant_text = self._recent_assistant_turn(recent_turns, require_numbered_list=True) or self._recent_assistant_turn(recent_turns) or ""
        if not assistant_text or not self._looks_like_contextual_followup(request_text):
            return None
        subject, unit = self._infer_followup_subject(recent_turns)
        if not subject:
            return None
        lowered = request_text.lower()
        list_items = self._extract_list_items(assistant_text)

        if any(phrase in lowered for phrase in ("most powerful one", "most powerful level", "which level", "what level")) and "marketing" in lowered:
            return f"Which single {unit} of {subject} is most powerful in marketing? Answer with one {unit} first, then a brief reason."
        if "how does that compare" in lowered:
            return f"How does that compare with the other {unit}s in {subject}?"
        if "would that work" in lowered or "does that work" in lowered:
            target_match = re.search(r"\bfor\s+([A-Za-z][A-Za-z0-9 '&-]{1,60})\??$", request_text, re.IGNORECASE)
            if target_match:
                target = re.sub(r"\s+too$", "", target_match.group(1).strip(), flags=re.IGNORECASE).strip()
                return f"Would that {unit} from {subject} also work for {target}?"
            return f"Would that {unit} from {subject} also work in a similar context?"
        if list_items and self._looks_like_choose_one_request(lowered):
            items_text = ", ".join(list_items[:-1]) + f", or {list_items[-1]}" if len(list_items) > 1 else list_items[0]
            return (
                f"For {subject}, choose the single strongest option from this list: {items_text}. "
                "Answer with one option first, state the criteria you used, and briefly compare it with the next strongest alternative. "
                "Use plain text only, not a table. Do not invent statistics or study claims. "
                "Keep the answer to 2 or 3 short paragraphs. "
                "If the recommendation involves legal, regulatory, safety, financial, or policy risk, include one short verification caution only if the answer has not already included one."
            )
        ordinal = self._extract_ordinal_reference(lowered)
        if ordinal is not None and (self.NUMBERED_LIST_ITEM_RE.search(assistant_text) or list_items):
            return f"Tell me more about the {ordinal} {unit} in {subject}."
        if "which one" in lowered or "what one" in lowered:
            return f"Which single {unit} of {subject} is the best fit here? Answer with one {unit} first, then a brief reason."
        return None
