from __future__ import annotations

import io
import unittest
from unittest.mock import patch
from urllib import error as urllib_error

from office_app.server.providers.base_provider import BaseProvider, ProviderRequestError
from office_app.server.providers.groq_provider import GroqProvider


class DummyProvider(BaseProvider):
    provider_name = "dummy"

    def generate_response(self, *, system_prompt, user_prompt, context=None, settings=None):
        raise NotImplementedError


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.body.encode("utf-8")


class ProviderConnectivityTests(unittest.TestCase):
    def test_base_provider_adds_default_user_agent_header(self) -> None:
        provider = DummyProvider(api_key="test", model_name="dummy-model", timeout_seconds=1)
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["user_agent"] = request.headers.get("User-agent")
            captured["authorization"] = request.headers.get("Authorization")
            return FakeResponse("{}")

        with patch("office_app.server.providers.base_provider.urllib_request.urlopen", side_effect=fake_urlopen):
            provider._get_json("https://example.com/models", headers={"Authorization": "Bearer test"})

        self.assertEqual(captured["user_agent"], "Veridex/0.1 (+https://veridex.local)")
        self.assertEqual(captured["authorization"], "Bearer test")

    def test_base_provider_does_not_overwrite_provider_user_agent(self) -> None:
        provider = DummyProvider(api_key="test", model_name="dummy-model", timeout_seconds=1)
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["user_agent"] = request.headers.get("User-agent")
            return FakeResponse("{}")

        with patch("office_app.server.providers.base_provider.urllib_request.urlopen", side_effect=fake_urlopen):
            provider._get_json("https://example.com/models", headers={"User-Agent": "CustomUA/1.0"})

        self.assertEqual(captured["user_agent"], "CustomUA/1.0")

    def test_base_provider_http_error_includes_provider_status_model_and_sanitized_body(self) -> None:
        provider = DummyProvider(api_key="secret123", model_name="dummy-model", timeout_seconds=1)
        error_body = '{"error":"forbidden Bearer secret123 api_key=secret123"}'
        http_error = urllib_error.HTTPError(
            url="https://example.com",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=io.BytesIO(error_body.encode("utf-8")),
        )

        with patch("office_app.server.providers.base_provider.urllib_request.urlopen", side_effect=http_error):
            with self.assertRaises(ProviderRequestError) as raised:
                provider._post_json("https://example.com", {"hello": "world"})

        message = str(raised.exception)
        self.assertIn("dummy request failed", message)
        self.assertIn("model=dummy-model", message)
        self.assertIn("status=403", message)
        self.assertIn("body=", message)
        self.assertNotIn("secret123", message)
        self.assertIn("Bearer ***", message)

    def test_groq_connectivity_diagnostic_reports_bad_key(self) -> None:
        provider = GroqProvider(api_key="test", model_name="llama-3.1-8b-instant", timeout_seconds=1)
        with patch.object(provider, "_get_json", side_effect=ProviderRequestError("groq request failed model=llama-3.1-8b-instant status=401 body=unauthorized")):
            result = provider.connectivity_diagnostic()
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "bad_key")

    def test_groq_connectivity_diagnostic_reports_request_blocked(self) -> None:
        provider = GroqProvider(api_key="test", model_name="llama-3.1-8b-instant", timeout_seconds=1)
        with patch.object(provider, "_get_json", side_effect=ProviderRequestError("groq request failed model=llama-3.1-8b-instant status=403 body=error code: 1010")):
            result = provider.connectivity_diagnostic()
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "request_blocked")

    def test_groq_connectivity_diagnostic_reports_model_permission_problem(self) -> None:
        provider = GroqProvider(api_key="test", model_name="llama-3.1-8b-instant", timeout_seconds=1)
        with patch.object(provider, "_get_json", return_value={"data": [{"id": "mixtral-8x7b"}]}):
            result = provider.connectivity_diagnostic()
        self.assertFalse(result["ok"])
        self.assertEqual(result["kind"], "model_permission_problem")
        self.assertIn("mixtral-8x7b", result["available_models"])

    def test_groq_connectivity_diagnostic_reports_ok_when_model_is_listed(self) -> None:
        provider = GroqProvider(api_key="test", model_name="llama-3.1-8b-instant", timeout_seconds=1)
        with patch.object(provider, "_get_json", return_value={"data": [{"id": "llama-3.1-8b-instant"}]}):
            result = provider.connectivity_diagnostic()
        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "ok")


if __name__ == "__main__":
    unittest.main()
