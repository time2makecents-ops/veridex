from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from office_app.server.model_router import ModelRouter, ModelRoutingError
from office_app.server.providers.base_provider import BaseProvider, ProviderResult


class FakeProvider(BaseProvider):
    provider_name = "fake"

    def __init__(self, *, name: str, text: str, available: bool = True, fail: bool = False):
        super().__init__(api_key="test", model_name=name, timeout_seconds=1)
        self.provider_name = name
        self._text = text
        self._available = available
        self._fail = fail

    def available(self) -> bool:
        return self._available

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        if self._fail:
            raise RuntimeError("boom")
        return ProviderResult(provider=self.provider_name, model=self.model_name, text=self._text, raw={})


class ModelRouterTests(unittest.TestCase):
    def test_forwards_task_type_to_provider_settings(self) -> None:
        provider = FakeProvider(name="codex_cli", text="primary")
        captured = {}
        original = provider.generate_response

        def capture(**kwargs):
            captured.update(kwargs.get("settings") or {})
            return original(**kwargs)

        provider.generate_response = capture  # type: ignore[method-assign]
        router = ModelRouter([provider])
        result = router.generate_response(
            system_prompt="system",
            user_prompt="plan this",
            settings={"temperature": 0.2},
            task_type="planning",
        )
        self.assertEqual(result.task_type, "planning")
        self.assertEqual(captured["_task_type"], "planning")

    def test_uses_first_available_provider(self) -> None:
        router = ModelRouter([FakeProvider(name="gemini", text="primary"), FakeProvider(name="groq", text="fallback")])
        result = router.generate_response(
            system_prompt="system",
            user_prompt="hello",
            context={"workspace_id": "default"},
            settings={},
        )
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.text, "primary")
        self.assertFalse(result.fallback_used)

    def test_falls_back_to_second_provider(self) -> None:
        router = ModelRouter(
            [
                FakeProvider(name="gemini", text="primary", available=False),
                FakeProvider(name="groq", text="fallback"),
            ]
        )
        result = router.generate_response(
            system_prompt="system",
            user_prompt="hello",
            context={"workspace_id": "default"},
            settings={},
        )
        self.assertEqual(result.provider, "groq")
        self.assertTrue(result.fallback_used)

    def test_raises_when_no_provider_is_available(self) -> None:
        router = ModelRouter([FakeProvider(name="gemini", text="primary", available=False)])
        with self.assertRaises(ModelRoutingError):
            router.generate_response(
                system_prompt="system",
                user_prompt="hello",
                context={"workspace_id": "default"},
                settings={},
            )


if __name__ == "__main__":
    unittest.main()
