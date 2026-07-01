from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.meeting_handlers import build_meeting_handlers
from office_app.server.meeting_state import MeetingStateStore
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore


class MeetingHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_dir = Path.cwd() / "office_app" / "runtime" / "_meeting_handler_test"
        shutil.rmtree(self.runtime_dir, ignore_errors=True)
        self.workspaces_dir = self.runtime_dir / "workspaces"
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.store = WorkspaceStore(self.workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
        self.kernel = WorkspaceKernel(store=self.store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
        self.kernel.create_workspace("ws_test", "Test")
        self.handlers = build_meeting_handlers(
            HandlerDeps(
                kernel=self.kernel,
                store=self.store,
                pipeline=None,
                archive_service=None,
                memo_service=None,
                nancy_service=None,
                receptionist_context_service=None,
                workspace_file_service=None,
                private_file_service=None,
                search_service=None,
                ocr_service=None,
                model_router=None,
                user_service=None,
                utc_now=lambda: "2026-04-21T12:00:00Z",
                stable_state_sha=lambda state: "sha",
                append_incident=lambda *args, **kwargs: "incident",
                error_missing_required_field=lambda field: ValueError(field),
                resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or "ws_test"),
            )
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.runtime_dir, ignore_errors=True)

    def test_start_add_show_meeting_state_persists_without_calendar_write(self) -> None:
        start = self.handlers["office.meeting_state_start"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "vendor kickoff"}
        )
        meeting_id = start["structuredContent"]["meeting_id"]
        self.assertEqual(start["structuredContent"]["title"], "vendor kickoff")
        self.assertIn("No calendar event was created", start["content"][0]["text"])

        self.handlers["office.meeting_state_add_agenda"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "review launch budget"}
        )
        self.handlers["office.meeting_state_record_decision"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "use option b"}
        )
        self.handlers["office.meeting_state_add_action_item"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "Sam will send notes"}
        )
        self.handlers["office.meeting_state_add_parking_lot"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "pricing follow-up"}
        )
        shown = self.handlers["office.meeting_state_show"]({"workspace_id": "ws_test", "session_id": "session_a"})
        state = shown["structuredContent"]
        self.assertEqual(state["meeting_id"], meeting_id)
        self.assertEqual(state["agenda"], ["review launch budget"])
        self.assertEqual(state["decisions"], ["use option b"])
        self.assertEqual(state["action_items"], ["Sam will send notes"])
        self.assertEqual(state["parking_lot"], ["pricing follow-up"])

        reloaded = MeetingStateStore(self.workspaces_dir / "ws_test" / "meetings").load(meeting_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.title, "vendor kickoff")
        self.assertEqual(reloaded.agenda, ["review launch budget"])

    def test_add_without_active_meeting_returns_start_required_response(self) -> None:
        result = self.handlers["office.meeting_state_add_agenda"](
            {"workspace_id": "ws_test", "session_id": "session_b", "item": "review budget"}
        )
        self.assertTrue(result["structuredContent"]["needs_meeting"])
        self.assertIn("Start a meeting first", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
