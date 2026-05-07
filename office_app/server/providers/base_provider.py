from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request


class ProviderError(RuntimeError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    text: str
    raw: Dict[str, Any]


class BaseProvider(ABC):
    provider_name: str = "provider"

    def __init__(self, *, api_key: Optional[str], model_name: str, timeout_seconds: int = 30):
        self.api_key = (api_key or "").strip()
        self.model_name = model_name.strip()
        self.timeout_seconds = timeout_seconds

    def available(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        raise NotImplementedError

    def _post_json(self, url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **(headers or {}),
            },
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError(f"{self.provider_name} request failed: {exc.code} {detail}") from exc
        except urllib_error.URLError as exc:
            raise ProviderRequestError(f"{self.provider_name} request failed: {exc.reason}") from exc

    @staticmethod
    def _context_summary(context: Optional[Dict[str, Any]]) -> str:
        if not context:
            return ""
        def _scalar_text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, str):
                return value.strip()
            return str(value).strip()

        def _list_text(values: list[Any], depth: int) -> str:
            items: list[str] = []
            for value in values[:5]:
                text = _value_text(value, depth + 1)
                if text:
                    items.append(text)
            return ", ".join(items)

        def _dict_text(mapping: Dict[str, Any], depth: int) -> str:
            lines: list[str] = []
            for key in sorted(mapping.keys()):
                text = _value_text(mapping[key], depth + 1)
                if text:
                    lines.append(f"{key}: {text}")
            return "; ".join(lines)

        def _value_text(value: Any, depth: int = 0) -> str:
            if depth > 1:
                return ""
            if isinstance(value, dict):
                return _dict_text(value, depth)
            if isinstance(value, list):
                return _list_text(value, depth)
            return _scalar_text(value)

        lines: list[str] = []
        for key in sorted(context.keys()):
            if key in {"recent_turns", "room_behavior_memory_refs"}:
                continue
            if key == "room_behavior_memory_text":
                memory_text = _scalar_text(context[key]).strip()
                if memory_text:
                    lines.append(f"Active room behavior memory:\n{memory_text[:3000]}")
                continue
            if key == "conversation_history_text":
                history_text = _scalar_text(context[key]).strip()
                if history_text:
                    lines.append(f"Conversation history:\n{history_text[:5000]}")
                continue
            if key == "session_summary_text":
                summary_text = _scalar_text(context[key]).strip()
                if summary_text:
                    lines.append(f"Session summary: {summary_text[:1400]}")
                continue
            value_text = _value_text(context[key]).strip()
            if value_text:
                lines.append(f"{key}: {value_text[:300]}")
        if not lines:
            return ""
        return "\n".join(lines[:12])

    @classmethod
    def _merge_system_context(cls, system_prompt: str, context: Optional[Dict[str, Any]]) -> str:
        summary = cls._context_summary(context)
        if not summary:
            return system_prompt.strip()
        return f"{system_prompt.strip()}\n\nContext summary:\n{summary}"

    @staticmethod
    def _merge_context_prompt(user_prompt: str, context: Optional[Dict[str, Any]]) -> str:
        return user_prompt.strip()
