from __future__ import annotations

import unittest
from typing import Any, Dict, List

from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.work_context_handlers import build_work_context_handlers


class FakeWorkContextService:
    def __init__(self) -> None:
        self.completed_calls: List[Dict[str, Any]] = []
        self.upsert_calls: List[Dict[str, Any]] = []

    def list_contexts(self, workspace_id: str, *, status: str = "active", limit: int = 10) -> List[Dict[str, Any]]:
        return []

    def upsert_context(self, **kwargs) -> Dict[str, Any]:
        self.upsert_calls.append(dict(kwargs))
        return {
            "context_id": "ctx_manual_1",
            "title": kwargs.get("title", ""),
            "summary": kwargs.get("summary", ""),
            "status": kwargs.get("status", "active"),
            "active_room": kwargs.get("active_room", ""),
            "active_persona": kwargs.get("active_persona", ""),
        }

    def complete_active_contexts(self, *, workspace_id: str, summary: str = "") -> List[Dict[str, Any]]:
        self.completed_calls.append({"workspace_id": workspace_id, "summary": summary})
        return [
            {
                "context_id": "ctx_manual_1",
                "title": "Research follow-up",
                "summary": summary,
                "status": "completed",
            }
        ]

    def complete_active_context_by_index(self, *, workspace_id: str, active_index: int, summary: str = "") -> Dict[str, Any]:
        self.completed_calls.append({"workspace_id": workspace_id, "active_index": active_index, "summary": summary})
        return {
            "context_id": "ctx_manual_2",
            "title": "Selected follow-up",
            "summary": summary,
            "status": "completed",
        }

    def complete_context_by_id(self, *, workspace_id: str, context_id: str, summary: str = "") -> Dict[str, Any]:
        self.completed_calls.append({"workspace_id": workspace_id, "context_id": context_id, "summary": summary})
        return {
            "context_id": context_id,
            "title": "Card-selected follow-up",
            "summary": summary,
            "status": "completed",
        }


class WorkContextHandlerTests(unittest.TestCase):
    def _deps(self, service: FakeWorkContextService) -> HandlerDeps:
        class FakeKernel:
            def get_state(self, workspace_id: str) -> Dict[str, Any]:
                return {"active_room": "sales_department", "active_persona": "Sales Director"}

        return HandlerDeps(
            kernel=FakeKernel(),
            store=None,
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
            utc_now=lambda: "2026-07-03T09:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
            work_context_service=service,
        )

    def test_save_manual_active_work_context_uses_active_room_and_persona(self) -> None:
        service = FakeWorkContextService()
        handlers = build_work_context_handlers(self._deps(service))

        response = handlers["office.work_context_save"](
            {
                "workspace_id": "default",
                "title": "Finalize launch plan",
                "summary": "Finalize launch plan with Sales and Marketing.",
                "session_id": "sess_1",
            }
        )

        upsert = service.upsert_calls[0]
        self.assertEqual(upsert["workspace_id"], "default")
        self.assertEqual(upsert["source_type"], "manual")
        self.assertTrue(str(upsert["source_id"]).startswith("sess_1:manual:"))
        self.assertEqual(upsert["title"], "Finalize launch plan")
        self.assertEqual(upsert["summary"], "Finalize launch plan with Sales and Marketing.")
        self.assertEqual(upsert["active_room"], "sales_department")
        self.assertEqual(upsert["active_persona"], "Sales Director")
        self.assertEqual(response["structuredContent"]["context"]["context_id"], "ctx_manual_1")
        self.assertIn("Saved active work context", response["content"][0]["text"])

    def test_save_replacing_manual_active_work_context_uses_stable_current_source(self) -> None:
        service = FakeWorkContextService()
        handlers = build_work_context_handlers(self._deps(service))

        response = handlers["office.work_context_save"](
            {
                "workspace_id": "default",
                "title": "Finalize launch plan",
                "summary": "Replace the current workspace focus.",
                "session_id": "sess_1",
                "replace_active_manual": True,
            }
        )

        upsert = service.upsert_calls[0]
        self.assertEqual(upsert["workspace_id"], "default")
        self.assertEqual(upsert["source_type"], "manual")
        self.assertEqual(upsert["source_id"], "sess_1:manual:current")
        self.assertEqual(upsert["refs"]["mode"], "replace_current")
        self.assertIn("Updated active work context", response["content"][0]["text"])

    def test_complete_all_active_contexts_returns_completed_rows(self) -> None:
        service = FakeWorkContextService()
        handlers = build_work_context_handlers(self._deps(service))

        response = handlers["office.work_context_complete"](
            {
                "workspace_id": "default",
                "all_active": True,
            }
        )

        self.assertEqual(service.completed_calls[0]["workspace_id"], "default")
        self.assertIn("User cleared active work context", service.completed_calls[0]["summary"])
        self.assertEqual(response["structuredContent"]["completed_count"], 1)
        self.assertEqual(response["structuredContent"]["contexts"][0]["context_id"], "ctx_manual_1")
        self.assertIn("Completed 1 work context item", response["content"][0]["text"])

    def test_complete_active_context_by_index_returns_selected_row(self) -> None:
        service = FakeWorkContextService()
        handlers = build_work_context_handlers(self._deps(service))

        response = handlers["office.work_context_complete"](
            {
                "workspace_id": "default",
                "active_index": 2,
            }
        )

        self.assertEqual(service.completed_calls[0]["active_index"], 2)
        self.assertIn("User completed selected work context", service.completed_calls[0]["summary"])
        self.assertEqual(response["structuredContent"]["completed_count"], 1)
        self.assertEqual(response["structuredContent"]["contexts"][0]["context_id"], "ctx_manual_2")
        self.assertIn("Completed work context 2", response["content"][0]["text"])

    def test_complete_active_context_by_id_returns_selected_row(self) -> None:
        service = FakeWorkContextService()
        handlers = build_work_context_handlers(self._deps(service))

        response = handlers["office.work_context_complete"](
            {
                "workspace_id": "default",
                "context_id": "ctx_manual_exact",
            }
        )

        self.assertEqual(service.completed_calls[0]["context_id"], "ctx_manual_exact")
        self.assertIn("User completed selected work context", service.completed_calls[0]["summary"])
        self.assertEqual(response["structuredContent"]["completed_count"], 1)
        self.assertEqual(response["structuredContent"]["contexts"][0]["context_id"], "ctx_manual_exact")
        self.assertIn("Completed work context", response["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
