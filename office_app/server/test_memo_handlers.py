from __future__ import annotations

import shutil
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from office_app.server.app import NAVIGATOR_CONTROL, RequestPipeline, WorkspaceStore
from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.memo_handlers import build_memo_handlers
from office_app.server.memo_service import MemoService
from office_app.server.model_router import ModelRouteResult, ModelRoutingError


class FakeKernel:
    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
        }


class FakeArchiveService:
    def __init__(self) -> None:
        self.records = {
            "art_room": {
                "content": "Focus on Oregon retail operations and local storefront realities.",
                "metadata": {"memory_kind": "room_behavior"},
            },
            "art_persona": {
                "content": "answer my sales questions from now on with the book how to win friends and influence people in mind",
                "metadata": {"memory_kind": "persona_behavior"},
            },
        }

    def get_artifact(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        record = dict(self.records[artifact_id])
        record["artifact_id"] = artifact_id
        record["workspace_id"] = workspace_id
        return record


class FakeReceptionistContextService:
    def room_behavior_memory_refs(self, *, workspace_id: str, room_id: str) -> List[Dict[str, Any]]:
        return [{"artifact_id": "art_room", "workspace_id": workspace_id}]

    def persona_behavior_memory_refs(self, *, workspace_id: str, room_id: str, persona_name: str) -> List[Dict[str, Any]]:
        return [{"artifact_id": "art_persona", "workspace_id": workspace_id, "target_persona": persona_name}]


@dataclass
class CapturingModelRouter:
    text: str
    system_prompts: List[str]
    user_prompts: List[str]
    contexts: List[Dict[str, Any]]

    def __init__(self, text: str) -> None:
        self.text = text
        self.system_prompts = []
        self.user_prompts = []
        self.contexts = []

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        self.contexts.append(dict(context or {}))
        return ModelRouteResult(
            provider="gemini",
            model="gemini-2.5-flash-lite",
            text=self.text,
            task_type=task_type,
            fallback_used=False,
            attempts=[],
        )


class FailingModelRouter:
    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        raise ModelRoutingError("provider unavailable", attempts=["gemini: unavailable"])


class MemoHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_dir = Path.cwd() / "office_app" / "runtime" / "_memo_handler_tests"
        self.workspaces_dir = self.runtime_dir / "workspaces"
        self.legacy_memos_dir = self.runtime_dir / "memos"
        shutil.rmtree(self.runtime_dir, ignore_errors=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_memos_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_id = "ws_test_memo"
        self.store = WorkspaceStore(self.workspaces_dir, utc_now_fn=lambda: "2026-05-27T12:00:00Z")
        self.memo_service = MemoService(
            store=self.store,
            legacy_memos_dir=self.legacy_memos_dir,
            utc_now_fn=lambda: "2026-05-27T12:00:00Z",
        )
        self.pipeline = RequestPipeline(
            kernel=FakeKernel(),
            navigator_control=NAVIGATOR_CONTROL,
            utc_now_fn=lambda: "2026-05-27T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.runtime_dir, ignore_errors=True)

    def _deps(self, model_router: Any) -> HandlerDeps:
        return HandlerDeps(
            kernel=FakeKernel(),
            store=self.store,
            pipeline=self.pipeline,
            archive_service=FakeArchiveService(),
            memo_service=self.memo_service,
            nancy_service=None,
            receptionist_context_service=FakeReceptionistContextService(),
            workspace_file_service=None,
            private_file_service=None,
            search_service=None,
            ocr_service=None,
            model_router=model_router,
            user_service=None,
            utc_now=lambda: "2026-05-27T12:00:00Z",
            stable_state_sha=lambda state: "sha256",
            append_incident=lambda **kwargs: "incident",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda workspace_id, args: workspace_id,
        )

    def test_mailroom_dispatch_returns_and_persists_destination_reply(self) -> None:
        router = CapturingModelRouter(
            "Memo filed to: Navigator (Control Room)\nSubject: ignore this\n\nSystem health is nominal."
        )
        handlers = build_memo_handlers(self._deps(router))

        response = handlers["mailroom.dispatch"](
            {
                "workspace_id": self.workspace_id,
                "to_room": "control_room",
                "body": "Please assess current system health.",
            }
        )

        response_text = response["structuredContent"]["response_text"]
        self.assertEqual(response["structuredContent"]["speaker"], "Navigator")
        self.assertIn("Memo filed to: Navigator (Control Room)", response_text)
        self.assertIn("System health is nominal.", response_text)
        self.assertNotIn("Subject: ignore this", response_text)
        self.assertIn("Focus on Oregon retail operations and local storefront realities.", router.system_prompts[0])
        self.assertIn("friendly, empathetic, relationship-first style", router.system_prompts[0])

        memo_id = response["structuredContent"]["memo_id"]
        stored_obj, body = self.memo_service.get_memo(self.workspace_id, memo_id)
        self.assertEqual(body, "Please assess current system health.")
        self.assertEqual(stored_obj["reply_text"], "System health is nominal.")
        self.assertEqual(stored_obj["reply_room"], "control_room")
        self.assertEqual(stored_obj["reply_persona"], "Navigator")

        memo_response = handlers["office.memo_get"](
            {
                "workspace_id": self.workspace_id,
                "memo_id": memo_id,
            }
        )
        memo_text = memo_response["content"][0]["text"]
        self.assertIn("Response from Navigator (control_room):", memo_text)
        self.assertIn("System health is nominal.", memo_text)

    def test_mailroom_dispatch_accepts_explicit_subject(self) -> None:
        router = CapturingModelRouter("System health is nominal.")
        handlers = build_memo_handlers(self._deps(router))

        response = handlers["mailroom.dispatch"](
            {
                "workspace_id": self.workspace_id,
                "to_room": "control_room",
                "subject": "System Health Review",
                "body": "Please assess current system health.",
            }
        )

        memo_id = response["structuredContent"]["memo_id"]
        stored_obj, body = self.memo_service.get_memo(self.workspace_id, memo_id)
        self.assertEqual(body, "Please assess current system health.")
        self.assertEqual(stored_obj["subject"], "System Health Review")
        self.assertEqual(response["structuredContent"]["subject"], "System Health Review")
        self.assertIn("Memo subject: System Health Review", router.user_prompts[0])

    def test_memos_list_includes_reply_status_and_actionable_text(self) -> None:
        router = CapturingModelRouter("System health is nominal.")
        handlers = build_memo_handlers(self._deps(router))
        dispatch_response = handlers["mailroom.dispatch"](
            {
                "workspace_id": self.workspace_id,
                "to_room": "control_room",
                "body": "Please assess current system health.",
            }
        )

        list_response = handlers["office.memos_list"]({"workspace_id": self.workspace_id})

        memo_id = dispatch_response["structuredContent"]["memo_id"]
        rows = list_response["structuredContent"]["memos"]
        self.assertEqual(rows[0]["memo_id"], memo_id)
        self.assertEqual(rows[0]["reply_status"], "replied")
        self.assertEqual(rows[0]["reply_persona"], "Navigator")
        self.assertEqual(rows[0]["reply_room"], "control_room")
        self.assertEqual(rows[0]["replied_utc"], "2026-05-27T12:00:00Z")
        self.assertFalse(rows[0]["is_refusal"])
        text = list_response["content"][0]["text"]
        self.assertIn(memo_id, text)
        self.assertIn("Please assess current system health.", text)
        self.assertIn("replied by Navigator (control_room)", text)

    def test_mailroom_dispatch_falls_back_to_structured_failure_reply(self) -> None:
        handlers = build_memo_handlers(self._deps(FailingModelRouter()))

        response = handlers["mailroom.dispatch"](
            {
                "workspace_id": self.workspace_id,
                "to_room": "it_department",
                "body": "Review the current workstation deployment issue.",
            }
        )

        reply_text = response["structuredContent"]["reply_text"]
        self.assertIn("internal processing failure", reply_text)
        self.assertIn("If further review is needed, see me in my office, or send a detailed memo.", reply_text)
        self.assertFalse(response["structuredContent"]["is_refusal"])
        self.assertTrue(response["structuredContent"]["closure_appended"])

    def test_email_memo_to_nancy_is_blocked_without_model_or_send_claim(self) -> None:
        router = CapturingModelRouter("I will send the email.")
        handlers = build_memo_handlers(self._deps(router))

        response = handlers["mailroom.dispatch"](
            {
                "workspace_id": self.workspace_id,
                "to_room": "my_office",
                "body": "Send that drafted email.",
            }
        )

        self.assertTrue(response["structuredContent"]["email_action_blocked"])
        self.assertIn("No email was sent.", response["structuredContent"]["response_text"])
        self.assertEqual(router.system_prompts, [])

    def test_memo_reply_external_side_effect_claim_is_sanitized(self) -> None:
        router = CapturingModelRouter("I scheduled the calendar event and sent the invite.")
        handlers = build_memo_handlers(self._deps(router))

        response = handlers["mailroom.dispatch"](
            {
                "workspace_id": self.workspace_id,
                "to_room": "conference_room",
                "body": "Schedule the vendor meeting tomorrow.",
            }
        )

        reply_text = response["structuredContent"]["reply_text"]
        self.assertIn("No external action was performed through this memo.", reply_text)
        self.assertNotIn("I scheduled", reply_text)
        self.assertNotIn("sent the invite", reply_text)
        memo_id = response["structuredContent"]["memo_id"]
        stored_obj, _ = self.memo_service.get_memo(self.workspace_id, memo_id)
        self.assertEqual(stored_obj["reply_text"], reply_text)


if __name__ == "__main__":
    unittest.main()
