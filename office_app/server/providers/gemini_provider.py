from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import quote

from office_app.server.providers.base_provider import (
    BaseProvider,
    ProviderRequestError,
    ProviderResult,
    ProviderUnavailableError,
)


class GeminiProvider(BaseProvider):
    provider_name = "gemini"
    default_model = "gemini-2.5-flash-lite"

    def __init__(self, *, api_key: Optional[str] = None, model_name: str = default_model, timeout_seconds: int = 30):
        super().__init__(api_key=api_key, model_name=model_name, timeout_seconds=timeout_seconds)

    @classmethod
    def from_env(cls, *, timeout_seconds: int = 30) -> "GeminiProvider":
        return cls(
            api_key=os.getenv("GEMINI_API_KEY"),
            model_name=os.getenv("GEMINI_MODEL", cls.default_model),
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
            raise ProviderUnavailableError("Gemini API key is not configured.")

        merged_system_prompt = self._merge_system_context(system_prompt, context)
        payload = {
            "systemInstruction": {
                "parts": [{"text": merged_system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt.strip()}],
                }
            ],
            "generationConfig": {
                "temperature": float((settings or {}).get("temperature", 0.3)),
                "maxOutputTokens": int((settings or {}).get("max_output_tokens", 512)),
            },
        }

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model_name, safe='')}:generateContent?key={quote(self.api_key, safe='')}"
        )
        data = self._post_json(url, payload)
        text = self._extract_text(data)
        return ProviderResult(provider=self.provider_name, model=self.model_name, text=text, raw=data)

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason") or "no candidates returned"
            raise ProviderRequestError(f"gemini returned no text: {reason}")

        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [str(part.get("text", "")).strip() for part in parts if isinstance(part, dict) and part.get("text")]
        text = "\n".join([part for part in texts if part]).strip()
        if not text:
            raise ProviderRequestError("gemini returned an empty response.")
        return text
