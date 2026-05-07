from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.file_handlers import build_file_handlers


class FakeKernel:
    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
        }


class FakeArchiveService:
    def __init__(self) -> None:
        self.created: Optional[Dict[str, Any]] = None

    def create_artifact(self, **kwargs: Any) -> Dict[str, Any]:
        self.created = dict(kwargs)
        return {
            "artifact_id": "art_oregon",
            "workspace_id": kwargs["workspace_id"],
            "type": kwargs["type"],
            "title": kwargs["title"],
            "content": kwargs["content"],
            "metadata": kwargs["metadata"],
        }


class FakeReceptionistContextService:
    def __init__(self) -> None:
        self.linked: Optional[Dict[str, Any]] = None

    def remember_room_behavior_ref(self, **kwargs: Any) -> Dict[str, Any]:
        self.linked = dict(kwargs)
        return {
            "workspace_id": kwargs["workspace_id"],
            "room_id": kwargs["room_id"],
            "room_behavior_memory_refs": [
                {
                    "artifact_id": kwargs["artifact_id"],
                    "workspace_id": kwargs["artifact_workspace_id"],
                    "preview": kwargs["preview"],
                }
            ],
        }

    def forget_room_behavior_refs(self, **kwargs: Any) -> Dict[str, Any]:
        self.linked = dict(kwargs)
        return {
            "workspace_id": kwargs["workspace_id"],
            "room_id": kwargs["room_id"],
            "removed_count": 1,
            "removed_refs": [{"artifact_id": "art_oregon"}],
            "room_behavior_memory_refs": [],
        }


class RoomMemoryHandlerTests(unittest.TestCase):
    def test_room_memory_is_stored_as_archive_artifact_and_linked_to_room(self) -> None:
        archive = FakeArchiveService()
        context = FakeReceptionistContextService()
        deps = HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=archive,
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=context,
            workspace_file_service=None,
            private_file_service=None,
            search_service=None,
            ocr_service=None,
            model_router=None,
            user_service=None,
            utc_now=lambda: "2026-05-07T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
        )
        handlers = build_file_handlers(deps)

        result = handlers["office.room_memory_remember"](
            {
                "workspace_id": "ws_1",
                "room_id": "sales_department",
                "instruction": "Sales questions pertain to businesses in Oregon.",
                "session_id": "sess_1",
            }
        )

        self.assertIsNotNone(archive.created)
        assert archive.created is not None
        self.assertEqual(archive.created["type"], "room_behavior_memory")
        self.assertEqual(archive.created["content"], "Sales questions pertain to businesses in Oregon.")
        self.assertEqual(archive.created["metadata"]["target_room"], "sales_department")
        self.assertEqual(archive.created["metadata"]["memory_kind"], "room_behavior")

        self.assertIsNotNone(context.linked)
        assert context.linked is not None
        self.assertEqual(context.linked["room_id"], "sales_department")
        self.assertEqual(context.linked["artifact_id"], "art_oregon")

        structured = result["structuredContent"]
        self.assertEqual(structured["artifact"]["artifact_id"], "art_oregon")
        self.assertIn("Records Archive", result["content"][0]["text"])

    def test_room_memory_forget_unlinks_behavior_reference(self) -> None:
        context = FakeReceptionistContextService()
        deps = HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=FakeArchiveService(),
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=context,
            workspace_file_service=None,
            private_file_service=None,
            search_service=None,
            ocr_service=None,
            model_router=None,
            user_service=None,
            utc_now=lambda: "2026-05-07T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
        )
        handlers = build_file_handlers(deps)
        result = handlers["office.room_memory_forget"](
            {
                "workspace_id": "ws_1",
                "room_id": "*",
                "match_text": "Oregon",
                "memory_index": 1,
            }
        )
        self.assertEqual(context.linked["memory_index"], 1)
        self.assertEqual(result["structuredContent"]["removed_count"], 1)
        self.assertEqual(result["structuredContent"]["room_title"], "all rooms")
        self.assertIn("Removed 1", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
