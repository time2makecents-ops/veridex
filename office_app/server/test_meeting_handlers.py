from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from fastapi import HTTPException

from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.meeting_handlers import build_meeting_handlers
from office_app.server.model_router import ModelRouteResult, ModelRoutingError
from office_app.server.meeting_state import MeetingStateStore
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore


class FakeArchiveService:
    def __init__(self) -> None:
        self.created = []

    def create_artifact(self, **kwargs):
        record = {
            "artifact_id": f"art_{len(self.created) + 1}",
            "workspace_id": kwargs["workspace_id"],
            "type": kwargs["type"],
            "artifact_type": kwargs["type"],
            "title": kwargs["title"],
            "display_name": kwargs["title"],
            "content": kwargs["content"],
            "content_preview": kwargs["content"][:200],
            "format": kwargs["format"],
            "status": kwargs["status"],
            "created_by": kwargs["created_by"],
            "metadata": kwargs.get("metadata") or {},
            "source_refs": kwargs.get("source_refs") or [],
        }
        self.created.append(record)
        return record


class FakeModelRouter:
    def __init__(self, text: str = "Polished meeting brief.") -> None:
        self.text = text
        self.calls = []

    def generate_response(self, **kwargs):
        self.calls.append(kwargs)
        return ModelRouteResult(
            provider="fake",
            model="fake-model",
            text=self.text,
            task_type=kwargs.get("task_type", "conversation"),
            fallback_used=False,
            attempts=[],
        )


class FailingModelRouter:
    def generate_response(self, **kwargs):
        raise ModelRoutingError("No model provider available.", attempts=["fake: unavailable"])


class MeetingHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_dir = Path.cwd() / "office_app" / "runtime" / "_meeting_handler_test"
        shutil.rmtree(self.runtime_dir, ignore_errors=True)
        self.workspaces_dir = self.runtime_dir / "workspaces"
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.store = WorkspaceStore(self.workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
        self.kernel = WorkspaceKernel(store=self.store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
        self.kernel.create_workspace("ws_test", "Test")
        self.archive_service = FakeArchiveService()
        self.model_router = FakeModelRouter()
        self.handlers = build_meeting_handlers(
            HandlerDeps(
                kernel=self.kernel,
                store=self.store,
                pipeline=None,
                archive_service=self.archive_service,
                memo_service=None,
                nancy_service=None,
                receptionist_context_service=None,
                workspace_file_service=None,
                private_file_service=None,
                search_service=None,
                ocr_service=None,
                model_router=self.model_router,
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

    def test_update_title_edit_and_delete_items_persist(self) -> None:
        start = self.handlers["office.meeting_state_start"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "vendor kickoff"}
        )
        meeting_id = start["structuredContent"]["meeting_id"]
        self.handlers["office.meeting_state_add_agenda"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "review launch budget"}
        )
        self.handlers["office.meeting_state_add_agenda"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "confirm owners"}
        )

        renamed = self.handlers["office.meeting_state_update_title"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "launch planning"}
        )
        edited = self.handlers["office.meeting_state_update_item"](
            {
                "workspace_id": "ws_test",
                "session_id": "session_a",
                "section": "agenda",
                "index": 0,
                "item": "review launch budget and risks",
            }
        )
        deleted = self.handlers["office.meeting_state_delete_item"](
            {"workspace_id": "ws_test", "session_id": "session_a", "section": "agenda", "index": 1}
        )

        self.assertEqual(renamed["structuredContent"]["title"], "launch planning")
        self.assertEqual(edited["structuredContent"]["agenda"][0], "review launch budget and risks")
        self.assertEqual(deleted["structuredContent"]["agenda"], ["review launch budget and risks"])

        reloaded = MeetingStateStore(self.workspaces_dir / "ws_test" / "meetings").load(meeting_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.title, "launch planning")
        self.assertEqual(reloaded.agenda, ["review launch budget and risks"])

    def test_update_item_rejects_invalid_section_and_index(self) -> None:
        self.handlers["office.meeting_state_start"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "vendor kickoff"}
        )
        self.handlers["office.meeting_state_add_agenda"](
            {"workspace_id": "ws_test", "session_id": "session_a", "item": "review launch budget"}
        )

        with self.assertRaises(HTTPException) as bad_section:
            self.handlers["office.meeting_state_update_item"](
                {"workspace_id": "ws_test", "session_id": "session_a", "section": "notes", "index": 0, "item": "x"}
            )
        self.assertEqual(bad_section.exception.status_code, 400)

        with self.assertRaises(HTTPException) as bad_index:
            self.handlers["office.meeting_state_delete_item"](
                {"workspace_id": "ws_test", "session_id": "session_a", "section": "agenda", "index": 2}
            )
        self.assertEqual(bad_index.exception.status_code, 404)

    def test_save_deterministic_meeting_brief_creates_artifact(self) -> None:
        start = self.handlers["office.meeting_state_start"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "vendor kickoff"}
        )
        meeting_id = start["structuredContent"]["meeting_id"]
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

        saved = self.handlers["office.meeting_brief_save"](
            {"workspace_id": "ws_test", "session_id": "session_a", "mode": "deterministic"}
        )
        artifact = saved["structuredContent"]["artifact"]

        self.assertEqual(artifact["artifact_type"], "meeting_brief")
        self.assertEqual(artifact["metadata"]["meeting_id"], meeting_id)
        self.assertEqual(artifact["metadata"]["brief_mode"], "deterministic")
        self.assertIn("# Meeting Brief: vendor kickoff", artifact["content"])
        self.assertIn("- review launch budget", artifact["content"])
        self.assertIn("- use option b", artifact["content"])
        self.assertIn("- Sam will send notes", artifact["content"])
        self.assertIn("- pricing follow-up", artifact["content"])

    def test_save_polished_meeting_brief_creates_separate_artifact_linked_to_source(self) -> None:
        self.handlers["office.meeting_state_start"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "vendor kickoff"}
        )
        deterministic = self.handlers["office.meeting_brief_save"](
            {"workspace_id": "ws_test", "session_id": "session_a", "mode": "deterministic"}
        )
        source_artifact_id = deterministic["structuredContent"]["artifact"]["artifact_id"]

        polished = self.handlers["office.meeting_brief_save"](
            {
                "workspace_id": "ws_test",
                "session_id": "session_a",
                "mode": "polished",
                "source_artifact_id": source_artifact_id,
            }
        )
        artifact = polished["structuredContent"]["artifact"]

        self.assertEqual(artifact["artifact_type"], "meeting_brief_polished")
        self.assertEqual(artifact["content"], "Polished meeting brief.")
        self.assertEqual(artifact["metadata"]["brief_mode"], "polished")
        self.assertEqual(artifact["metadata"]["source_artifact_id"], source_artifact_id)
        self.assertEqual(len(self.archive_service.created), 2)

    def test_polished_brief_failure_does_not_create_artifact(self) -> None:
        self.handlers = build_meeting_handlers(
            HandlerDeps(
                kernel=self.kernel,
                store=self.store,
                pipeline=None,
                archive_service=self.archive_service,
                memo_service=None,
                nancy_service=None,
                receptionist_context_service=None,
                workspace_file_service=None,
                private_file_service=None,
                search_service=None,
                ocr_service=None,
                model_router=FailingModelRouter(),
                user_service=None,
                utc_now=lambda: "2026-04-21T12:00:00Z",
                stable_state_sha=lambda state: "sha",
                append_incident=lambda *args, **kwargs: "incident",
                error_missing_required_field=lambda field: ValueError(field),
                resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or "ws_test"),
            )
        )
        self.handlers["office.meeting_state_start"](
            {"workspace_id": "ws_test", "session_id": "session_a", "title": "vendor kickoff"}
        )

        with self.assertRaises(HTTPException) as failure:
            self.handlers["office.meeting_brief_save"](
                {"workspace_id": "ws_test", "session_id": "session_a", "mode": "polished"}
            )

        self.assertEqual(failure.exception.status_code, 503)
        self.assertEqual(self.archive_service.created, [])


if __name__ == "__main__":
    unittest.main()
