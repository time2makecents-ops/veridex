from __future__ import annotations

import os
from typing import Any, Dict, Optional

from office_app.server.providers.base_provider import (
    BaseProvider,
    ProviderRequestError,
    ProviderResult,
    ProviderUnavailableError,
)


class OpenRouterProvider(BaseProvider):
    provider_name = "openrouter"
    default_model = "openrouter/free"

    def __init__(self, *, api_key: Optional[str] = None, model_name: str = default_model, timeout_seconds: int = 30):
        super().__init__(api_key=api_key, model_name=model_name, timeout_seconds=timeout_seconds)

    @classmethod
    def from_env(cls, *, timeout_seconds: int = 30) -> "OpenRouterProvider":
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model_name=os.getenv("OPENROUTER_MODEL", cls.default_model),
            timeout_seconds=timeout_seconds,
        )

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        if not self.available():
            raise ProviderUnavailableError("OpenRouter API key is not configured.")

        merged_system_prompt = self._merge_system_context(system_prompt, context)
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": merged_system_prompt},
                {"role": "user", "content": user_prompt.strip()},
            ],
            "temperature": float((settings or {}).get("temperature", 0.3)),
            "max_tokens": int((settings or {}).get("max_output_tokens", 512)),
        }
        data = self._post_json(
            "https://openrouter.ai/api/v1/chat/completions",
            payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://veridex.local",
                "X-Title": "Veridex",
            },
        )
        text = self._extract_text(data)
        return ProviderResult(provider=self.provider_name, model=self.model_name, text=text, raw=data)

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderRequestError("openrouter returned no choices.")
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "").strip()
        if not text:
            raise ProviderRequestError("openrouter returned an empty response.")
        return text
