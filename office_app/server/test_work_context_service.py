from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from office_app.server.workspace_kernel import WorkspaceStore
from office_app.server.work_context_service import WorkContextService


class WorkContextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.now_values = iter(
            [
                "2026-07-03T08:00:00Z",
                "2026-07-03T08:01:00Z",
                "2026-07-03T08:02:00Z",
                "2026-07-03T08:03:00Z",
                "2026-07-03T08:04:00Z",
                "2026-07-03T08:05:00Z",
                "2026-07-03T08:06:00Z",
                "2026-07-03T08:07:00Z",
            ]
        )
        self.store = WorkspaceStore(Path(self.tmp.name), utc_now_fn=lambda: "2026-07-03T08:00:00Z")
        self.service = WorkContextService(store=self.store, utc_now_fn=lambda: next(self.now_values))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_upsert_updates_existing_source_context(self) -> None:
        self.service.upsert_context(
            workspace_id="default",
            source_type="nancy_email",
            source_id="sess_1:nancy_email",
            title="Email to James",
            summary="Nancy is waiting for the subject.",
            session_id="sess_1",
            active_room="my_office",
            active_persona="Nancy",
            refs={"stage": "subject"},
        )

        self.service.upsert_context(
            workspace_id="default",
            source_type="nancy_email",
            source_id="sess_1:nancy_email",
            title="Email to James",
            summary="Nancy is waiting for the body.",
            session_id="sess_1",
            active_room="sales_department",
            active_persona="Sales Director",
            refs={"stage": "body"},
        )

        rows = self.service.list_contexts("default", status="active")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["summary"], "Nancy is waiting for the body.")
        self.assertEqual(rows[0]["active_room"], "sales_department")
        self.assertEqual(rows[0]["refs"]["stage"], "body")

    def test_completed_context_is_omitted_from_active_list(self) -> None:
        self.service.upsert_context(
            workspace_id="default",
            source_type="memo",
            source_id="memo_123",
            title="Memo to Sales",
            summary="Memo sent to Sales.",
        )

        self.service.complete_context(
            workspace_id="default",
            source_type="memo",
            source_id="memo_123",
            summary="Memo reply was recorded.",
        )

        self.assertEqual(self.service.list_contexts("default", status="active"), [])
        completed = self.service.list_contexts("default", status="completed")
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["summary"], "Memo reply was recorded.")

    def test_complete_active_contexts_marks_all_active_rows_completed(self) -> None:
        self.service.upsert_context(
            workspace_id="default",
            source_type="nancy_email",
            source_id="sess_1:nancy_email",
            title="Email to James",
            summary="Waiting for confirmation.",
        )
        self.service.upsert_context(
            workspace_id="default",
            source_type="manual",
            source_id="manual_1",
            title="Research follow-up",
            summary="Waiting for review.",
        )

        completed = self.service.complete_active_contexts(
            workspace_id="default",
            summary="User cleared active work context.",
        )

        self.assertEqual(len(completed), 2)
        self.assertEqual(self.service.list_contexts("default", status="active"), [])
        completed_rows = self.service.list_contexts("default", status="completed")
        self.assertEqual(len(completed_rows), 2)
        self.assertTrue(all(row["summary"] == "User cleared active work context." for row in completed_rows))

    def test_complete_active_context_by_index_marks_only_selected_row(self) -> None:
        self.service.upsert_context(
            workspace_id="default",
            source_type="manual",
            source_id="manual_old",
            title="Older task",
            summary="Older task summary.",
        )
        self.service.upsert_context(
            workspace_id="default",
            source_type="manual",
            source_id="manual_new",
            title="Newer task",
            summary="Newer task summary.",
        )

        completed = self.service.complete_active_context_by_index(
            workspace_id="default",
            active_index=2,
            summary="User completed selected work context.",
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed["title"], "Older task")
        active = self.service.list_contexts("default", status="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["title"], "Newer task")

    def test_complete_context_by_id_marks_exact_active_row(self) -> None:
        older = self.service.upsert_context(
            workspace_id="default",
            source_type="manual",
            source_id="manual_old",
            title="Older task",
            summary="Older task summary.",
        )
        self.service.upsert_context(
            workspace_id="default",
            source_type="manual",
            source_id="manual_new",
            title="Newer task",
            summary="Newer task summary.",
        )

        completed = self.service.complete_context_by_id(
            workspace_id="default",
            context_id=older["context_id"],
            summary="User completed card context.",
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed["context_id"], older["context_id"])
        self.assertEqual(completed["title"], "Older task")
        active = self.service.list_contexts("default", status="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["title"], "Newer task")


if __name__ == "__main__":
    unittest.main()
