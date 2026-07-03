from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from office_app.server.integration_service import IntegrationService, TokenCipher
from office_app.server.request_pipeline import RequestPipeline


def _gmail_body_data(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


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

    def test_gmail_search_enriches_messages_with_sender_subject_date_and_snippet(self) -> None:
        responses = [
            {"messages": [{"id": "msg_1", "threadId": "thr_1"}]},
            {
                "id": "msg_1",
                "threadId": "thr_1",
                "snippet": "Latest project status",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Alex <alex@example.com>"},
                        {"name": "Subject", "value": "Project update"},
                        {"name": "Date", "value": "Thu, 2 Jul 2026 08:00:00 -0700"},
                    ]
                },
            },
        ]
        with patch.object(self.service, "_google_authorized_json", side_effect=responses):
            messages = self.service.gmail_search("user_a", "in:inbox", 10)
        self.assertEqual(messages[0]["id"], "msg_1")
        self.assertEqual(messages[0]["from"], "Alex <alex@example.com>")
        self.assertEqual(messages[0]["subject"], "Project update")
        self.assertEqual(messages[0]["date"], "Thu, 2 Jul 2026 08:00:00 -0700")
        self.assertEqual(messages[0]["snippet"], "Latest project status")
        contacts = self.service.search_contacts("user_a", "Alex")
        self.assertEqual(contacts[0]["email"], "alex@example.com")
        self.assertEqual(contacts[0]["display_name"], "Alex")

    def test_address_book_save_search_and_alias_resolution(self) -> None:
        saved = self.service.save_contact(
            "user_a",
            email="time2makecents@gmail.com",
            display_name="James Willis",
            aliases=["James", "Time2"],
            source="manual",
        )
        self.assertEqual(saved["email"], "time2makecents@gmail.com")

        by_name = self.service.search_contacts("user_a", "James")
        by_alias = self.service.search_contacts("user_a", "Time2")

        self.assertEqual(by_name[0]["email"], "time2makecents@gmail.com")
        self.assertEqual(by_alias[0]["display_name"], "James Willis")

    def test_gmail_read_returns_readable_headers_and_plain_text_body(self) -> None:
        encoded = "SGVsbG8gZnJvbSBHbWFpbC4".rstrip("=")
        response = {
            "id": "msg_1",
            "threadId": "thr_1",
            "snippet": "Hello from Gmail.",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Alex <alex@example.com>"},
                    {"name": "To", "value": "JR <jr@example.com>"},
                    {"name": "Subject", "value": "Project update"},
                    {"name": "Date", "value": "Thu, 2 Jul 2026 08:00:00 -0700"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": encoded},
                    }
                ],
            },
        }
        with patch.object(self.service, "_google_authorized_json", return_value=response):
            message = self.service.gmail_read("user_a", "msg_1")
        self.assertEqual(message["id"], "msg_1")
        self.assertEqual(message["from"], "Alex <alex@example.com>")
        self.assertEqual(message["to"], "JR <jr@example.com>")
        self.assertEqual(message["subject"], "Project update")
        self.assertEqual(message["body_text"], "Hello from Gmail.")

    def test_gmail_thread_read_returns_readable_messages(self) -> None:
        encoded = "SGVsbG8gZnJvbSB0aGUgdGhyZWFkLg".rstrip("=")
        response = {
            "id": "thread_1",
            "messages": [
                {
                    "id": "msg_1",
                    "threadId": "thread_1",
                    "snippet": "Hello from the thread.",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Alex <alex@example.com>"},
                            {"name": "To", "value": "JR <jr@example.com>"},
                            {"name": "Subject", "value": "Project update"},
                            {"name": "Date", "value": "Thu, 2 Jul 2026 08:00:00 -0700"},
                        ],
                        "parts": [{"mimeType": "text/plain", "body": {"data": encoded}}],
                    },
                }
            ],
        }
        with patch.object(self.service, "_google_authorized_json", return_value=response):
            messages = self.service.gmail_thread_read("user_a", "thread_1")
        self.assertEqual(messages[0]["id"], "msg_1")
        self.assertEqual(messages[0]["threadId"], "thread_1")
        self.assertEqual(messages[0]["from"], "Alex <alex@example.com>")
        self.assertEqual(messages[0]["body_text"], "Hello from the thread.")

    def test_gmail_thread_read_prefers_plain_text_over_html_alternative(self) -> None:
        plain = "Got it! Thanks for testing. : )\n\nJR"
        html = '<div dir="ltr">Got it! Thanks for testing. : )<br><br>JR</div>'
        response = {
            "id": "thread_1",
            "messages": [
                {
                    "id": "msg_1",
                    "threadId": "thread_1",
                    "payload": {
                        "headers": [{"name": "From", "value": "James Willis <time2makecents@gmail.com>"}],
                        "parts": [
                            {"mimeType": "text/plain", "body": {"data": _gmail_body_data(plain)}},
                            {"mimeType": "text/html", "body": {"data": _gmail_body_data(html)}},
                        ],
                    },
                }
            ],
        }
        with patch.object(self.service, "_google_authorized_json", return_value=response):
            messages = self.service.gmail_thread_read("user_a", "thread_1")
        self.assertEqual(messages[0]["body_text"], plain)
        self.assertNotIn("<div", messages[0]["body_text"])

    def test_gmail_read_strips_html_when_plain_text_is_missing(self) -> None:
        response = {
            "id": "msg_1",
            "payload": {
                "headers": [{"name": "From", "value": "Alex <alex@example.com>"}],
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": _gmail_body_data('<div>Hello&nbsp;JR<br>Line 2</div>')},
                    }
                ],
            },
        }
        with patch.object(self.service, "_google_authorized_json", return_value=response):
            message = self.service.gmail_read("user_a", "msg_1")
        self.assertEqual(message["body_text"], "Hello JR\nLine 2")
        self.assertNotIn("<div", message["body_text"])

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
