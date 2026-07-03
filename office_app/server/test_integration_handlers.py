from __future__ import annotations

import unittest

from office_app.server.handlers.integration_handlers import build_integration_handlers


class FakeIntegrationService:
    def __init__(self, *, connected: bool = False, configured: bool = True) -> None:
        self.connected = connected
        self.configured = configured
        self.pending_actions: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] = []
        self.contacts: list[dict[str, object]] = []

    def google_connection_status(self, user_id: str) -> dict[str, object]:
        return {
            "provider": "google",
            "configured": self.configured,
            "connected": self.connected,
            "account_email": "user@example.com" if self.connected else "",
            "scopes": [],
        }

    def create_pending_action(self, *, user_id: str, action_kind: str, payload: dict[str, object]) -> dict[str, object]:
        pending = {
            "confirmation_id": "confirm_fake",
            "provider": "google",
            "action_kind": action_kind,
            "payload": payload,
        }
        self.pending_actions.append(pending)
        return pending

    def gmail_search(self, user_id: str, query: str, max_results: int = 10) -> list[dict[str, object]]:
        return self.messages[:max_results]

    def gmail_read(self, user_id: str, message_id: str) -> dict[str, object]:
        for message in self.messages:
            if message.get("id") == message_id:
                return {
                    **message,
                    "to": "JR <jr@example.com>",
                    "body_text": "Full message body.",
                }
        return {}

    def gmail_thread_read(self, user_id: str, thread_id: str) -> list[dict[str, object]]:
        return [
            {
                **message,
                "to": "JR <jr@example.com>",
                "body_text": f"Thread body for {message.get('id')}.",
            }
            for message in self.messages
            if message.get("threadId") == thread_id
        ]

    def search_contacts(self, user_id: str, query: str, limit: int = 10) -> list[dict[str, object]]:
        lowered = query.lower()
        return [
            contact for contact in self.contacts
            if lowered in str(contact.get("display_name") or "").lower()
            or lowered in str(contact.get("email") or "").lower()
            or any(lowered in str(alias).lower() for alias in contact.get("aliases", []))
        ][:limit]

    def save_contact(self, user_id: str, *, email: str, display_name: str = "", aliases: list[str] | None = None, source: str = "manual") -> dict[str, object]:
        contact = {"email": email, "display_name": display_name, "aliases": aliases or [], "source": source}
        self.contacts.append(contact)
        return contact


class FakeUserService:
    def get_user_for_session(self, session_id: str) -> dict[str, str]:
        return {"user_id": "user_a"}


