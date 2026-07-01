from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

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
        self.requested_workspace_id = ""

    def get_artifact(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        self.requested_workspace_id = workspace_id
        return {
            "artifact_id": artifact_id,
            "workspace_id": workspace_id,
            "title": "Sales guidance",
            "content": "Answer sales questions with How to Win Friends and Influence People in mind.",
            "metadata": {"memory_kind": "room_behavior"},
        }


class FakeContextService:
    def room_behavior_memory_refs(self, *, workspace_id: str, room_id: str) -> List[Dict[str, Any]]:
        return [{"artifact_id": "art_123", "workspace_id": "ws_archive", "linked_at": "2026-05-07T12:00:00Z"}]

    def persona_behavior_memory_refs(self, *, workspace_id: str, room_id: str, persona_name: str) -> List[Dict[str, Any]]:
        return []


class RoomMemoryListHandlerTests(unittest.TestCase):
    def test_room_memory_list_includes_description(self) -> None:
        archive = FakeArchiveService()
        deps = HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=archive,
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=FakeContextService(),
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
        result = handlers["office.room_memory_list"]({"workspace_id": "ws_1", "room_id": "sales_department"})
        text = result["content"][0]["text"]
        self.assertTrue(text.startswith("Room behavior memories:"))
        self.assertIn("1. ", text)
        self.assertIn("How to Win Friends and Influence People", text)
        self.assertEqual(archive.requested_workspace_id, "ws_archive")
        self.assertEqual(result["structuredContent"]["items"][0]["index"], 1)


if __name__ == "__main__":
    unittest.main()
