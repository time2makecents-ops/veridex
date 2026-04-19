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
    def _merge_context_prompt(user_prompt: str, context: Optional[Dict[str, Any]]) -> str:
        if not context:
            return user_prompt.strip()
        context_block = json.dumps(context, indent=2, sort_keys=True)
        return f"{user_prompt.strip()}\n\nContext:\n{context_block}"

