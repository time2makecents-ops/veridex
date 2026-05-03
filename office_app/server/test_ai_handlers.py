from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from office_app.server.handlers.ai_handlers import build_ai_handlers
from office_app.server.handlers.dependencies import HandlerDeps


class FakeKernel:
    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
        }


@dataclass
class FakeFileService:
    rows: List[Dict[str, Any]]
    content_by_id: Dict[str, bytes]

    def __post_init__(self) -> None:
        self.store = self

    def list_files(self, workspace_id: str, scope: Optional[str] = None, scope_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        filtered = [row for row in self.rows if row["workspace_id"] == workspace_id]
        if scope:
            filtered = [row for row in filtered if row.get("scope") == scope]
        if scope_ref:
            filtered = [row for row in filtered if row.get("scope_ref") == scope_ref]
        return filtered

    def file_bytes(self, workspace_id: str, file_id: str) -> Tuple[Dict[str, Any], bytes]:
        for row in self.rows:
            if row["workspace_id"] == workspace_id and row["file_id"] == file_id:
                return row, self.content_by_id[file_id]
        raise FileNotFoundError(file_id)


class FakeOcrService:
    def extract_text(self, *, file_name: str, mime_type: Optional[str], content_bytes: bytes) -> Dict[str, Any]:
        return {
            "method": "local_text",
            "mime_type": mime_type or "application/octet-stream",
            "text": content_bytes.decode("utf-8"),
            "file_name": file_name,
        }


class FakeSearchService:
    def __init__(self) -> None:
        self.place_calls: List[Dict[str, Any]] = []

    def search_places(
        self,
        *,
        query: str,
        location: Optional[str] = None,
        category: Optional[str] = None,
        needs_location: bool = False,
        limit: int = 5,
    ) -> Dict[str, Any]:
        self.place_calls.append(
            {
                "query": query,
                "location": location,
                "category": category,
                "needs_location": needs_location,
                "limit": limit,
            }
        )
        return {
            "query": query,
            "location": location,
            "category": category,
            "needs_location": needs_location,
            "limit": limit,
            "results": [],
            "summary_text": "I need your location or a city/area to search nearby restaurants.",
        }


class AiHandlerTests(unittest.TestCase):
    def _deps(self, workspace_rows: List[Dict[str, Any]], search_service: Optional[Any] = None) -> HandlerDeps:
        workspace_service = FakeFileService(
            rows=workspace_rows,
            content_by_id={row["file_id"]: b"Extracted contents" for row in workspace_rows},
        )
        private_service = FakeFileService(rows=[], content_by_id={})
        return HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=None,
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=None,
            workspace_file_service=workspace_service,
            private_file_service=private_service,
            search_service=search_service,
            ocr_service=FakeOcrService(),
            model_router=None,
            user_service=None,
            utc_now=lambda: "2026-04-24T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
        )

    def test_ocr_extract_resolves_room_scoped_file_by_name(self) -> None:
        deps = self._deps(
            [
                {
                    "workspace_id": "ws_1",
                    "file_id": "file_123",
                    "original_name": "JW_Cover.rtf",
                    "mime_type": "application/rtf",
                    "scope": "room",
                    "scope_ref": "sales_department",
                }
            ]
        )
        handlers = build_ai_handlers(deps)
        result = handlers["office.ocr_extract"](
            {
                "workspace_id": "ws_1",
                "file_name": "JW_Cover.rtf",
                "session_id": "sess_1",
            }
        )
        self.assertEqual(result["structuredContent"]["file_id"], "file_123")
        self.assertEqual(result["structuredContent"]["original_name"], "JW_Cover.rtf")
        self.assertEqual(result["content"][0]["text"], "Extracted contents")

    def test_search_places_passes_needs_location_to_service(self) -> None:
        search_service = FakeSearchService()
        handlers = build_ai_handlers(self._deps([], search_service=search_service))
        result = handlers["office.search_places"](
            {
                "workspace_id": "ws_1",
                "query": "restaurants",
                "category": "restaurants",
                "needs_location": True,
            }
        )
        self.assertEqual(result["content"][0]["text"], "I need your location or a city/area to search nearby restaurants.")
        self.assertEqual(search_service.place_calls[0]["query"], "restaurants")
        self.assertTrue(search_service.place_calls[0]["needs_location"])


if __name__ == "__main__":
    unittest.main()
