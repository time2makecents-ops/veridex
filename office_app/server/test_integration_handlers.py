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
                    "body_text": message.get("body_text") or "Full message body.",
                }
        return {}

    def gmail_thread_read(self, user_id: str, thread_id: str) -> list[dict[str, object]]:
        return [
            {
                **message,
                "to": "JR <jr@example.com>",
                "body_text": message.get("body_text") or f"Thread body for {message.get('id')}.",
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

    def confirm_action(self, *, user_id: str, confirmation_id: str) -> dict[str, object]:
        return {
            "action_kind": "gmail.send",
            "payload": {"to": ["jane@example.com"], "subject": "Welcome", "body": "Thanks."},
            "result": {"id": "gmail_msg_1"},
        }

    def cancel_action(self, *, user_id: str, confirmation_id: str) -> dict[str, object]:
        return {
            "action_kind": "gmail.send",
            "payload": {"to": ["jane@example.com"], "subject": "Welcome", "body": "Thanks."},
            "confirmation_id": confirmation_id,
            "canceled": True,
        }


class FakeCalendarConfirmIntegrationService(FakeIntegrationService):
    def confirm_action(self, *, user_id: str, confirmation_id: str) -> dict[str, object]:
        return {
            "action_kind": "calendar.create",
            "payload": {"summary": "Planning"},
            "result": {"id": "evt_1"},
        }

    def cancel_action(self, *, user_id: str, confirmation_id: str) -> dict[str, object]:
        return {
            "action_kind": "calendar.create",
            "payload": {"summary": "Planning"},
            "confirmation_id": confirmation_id,
            "canceled": True,
        }


class FakeUserService:
    def get_user_for_session(self, session_id: str) -> dict[str, str]:
        return {"user_id": "user_a"}

    def resolve_workspace_for_session(self, session_id: str) -> str:
        return "workspace_a"


class FakeWorkContextService:
    def __init__(self) -> None:
        self.completed: list[dict[str, object]] = []

    def complete_context(self, **kwargs) -> dict[str, object]:
        self.completed.append(dict(kwargs))
        return dict(kwargs)


class IntegrationHandlerTests(unittest.TestCase):
    def handlers_for(self, service: FakeIntegrationService, work_context_service: FakeWorkContextService | None = None) -> dict[str, object]:
        return build_integration_handlers(
            integration_service=service,
            user_service=FakeUserService(),
            work_context_service=work_context_service,
        )

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

    def test_gmail_confirmation_completes_nancy_email_work_context(self) -> None:
        service = FakeIntegrationService(connected=True)
        work_context = FakeWorkContextService()
        handlers = self.handlers_for(service, work_context_service=work_context)

        response = handlers["office.integration_confirm"](
            {
                "session_id": "sess_a",
                "confirmation_id": "confirm_fake",
            }
        )

        self.assertEqual(response["structuredContent"]["result"]["action_kind"], "gmail.send")
        self.assertEqual(len(work_context.completed), 1)
        completed = work_context.completed[0]
        self.assertEqual(completed["workspace_id"], "workspace_a")
        self.assertEqual(completed["source_type"], "nancy_email")
        self.assertEqual(completed["source_id"], "sess_a:nancy_email")
        self.assertIn("confirmed and sent", completed["summary"])

    def test_calendar_confirmation_completes_generic_integration_work_context(self) -> None:
        service = FakeCalendarConfirmIntegrationService(connected=True)
        work_context = FakeWorkContextService()
        handlers = self.handlers_for(service, work_context_service=work_context)

        response = handlers["office.integration_confirm"](
            {
                "session_id": "sess_a",
                "confirmation_id": "confirm_fake",
            }
        )

        self.assertEqual(response["structuredContent"]["result"]["action_kind"], "calendar.create")
        self.assertEqual(len(work_context.completed), 1)
        completed = work_context.completed[0]
        self.assertEqual(completed["workspace_id"], "workspace_a")
        self.assertEqual(completed["source_type"], "integration_confirmation")
        self.assertEqual(completed["source_id"], "confirm_fake")
        self.assertIn("confirmed and completed", completed["summary"])

    def test_gmail_cancel_completes_nancy_email_work_context_and_clears_compose(self) -> None:
        service = FakeIntegrationService(connected=True)
        work_context = FakeWorkContextService()
        handlers = self.handlers_for(service, work_context_service=work_context)

        response = handlers["office.integration_cancel"](
            {
                "session_id": "sess_a",
                "confirmation_id": "confirm_fake",
            }
        )

        self.assertTrue(response["structuredContent"]["result"]["canceled"])
        self.assertTrue(response["structuredContent"]["clear_pending_nancy_email"])
        self.assertEqual(len(work_context.completed), 1)
        completed = work_context.completed[0]
        self.assertEqual(completed["source_type"], "nancy_email")
        self.assertEqual(completed["source_id"], "sess_a:nancy_email")
        self.assertIn("dismissed", completed["summary"])

    def test_calendar_cancel_completes_generic_integration_work_context(self) -> None:
        service = FakeCalendarConfirmIntegrationService(connected=True)
        work_context = FakeWorkContextService()
        handlers = self.handlers_for(service, work_context_service=work_context)

        response = handlers["office.integration_cancel"](
            {
                "session_id": "sess_a",
                "confirmation_id": "confirm_fake",
            }
        )

        self.assertTrue(response["structuredContent"]["result"]["canceled"])
        self.assertEqual(len(work_context.completed), 1)
        completed = work_context.completed[0]
        self.assertEqual(completed["source_type"], "integration_confirmation")
        self.assertEqual(completed["source_id"], "confirm_fake")
        self.assertIn("dismissed", completed["summary"])

    def test_gmail_search_content_uses_cards_instead_of_duplicate_text_list(self) -> None:
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
        self.assertIn("email cards", text)
        self.assertNotIn("Alex <alex@example.com>", text)
        self.assertNotIn("Project update", text)
        self.assertNotIn("Please review", text)
        self.assertEqual(response["structuredContent"]["gmail_messages"][0]["id"], "msg_1")

    def test_gmail_read_content_keeps_reply_metadata_without_body_copy(self) -> None:
        service = FakeIntegrationService(connected=True)
        service.messages = [
            {
                "id": "msg_1",
                "from": "Alex <alex@example.com>",
                "subject": "Project update",
                "date": "Thu, 2 Jul 2026 08:00:00 -0700",
                "snippet": "The latest status is ready.",
                "body_text": (
                    "Current answer.\n\n"
                    "On Thu, Jul 2, 2026 at 1:19 AM James <jr@example.com> wrote:\n"
                    "> Previous answer.\n\n"
                    "<div dir=\"ltr\">Current answer.</div>"
                ),
            }
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_read"]({"session_id": "sess_a", "message_id": "msg_1"})
        text = response["content"][0]["text"]
        self.assertIn("From: Alex <alex@example.com>", text)
        self.assertIn("Subject: Project update", text)
        self.assertNotIn("Current answer.", text)
        self.assertIn("Would you like to reply", text)
        self.assertEqual(response["structuredContent"]["gmail_message"]["id"], "msg_1")
        self.assertEqual(response["structuredContent"]["gmail_message"]["body_text"], "Current answer.")

    def test_gmail_thread_read_content_keeps_reply_metadata_without_body_copies(self) -> None:
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
                "body_text": (
                    "Thanks.\n\n"
                    "On Thu, Jul 2, 2026 at 8:00 AM Alex <alex@example.com> wrote:\n"
                    "> The latest status is ready.\n\n"
                    "<div class=\"gmail_quote\">duplicated quoted html</div>"
                ),
            },
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.gmail_thread_read"]({"session_id": "sess_a", "thread_id": "thread_1"})
        text = response["content"][0]["text"]
        self.assertIn("Loaded Gmail thread with 2 message(s).", text)
        self.assertIn("From: JR <jr@example.com>", text)
        self.assertIn("Subject: Re: Project update", text)
        self.assertNotIn("Thread body", text)
        self.assertNotIn("duplicated quoted html", text)
        self.assertEqual(len(response["structuredContent"]["gmail_thread"]), 2)
        self.assertEqual(response["structuredContent"]["gmail_thread"][0]["id"], "msg_1")
        self.assertEqual(response["structuredContent"]["gmail_thread"][1]["body_text"], "Thanks.")

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

    def test_contact_list_content_uses_structured_cards_without_duplicate_text(self) -> None:
        service = FakeIntegrationService(connected=True)
        service.contacts = [
            {
                "email": "time2makecents@gmail.com",
                "display_name": "James Willis",
                "aliases": ["James", "Time2"],
                "source": "gmail",
            },
            {
                "email": "alex@example.com",
                "display_name": "Alex Rivera",
                "aliases": ["Alex"],
                "source": "manual",
            },
        ]
        handlers = self.handlers_for(service)
        response = handlers["office.contact_list"]({"session_id": "sess_a"})
        text = response["content"][0]["text"]
        self.assertIn("Found 2 contact(s).", text)
        self.assertIn("contact cards", text)
        self.assertNotIn("time2makecents@gmail.com", text)
        self.assertNotIn("James Willis", text)
        self.assertEqual(response["structuredContent"]["contacts"][0]["email"], "time2makecents@gmail.com")


if __name__ == "__main__":
    unittest.main()
