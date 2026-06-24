from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from office_app.server.integration_service import IntegrationService, TokenCipher
from office_app.server.request_pipeline import RequestPipeline


class IntegrationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.env = {
            "VERIDEX_INTEGRATION_ENCRYPTION_KEY": "test-integration-key-with-at-least-thirty-two-characters",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8078/integrations/google/callback",
        }
        self.service = IntegrationService(runtime_dir=Path(self.tempdir.name), env=self.env)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_token_cipher_round_trip_and_tamper_rejection(self) -> None:
        cipher = TokenCipher(self.env["VERIDEX_INTEGRATION_ENCRYPTION_KEY"])
        encrypted = cipher.encrypt("refresh-token")
        self.assertNotIn("refresh-token", encrypted)
        self.assertEqual(cipher.decrypt(encrypted), "refresh-token")
        with self.assertRaises(Exception):
            cipher.decrypt(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))

    def test_connections_are_private_to_user(self) -> None:
        self.service.store.upsert_connection({
            "user_id": "user_a", "provider": "google", "account_email": "a@example.com", "scopes_json": "[]", "status": "connected",
            "access_token_ciphertext": "x", "refresh_token_ciphertext": "y", "access_token_expires_at": "", "created_at": "now", "updated_at": "now",
        })
        owner = self.service.list_connections("user_a")[0]
        other = self.service.list_connections("user_b")[0]
        self.assertTrue(owner["connected"])
        self.assertEqual(owner["account_email"], "a@example.com")
        self.assertFalse(other["connected"])
        self.assertEqual(other["account_email"], "")

    def test_pending_google_write_requires_matching_user_and_is_single_use(self) -> None:
        pending = self.service.create_pending_action(
            user_id="user_a", action_kind="gmail.send", payload={"to": ["to@example.com"], "subject": "Subject", "body": "Body"},
        )
        with self.assertRaises(HTTPException) as mismatch:
            self.service.confirm_action(user_id="user_b", confirmation_id=pending["confirmation_id"])
        self.assertEqual(mismatch.exception.status_code, 404)
        with self.assertRaises(HTTPException) as consumed:
            self.service.confirm_action(user_id="user_a", confirmation_id=pending["confirmation_id"])
        self.assertEqual(consumed.exception.status_code, 409)

    def test_missing_encryption_key_reports_configuration_failure(self) -> None:
        service = IntegrationService(runtime_dir=Path(self.tempdir.name) / "missing-key", env={})
        with self.assertRaises(HTTPException) as context:
            service.begin_google_connect(user_id="user_a", session_id="session_a")
        self.assertEqual(context.exception.status_code, 503)

    def test_google_oauth_success_stores_only_encrypted_credentials(self) -> None:
        authorization_url = self.service.begin_google_connect(user_id="user_a", session_id="session_a")
        state = authorization_url.split("state=", 1)[1].split("&", 1)[0]
        state = state.replace("%2E", ".")
        with patch.object(self.service, "_post_form", return_value={"access_token": "access-token", "refresh_token": "refresh-token", "expires_in": 3600, "scope": "email"}), patch.object(self.service, "_google_json", return_value={"email": "user@example.com"}):
            result = self.service.complete_google_connect(code="code", state=state)
        stored = self.service.store.get_connection("user_a", "google")
        self.assertEqual(result["account_email"], "user@example.com")
        self.assertIsNotNone(stored)
        self.assertNotIn("access-token", str(stored["access_token_ciphertext"]))
        self.assertNotIn("refresh-token", str(stored["refresh_token_ciphertext"]))

    def test_read_only_chat_routes_target_google_tools(self) -> None:
        pipeline = RequestPipeline(
            kernel=None,
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-06-24T00:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        calendar = pipeline.route_integration_request("workspace", "show my calendar")
        gmail = pipeline.route_integration_request("workspace", "search my emails for invoices")
        self.assertEqual(calendar["tool"], "office.calendar_list")
        self.assertEqual(gmail["tool"], "office.gmail_search")
        self.assertEqual(gmail["arguments"]["query"], "invoices")

    def test_direct_nancy_email_send_routes_to_confirmation_tool(self) -> None:
        pipeline = RequestPipeline(
            kernel=None,
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-06-24T00:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        route = pipeline.route_nancy_direct_request(
            "workspace",
            "Nancy, send an email to jane@example.com subject: Welcome body: Thanks for trying Veridex.",
        )
        self.assertIsNotNone(route)
        assert route is not None
        self.assertEqual(route["tool"], "office.gmail_send")
        self.assertEqual(route["arguments"]["to"], ["jane@example.com"])
        self.assertEqual(route["arguments"]["assistant_persona"], "Nancy")


if __name__ == "__main__":
    unittest.main()
