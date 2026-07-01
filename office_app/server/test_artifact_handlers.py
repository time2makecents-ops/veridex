from __future__ import annotations

import unittest
from typing import Any, Dict, List

from office_app.server.handlers.artifact_handlers import build_artifact_handlers
from office_app.server.handlers.dependencies import HandlerDeps


class FakeKernel:
    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {"active_room": "sales_department", "active_persona": "Sales Director"}


class FakeArchiveService:
    def list_artifacts(self, workspace_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
        return [
            {"artifact_id": "art_1", "display_name": "Workspace Note", "artifact_type": "note", "content_preview": "Follow up with the client."},
            {"artifact_id": "art_2", "display_name": "Sales Plan", "artifact_type": "document", "content_preview": "Grow repeat customers through referrals."},
        ]

    def list_artifacts_across_workspaces(self, workspace_ids: List[str], include_archived: bool = True) -> List[Dict[str, Any]]:
        return []

    def delete_artifact(self, *, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        return {
            "artifact_id": artifact_id,
            "display_name": "Workspace Note",
            "artifact_type": "note",
            "content": "Follow up with the client.",
            "metadata": {"memory_kind": "room_behavior", "target_room": "sales_department"},
        }


class FakeReceptionistContextService:
    def __init__(self) -> None:
        self.removed = []

    def forget_room_behavior_refs(self, **kwargs):
        self.removed.append(kwargs)
        return {"removed_count": 1, "removed_refs": [], "room_behavior_memory_refs": []}


class ArtifactHandlersTests(unittest.TestCase):
    def test_artifact_list_text_includes_item_names_and_previews(self) -> None:
        deps = HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=FakeArchiveService(),
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=FakeReceptionistContextService(),
            workspace_file_service=None,
            private_file_service=None,
            search_service=None,
            ocr_service=None,
            model_router=None,
            user_service=None,
            utc_now=lambda: "2026-05-13T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
        )
        handlers = build_artifact_handlers(deps)
        result = handlers["office.artifact_list"]({"workspace_id": "ws_1", "retrieval_scope": "workspace"})
        text = result["content"][0]["text"]
        self.assertIn("Found 2 artifact(s)", text)
        self.assertIn("Workspace Note", text)
        self.assertIn("Sales Plan", text)
        self.assertIn("Follow up with the client.", text)
        self.assertIn("Grow repeat customers through referrals.", text)

    def test_artifact_delete_text_reports_deleted_item(self) -> None:
        receptionist_context_service = FakeReceptionistContextService()
        deps = HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=FakeArchiveService(),
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=receptionist_context_service,
            workspace_file_service=None,
            private_file_service=None,
            search_service=None,
            ocr_service=None,
            model_router=None,
            user_service=None,
            utc_now=lambda: "2026-05-13T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
        )
        handlers = build_artifact_handlers(deps)
        result = handlers["office.artifact_delete"]({"workspace_id": "ws_1", "artifact_id": "art_1"})
        text = result["content"][0]["text"]
        self.assertIn("Deleted artifact Workspace Note (art_1).", text)
        self.assertEqual(len(receptionist_context_service.removed), 1)
        self.assertEqual(receptionist_context_service.removed[0]["artifact_id"], "art_1")


if __name__ == "__main__":
    unittest.main()
