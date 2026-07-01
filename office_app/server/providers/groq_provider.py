from __future__ import annotations

import os
from typing import Any, Dict, Optional

from office_app.server.providers.base_provider import (
    BaseProvider,
    ProviderRequestError,
    ProviderResult,
    ProviderUnavailableError,
)


class GroqProvider(BaseProvider):
    provider_name = "groq"
    default_model = "llama-3.1-8b-instant"
    models_url = "https://api.groq.com/openai/v1/models"

    def __init__(self, *, api_key: Optional[str] = None, model_name: str = default_model, timeout_seconds: int = 30):
        super().__init__(api_key=api_key, model_name=model_name, timeout_seconds=timeout_seconds)

    @classmethod
    def from_env(cls, *, timeout_seconds: int = 30) -> "GroqProvider":
        return cls(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name=os.getenv("GROQ_MODEL", cls.default_model),
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
            raise ProviderUnavailableError("Groq API key is not configured.")

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
        url = "https://api.groq.com/openai/v1/chat/completions"
        data = self._post_json(
            url,
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        text = self._extract_text(data)
        return ProviderResult(provider=self.provider_name, model=self.model_name, text=text, raw=data)

    def connectivity_diagnostic(self) -> Dict[str, Any]:
        if not self.available():
            raise ProviderUnavailableError("Groq API key is not configured.")

        try:
            data = self._get_json(
                self.models_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except ProviderRequestError as exc:
            message = str(exc)
            lowered = message.lower()
            kind = "request_blocked"
            if "status=401" in lowered or "invalid api key" in lowered or "unauthorized" in lowered:
                kind = "bad_key"
            elif "status=403" in lowered and ("1010" in lowered or "access denied" in lowered or "forbidden" in lowered):
                kind = "request_blocked"
            return {
                "ok": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "kind": kind,
                "message": message,
            }

        rows = data.get("data")
        rows = rows if isinstance(rows, list) else []
        available_models = [
            str(item.get("id") or "").strip()
            for item in rows
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        if self.model_name not in available_models:
            return {
                "ok": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "kind": "model_permission_problem",
                "message": f"groq model permission problem model={self.model_name}",
                "available_models": available_models[:50],
            }
        return {
            "ok": True,
            "provider": self.provider_name,
            "model": self.model_name,
            "kind": "ok",
            "message": f"groq connectivity ok model={self.model_name}",
            "available_models": available_models[:50],
        }

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderRequestError("groq returned no choices.")
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "").strip()
        if not text:
            raise ProviderRequestError("groq returned an empty response.")
        return text
