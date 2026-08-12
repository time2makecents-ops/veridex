from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from office_app.server.providers.base_provider import (
    BaseProvider,
    ProviderRequestError,
    ProviderResult,
    ProviderUnavailableError,
)


TRUTHY = {"1", "true", "yes", "on"}


class CodexCliProvider(BaseProvider):
    """Veridex model provider backed by the user's authenticated Codex CLI."""

    provider_name = "codex_cli"

    def __init__(
        self,
        *,
        gateway_path: str,
        python_command: str = sys.executable,
        enabled: bool = True,
        timeout_seconds: int = 255,
    ):
        super().__init__(api_key=None, model_name="task-routed", timeout_seconds=timeout_seconds)
        self.gateway_path = str(gateway_path or "").strip()
        self.python_command = str(python_command or sys.executable).strip()
        self.enabled = bool(enabled)

    @classmethod
    def from_env(cls, *, timeout_seconds: int = 30) -> "CodexCliProvider":
        gateway_timeout = max(10, int(str(os.getenv("VERIDEX_CODEX_TIMEOUT_SECONDS", "240") or "240")))
        provider_timeout = max(
            timeout_seconds,
            int(str(os.getenv("VERIDEX_CODEX_PROVIDER_TIMEOUT_SECONDS", gateway_timeout + 15))),
        )
        return cls(
            gateway_path=os.getenv("VERIDEX_CODEX_GATEWAY", r"C:\codex2veridex\codex_gateway.py"),
            python_command=os.getenv("VERIDEX_CODEX_PYTHON", sys.executable),
            enabled=str(os.getenv("VERIDEX_CODEX_ENABLED", "true")).strip().lower() in TRUTHY,
            timeout_seconds=provider_timeout,
        )

    def available(self) -> bool:
        if not self.enabled or not self.gateway_path:
            return False
        if not Path(self.gateway_path).is_file():
            return False
        if not (Path(self.python_command).is_file() or shutil.which(self.python_command)):
            return False
        return bool(shutil.which(str(os.getenv("VERIDEX_CODEX_COMMAND", "codex") or "codex")))

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        if not self.available():
            raise ProviderUnavailableError("Codex CLI gateway is not available.")

        effective_settings = dict(settings or {})
        payload = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "context": context or {},
            "settings": {
                "temperature": effective_settings.get("temperature"),
                "max_output_tokens": effective_settings.get("max_output_tokens"),
            },
            "task_type": str(effective_settings.get("_task_type") or "conversation"),
        }
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                [self.python_command, self.gateway_path],
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderRequestError(f"codex_cli request timed out after {self.timeout_seconds} seconds") from exc
        except OSError as exc:
            raise ProviderRequestError(f"codex_cli gateway could not be started: {exc}") from exc

        data: Dict[str, Any] = {}
        try:
            parsed = json.loads(str(completed.stdout or "").strip())
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}
        if completed.returncode != 0 or not data.get("ok"):
            detail = str(data.get("error") or completed.stderr or "gateway failed")
            detail = self._sanitize_error_detail(detail)
            raise ProviderRequestError(f"codex_cli request failed: {detail}")

        text = str(data.get("text") or "").strip()
        if not text:
            raise ProviderRequestError("codex_cli returned an empty response.")
        model = str(data.get("model") or self.model_name).strip()
        return ProviderResult(provider=self.provider_name, model=model, text=text, raw=data)
