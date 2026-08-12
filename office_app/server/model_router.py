from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from office_app.server.env_loader import load_env_files
from office_app.server.providers.base_provider import BaseProvider, ProviderError, ProviderRequestError, ProviderResult, ProviderUnavailableError
from office_app.server.providers.codex_cli_provider import CodexCliProvider
from office_app.server.providers.gemini_provider import GeminiProvider
from office_app.server.providers.groq_provider import GroqProvider
from office_app.server.providers.openrouter_provider import OpenRouterProvider


@dataclass(frozen=True)
class ModelRouteResult:
    provider: str
    model: str
    text: str
    task_type: str
    fallback_used: bool
    attempts: List[str]
    reasoning_effort: str = ""


class ModelRoutingError(ProviderError):
    def __init__(self, message: str, *, attempts: Optional[List[str]] = None):
        super().__init__(message)
        self.attempts = attempts or []


class ModelRouter:
    def __init__(
        self,
        providers: Sequence[BaseProvider],
        openrouter_scaffold: Optional[BaseProvider] = None,
        *,
        allow_openrouter_by_default: bool = False,
    ):
        self.providers = list(providers)
        self.openrouter_scaffold = openrouter_scaffold
        self.allow_openrouter_by_default = allow_openrouter_by_default
        self.provider_map = {provider.provider_name: provider for provider in self.providers}
        if openrouter_scaffold is not None:
            self.provider_map[openrouter_scaffold.provider_name] = openrouter_scaffold

    @classmethod
    def from_env(cls, *, timeout_seconds: int = 30) -> "ModelRouter":
        root_dir = Path(__file__).resolve().parents[2]
        pkg_dir = root_dir / "office_app"
        load_env_files(
            [
                root_dir / ".env",
                root_dir / ".env.local",
                pkg_dir / ".env",
                pkg_dir / ".env.local",
            ]
        )
        providers: List[BaseProvider] = [CodexCliProvider.from_env(timeout_seconds=timeout_seconds)]
        allow_external_fallback = str(os.getenv("VERIDEX_MODEL_ALLOW_EXTERNAL_FALLBACK", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if allow_external_fallback:
            providers.extend(
                [
                    GeminiProvider.from_env(timeout_seconds=timeout_seconds),
                    GroqProvider.from_env(timeout_seconds=timeout_seconds),
                ]
            )
        openrouter = OpenRouterProvider.from_env(timeout_seconds=timeout_seconds)
        allow_openrouter = str(os.getenv("VERIDEX_MODEL_ALLOW_OPENROUTER", "")).strip().lower() in {"1", "true", "yes", "on"}
        return cls(providers, openrouter_scaffold=openrouter, allow_openrouter_by_default=allow_openrouter)

    def _ordered_providers(self, *, task_type: str, settings: Optional[Dict[str, Any]] = None) -> List[BaseProvider]:
        settings = settings or {}
        requested_provider = str(settings.get("provider") or "").strip().lower()
        task_map = settings.get("provider_by_task_type")
        explicit = ""
        if isinstance(task_map, dict):
            explicit = str(task_map.get(task_type) or "").strip().lower()

        ordered: List[BaseProvider] = []
        for candidate in [explicit, requested_provider]:
            if candidate and candidate in self.provider_map:
                provider = self.provider_map[candidate]
                if provider not in ordered:
                    ordered.append(provider)

        for provider in self.providers:
            if provider not in ordered:
                ordered.append(provider)

        allow_openrouter = self.allow_openrouter_by_default or bool(settings.get("allow_openrouter"))
        if allow_openrouter and self.openrouter_scaffold is not None and self.openrouter_scaffold not in ordered:
            ordered.append(self.openrouter_scaffold)

        return ordered

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        attempts: List[str] = []
        ordered = self._ordered_providers(task_type=task_type, settings=settings)
        provider_settings = dict(settings or {})
        provider_settings["_task_type"] = task_type

        for index, provider in enumerate(ordered):
            if not provider.available():
                attempts.append(f"{provider.provider_name}: unavailable")
                continue

            try:
                result = provider.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    context=context,
                    settings=provider_settings,
                )
                return ModelRouteResult(
                    provider=result.provider,
                    model=result.model,
                    text=result.text,
                    task_type=task_type,
                    fallback_used=index > 0,
                    attempts=attempts,
                    reasoning_effort=str(result.raw.get("reasoning_effort") or "").strip()
                    if isinstance(result.raw, dict)
                    else "",
                )
            except ProviderError as exc:
                attempts.append(f"{provider.provider_name}: {exc}")

        raise ModelRoutingError(
            "No model provider available or all providers failed.",
            attempts=attempts,
        )
