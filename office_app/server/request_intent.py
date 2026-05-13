from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Pattern


PlaceQueryNormalizer = Callable[[str], Dict[str, Any]]
ExplicitRoomNavigator = Callable[[str], bool]


@dataclass(frozen=True)
class RequestIntentConfig:
    artifact_create_triggers: tuple[str, ...]
    artifact_list_triggers: tuple[str, ...]
    artifact_open_triggers: tuple[str, ...]
    factual_entity_lookup_patterns: tuple[Pattern[str], ...]
    factual_entity_search_patterns: tuple[Pattern[str], ...]
    file_id_re: Pattern[str]
    file_name_re: Pattern[str]
    intent_advice_hints: tuple[str, ...]
    intent_meta_hints: tuple[str, ...]
    ocr_explicit_hints: tuple[str, ...]
    room_status_hints: tuple[str, ...]
    search_business_advice_hints: tuple[str, ...]
    search_place_hints: tuple[str, ...]
    search_review_hints: tuple[str, ...]
    search_web_hints: tuple[str, ...]
    session_create_hints: tuple[str, ...]


class RequestIntentAnalyzer:
    def __init__(
        self,
        config: RequestIntentConfig,
        *,
        normalize_place_query: PlaceQueryNormalizer,
        is_explicit_room_navigation: ExplicitRoomNavigator,
    ) -> None:
        self.config = config
        self.normalize_place_query = normalize_place_query
        self.is_explicit_room_navigation = is_explicit_room_navigation

    def place_search_signals(self, request_text: str) -> Dict[str, Any]:
        text = str(request_text or "").strip()
        lowered = text.lower().strip()
        place_query = self.normalize_place_query(request_text)
        has_place_hint = any(hint in lowered for hint in self.config.search_place_hints)
        location_signal = bool(
            place_query["location"]
            or re.search(r"\b(?:near me|nearby|nearest)\b", lowered)
            or re.search(r"\baround\s+[A-Za-z]", text, re.IGNORECASE)
        )
        discovery_signal = bool(
            re.match(r"^(?:find|show me|list|recommend|give me)\b", lowered)
            or re.search(r"\b(?:near me|nearby|nearest)\b", lowered)
            or re.match(r"^(?:where is|where are)\b", lowered)
            or "reviews for" in lowered
            or re.search(r"\bwhich\s+ones?\b", lowered)
            or re.search(r"\bwhich\s+ones?\s+are\s+they\b", lowered)
            or (has_place_hint and location_signal and re.search(r"\b(?:major|main|largest|biggest|top|best|notable)\b", lowered))
        )
        explicit_review_signal = any(hint in lowered for hint in self.config.search_review_hints)
        review_signal = bool(
            explicit_review_signal or re.search(r"\b(?:best|top|highest rated|top rated|best rated)\b", lowered)
        )
        return {
            "has_place_hint": has_place_hint,
            "discovery_signal": discovery_signal,
            "explicit_review_signal": explicit_review_signal,
            "review_signal": review_signal,
            "location_signal": location_signal,
            "place_query": place_query,
        }

    def classify_intent(self, request_text: str) -> str:
        text = str(request_text or "").lower().strip()
        if not text:
            return "task"
        if self.is_meta_intent(text):
            return "meta"
        if self.is_explicit_task_intent(request_text):
            return "task"
        if self.is_advice_intent(text):
            return "advice"
        return "task"

    def is_meta_intent(self, text: str) -> bool:
        if any(hint in text for hint in self.config.intent_meta_hints):
            return True
        return bool(
            re.search(
                r"\b(?:why|how|what)\s+(?:did|do|are)\s+you\s+(?:respond|answer|decide|choos|think|reason)",
                text,
            )
        )

    def is_advice_intent(self, text: str) -> bool:
        if any(hint in text for hint in self.config.intent_advice_hints):
            return True
        if re.search(r"\bwhat\s+companies\s+should\s+i\s+study\b", text):
            return True
        if re.search(r"\bwhat\s+makes\b", text):
            return True
        if re.match(r"^(?:how|why)\s+(?:do|does|can|could|should|would|is|are)\b", text):
            return True
        if re.match(r"^(?:what|which)\s+is\s+the\s+best\s+way\b", text):
            return True
        advice_terms = (
            "advice",
            "approach",
            "best practice",
            "criteria",
            "explain",
            "idea",
            "improve",
            "increase",
            "marketing",
            "model",
            "plan",
            "strategy",
            "successful",
            "tip",
        )
        question_starter = re.match(r"^(?:what|which|tell me|can you explain|help me)\b", text)
        return bool(question_starter and any(term in text for term in advice_terms))

    def is_explicit_task_intent(self, request_text: str) -> bool:
        text = str(request_text or "").lower().strip()
        if not text:
            return False
        if self.is_explicit_room_navigation(text):
            return True
        if any(hint in text for hint in self.config.room_status_hints):
            return True
        if any(hint in text for hint in self.config.session_create_hints):
            return True
        if any(
            trigger in text
            for trigger in (
                self.config.artifact_create_triggers
                + self.config.artifact_list_triggers
                + self.config.artifact_open_triggers
            )
        ):
            return True
        if any(hint in text for hint in self.config.ocr_explicit_hints):
            return True
        if any(hint in text for hint in self.config.search_web_hints):
            return True

        entity_request = self.extract_factual_entity_request(request_text)
        if entity_request is not None and entity_request.get("search_requested"):
            return True

        place_signals = self.place_search_signals(request_text)
        if place_signals["has_place_hint"]:
            return bool(
                (place_signals["discovery_signal"] or place_signals["review_signal"])
                and (place_signals["location_signal"] or place_signals["explicit_review_signal"])
            )
        return False

    def is_search_capability_question(self, text: str) -> bool:
        return bool(
            re.match(
                r"^(?:can|could|do)\s+you\s+(?:actually\s+|really\s+)?"
                r"(?:search(?:\s+the)?\s+(?:internet|web)|search\s+online|look\s+things\s+up|check\s+online|"
                r"use(?:\s+the)?\s+(?:internet|web)|access(?:\s+the)?\s+(?:internet|web)|browse(?:\s+the)?\s+web)\??$",
                text,
            )
        )

    def extract_factual_entity_request(self, request_text: str) -> Dict[str, Any] | None:
        text = str(request_text or "").strip()
        lowered = text.lower()
        if not text or self.is_advice_intent(lowered):
            return None
        place_signals = self.place_search_signals(request_text)
        if place_signals["has_place_hint"] and (place_signals["discovery_signal"] or place_signals["review_signal"]):
            return None

        for pattern in self.config.factual_entity_search_patterns:
            match = pattern.match(text)
            if not match:
                continue
            subject = self.clean_entity_subject(match.group(1))
            if self.looks_like_specific_entity(subject):
                return {
                    "entity_subject": subject,
                    "search_requested": True,
                }

        for pattern in self.config.factual_entity_lookup_patterns:
            match = pattern.match(text)
            if not match:
                continue
            subject = self.clean_entity_subject(match.group(1))
            if self.looks_like_specific_entity(subject):
                return {
                    "entity_subject": subject,
                    "search_requested": False,
                }
        return None

    def clean_entity_subject(self, subject: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(subject or "").strip(" .?!,:;"))
        cleaned = re.sub(
            r"\s+(?:and\s+give\s+me\s+information(?:\s+about\s+the\s+company)?|and\s+tell\s+me\s+about\s+the\s+company|please)$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+(?:company|business|brand)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(?:the\s+)?(?:company|business|brand)\s+", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip(" .?!,:;")

    def looks_like_specific_entity(self, subject: str) -> bool:
        text = re.sub(r"\s+", " ", str(subject or "").strip()).lower()
        if not text:
            return False
        if self.config.file_id_re.search(text) or self.config.file_name_re.search(text):
            return False
        if len(text.split()) > 6:
            return False
        if re.search(
            r"\b(restaurant marketing|customer retention|sales process|strong brand|brand strategy|marketing strategy|"
            r"marketing ideas|ideas|strategy|branding|brand|marketing|sales|retention|process|successful|success|"
            r"file|document|session|workspace|room|response)\b",
            text,
        ):
            return False
        if text in {"company", "business", "brand", "restaurant", "restaurants"}:
            return False
        return True
