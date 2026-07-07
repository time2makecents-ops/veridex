from __future__ import annotations

import unittest
from types import SimpleNamespace

from office_app.server.handlers.navigator_handlers import build_navigator_handlers


class DummyNavigatorDiagnostics:
    def status_report(self, workspace_id: str, *, session_id: str | None = None):
        return {
            "health": {"ok": True},
            "workspace": {"active_room": "lobby", "active_persona": "Receptionist"},
            "tools": {"count": 7, "missing_expected": []},
            "config": {"serpapi_ready": True, "google_custom_search_ready": False, "google_oauth_configured": False},
            "incidents": [],
            "logs": {"backend": ["API_KEY=[REDACTED]"], "frontend": []},
        }

    def recent_errors(self, workspace_id: str, *, session_id: str | None = None):
        return {"incidents": [], "logs": {"backend": [], "frontend": []}}

    def explain_error(self, workspace_id: str, *, error_text: str = "", session_id: str | None = None):
        return {
            "summary": "The action was blocked by a room capability policy.",
            "next_step": "Move to the correct room or use the assistant that owns that capability, then retry.",
            "category": "capability_policy",
        }


class NavigatorHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handlers = build_navigator_handlers(
            SimpleNamespace(
                resolve_workspace_id=lambda tool, args: args.get("workspace_id") or "ws1",
                navigator_diagnostics_service=DummyNavigatorDiagnostics(),
            )
        )

    def test_status_report_returns_navigator_speaker(self) -> None:
        response = self.handlers["office.navigator_status_report"]({"workspace_id": "ws1", "session_id": "sess1"})

        structured = response["structuredContent"]
        self.assertEqual(structured["speaker"], "Navigator")
        self.assertEqual(structured["workspace_id"], "ws1")
        self.assertIn("Navigator status report", response["content"][0]["text"])

    def test_explain_error_returns_actionable_text(self) -> None:
        response = self.handlers["office.navigator_explain_error"](
            {"workspace_id": "ws1", "error_text": "Tool is not allowed from room lobby."}
        )

        self.assertEqual(response["structuredContent"]["speaker"], "Navigator")
        self.assertIn("Next step:", response["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