class IntegrationHandlerTests(unittest.TestCase):
    def handlers_for(self, service: FakeIntegrationService) -> dict[str, object]:
        return build_integration_handlers(integration_service=service, user_service=FakeUserService())

    def test_gmail_send_reports_disconnected_google_without_pending_confirmation(self) -> None:
        service = FakeIntegrationService(connected=False)
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_send"](
            {
                "session_id": "sess_a",
                "to": ["jane@example.com"],
                "subject": "Welcome",
                "body": "Thanks for trying Veridex.",
                "assistant_persona": "Nancy",
            }
        )
        self.assertEqual(service.pending_actions, [])
        self.assertFalse(response["structuredContent"]["google_connection"]["connected"])
        text = response["content"][0]["text"]
        self.assertIn("Google is configured but not connected", text)
        self.assertIn("Profile", text)
        self.assertIn("Nancy", text)

    def test_calendar_write_reports_disconnected_google_without_pending_confirmation(self) -> None:
        service = FakeIntegrationService(connected=False)
        handlers = self.handlers_for(service)
        response = handlers["office.calendar_create"](
            {
                "session_id": "sess_a",
                "event": {
                    "summary": "Planning",
                    "start": {"dateTime": "2026-07-03T14:00:00"},
                    "end": {"dateTime": "2026-07-03T15:00:00"},
                },
                "assistant_persona": "Nancy",
            }
        )
        self.assertEqual(service.pending_actions, [])
        self.assertFalse(response["structuredContent"]["google_connection"]["connected"])
        text = response["content"][0]["text"]
        self.assertIn("Google is configured but not connected", text)
        self.assertIn("Calendar", text)

    def test_gmail_draft_surfaces_disconnected_google_but_keeps_local_draft(self) -> None:
        service = FakeIntegrationService(connected=False)
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_draft"](
            {
                "session_id": "sess_a",
                "to": ["jane@example.com"],
                "subject": "Welcome",
                "body": "Thanks for trying Veridex.",
                "assistant_persona": "Nancy",
            }
        )
        self.assertEqual(response["structuredContent"]["draft"]["subject"], "Welcome")
        self.assertFalse(response["structuredContent"]["google_connection"]["connected"])
        self.assertIn("connect Google from Profile", response["content"][0]["text"])

    def test_connected_google_write_still_creates_pending_confirmation(self) -> None:
        service = FakeIntegrationService(connected=True)
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_send"](
            {
                "session_id": "sess_a",
                "to": ["jane@example.com"],
                "subject": "Welcome",
                "body": "Thanks for trying Veridex.",
                "assistant_persona": "Nancy",
            }
        )
        self.assertEqual(len(service.pending_actions), 1)
        self.assertEqual(response["structuredContent"]["confirmation_id"], "confirm_fake")
        self.assertIn("prepared the Gmail send confirmation", response["content"][0]["text"])

    def test_gmail_search_content_lists_real_sender_subject_and_snippet(self) -> None:
        service = FakeIntegrationService(connected=True)
        service.messages = [
            {
                "id": "msg_1",
                "from": "Alex <alex@example.com>",
                "subject": "Project update",
                "date": "Thu, 2 Jul 2026 08:00:00 -0700",
                "snippet": "The latest status is ready.",
            },
            {
                "id": "msg_2",
                "from": "Pat <pat@example.com>",
                "subject": "Invoice",
                "date": "Thu, 2 Jul 2026 08:05:00 -0700",
                "snippet": "Please review the attached invoice.",
            },
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_search"]({"session_id": "sess_a", "query": "in:inbox"})
        text = response["content"][0]["text"]
        self.assertIn("Found 2 Gmail message(s).", text)
        self.assertIn("Alex <alex@example.com>", text)
        self.assertIn("Project update", text)
        self.assertIn("Please review", text)
        self.assertEqual(response["structuredContent"]["gmail_messages"][0]["id"], "msg_1")

    def test_gmail_read_content_formats_readable_message_and_reply_prompt(self) -> None:
        service = FakeIntegrationService(connected=True)
        service.messages = [
            {
                "id": "msg_1",
                "from": "Alex <alex@example.com>",
                "subject": "Project update",
                "date": "Thu, 2 Jul 2026 08:00:00 -0700",
                "snippet": "The latest status is ready.",
            }
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_read"]({"session_id": "sess_a", "message_id": "msg_1"})
        text = response["content"][0]["text"]
        self.assertIn("From: Alex <alex@example.com>", text)
        self.assertIn("Full message body.", text)
        self.assertIn("Would you like to reply", text)
        self.assertEqual(response["structuredContent"]["gmail_message"]["id"], "msg_1")

    def test_gmail_thread_read_formats_thread_messages(self) -> None:
        service = FakeIntegrationService(connected=True)
        service.messages = [
            {
                "id": "msg_1",
                "threadId": "thread_1",
                "from": "Alex <alex@example.com>",
                "subject": "Project update",
                "date": "Thu, 2 Jul 2026 08:00:00 -0700",
                "snippet": "The latest status is ready.",
            },
            {
                "id": "msg_2",
                "threadId": "thread_1",
                "from": "JR <jr@example.com>",
                "subject": "Re: Project update",
                "date": "Thu, 2 Jul 2026 08:05:00 -0700",
                "snippet": "Thanks.",
            },
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_thread_read"]({"session_id": "sess_a", "thread_id": "thread_1"})
        text = response["content"][0]["text"]
        self.assertIn("Loaded Gmail thread with 2 message(s).", text)
        self.assertEqual(len(response["structuredContent"]["gmail_thread"]), 2)
        self.assertEqual(response["structuredContent"]["gmail_thread"][0]["id"], "msg_1")

    def test_gmail_send_returns_email_review_for_frontend(self) -> None:
        service = FakeIntegrationService(connected=True)
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_send"](
            {
                "session_id": "sess_a",
                "to": ["jane@example.com"],
                "subject": "Welcome",
                "body": "Thanks for trying Veridex.",
                "assistant_persona": "Nancy",
            }
        )
        self.assertEqual(response["structuredContent"]["email_review"]["to"], ["jane@example.com"])
        self.assertEqual(response["structuredContent"]["email_review"]["subject"], "Welcome")
        self.assertIn("To: jane@example.com", response["content"][0]["text"])

    def test_contact_resolve_returns_nancy_subject_prompt_for_known_contact(self) -> None:
        service = FakeIntegrationService(connected=True)
        service.contacts = [
            {
                "email": "time2makecents@gmail.com",
                "display_name": "James Willis",
                "aliases": ["James"],
            }
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.contact_resolve_email"]({"session_id": "sess_a", "name": "James"})
        self.assertEqual(response["structuredContent"]["speaker"], "Nancy")
        self.assertEqual(response["structuredContent"]["resolved_contact"]["email"], "time2makecents@gmail.com")
        self.assertIn("What subject should I use", response["content"][0]["text"])

    def test_contact_save_returns_saved_contact(self) -> None:
        service = FakeIntegrationService(connected=True)
        handlers = self.handlers_for(service)
        response = handlers["office.contact_save"](
            {
                "session_id": "sess_a",
                "email": "time2makecents@gmail.com",
                "display_name": "James Willis",
                "aliases": ["James"],
            }
        )
        self.assertEqual(response["structuredContent"]["contact"]["email"], "time2makecents@gmail.com")
        self.assertIn("Saved contact", response["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
