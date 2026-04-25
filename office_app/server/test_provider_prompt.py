from __future__ import annotations

import unittest

from office_app.server.providers.base_provider import BaseProvider, ProviderResult


class PromptProbeProvider(BaseProvider):
    provider_name = "probe"

    def __init__(self) -> None:
        super().__init__(api_key="test", model_name="probe-model", timeout_seconds=1)
        self.last_prompt = ""

    def generate_response(self, *, system_prompt, user_prompt, context=None, settings=None) -> ProviderResult:
        self.last_prompt = self._merge_context_prompt(user_prompt, context)
        return ProviderResult(provider=self.provider_name, model=self.model_name, text=self.last_prompt, raw={})


class ProviderPromptTests(unittest.TestCase):
    def test_context_prompt_is_plain_text(self) -> None:
        provider = PromptProbeProvider()
        result = provider.generate_response(
            system_prompt="system",
            user_prompt="hello there",
            context={
                "workspace_id": "ws_1",
                "active_room": "sales_department",
                "active_persona": "Sales Director",
                "recent_turns_text": ["Alice [user]: hello", "Sales Director [assistant]: hi"],
                "nested": {"foo": "bar"},
            },
        )
        self.assertIn("Context summary:", result.text)
        self.assertIn("workspace_id: ws_1", result.text)
        self.assertIn("recent_turns_text: Alice [user]: hello, Sales Director [assistant]: hi", result.text)
        self.assertNotIn("{", result.text)
        self.assertNotIn("}", result.text)


if __name__ == "__main__":
    unittest.main()
