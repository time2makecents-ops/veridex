from __future__ import annotations

import unittest

from office_app.server.request_pipeline import RequestPipeline


class DummyKernel:
    def current_context(self, workspace_id: str):
        return {
            "active_room": "lobby",
            "active_persona": "Receptionist",
            "active_persona_profile": {"name": "Receptionist"},
        }

    def list_workspaces(self):
        return {"workspaces": []}


class NaturalLanguageRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = RequestPipeline(
            kernel=DummyKernel(),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

    def test_save_this_routes_to_artifact_create(self) -> None:
        routed = self.pipeline.route_user_request("default", "save this")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["tool"], "office.artifact_create")
        self.assertEqual(routed["workspace_id"], "default")
        self.assertEqual(routed["arguments"]["created_by"], "user")

    def test_list_artifacts_routes_to_artifact_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "show artifacts")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["tool"], "office.artifact_list")

    def test_open_artifact_routes_to_artifact_get(self) -> None:
        routed = self.pipeline.route_user_request("default", "open artifact art_123abc")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["tool"], "office.artifact_get")
        self.assertEqual(routed["arguments"]["artifact_id"], "art_123abc")

    def test_unknown_text_falls_back_to_nancy(self) -> None:
        routed = self.pipeline.route_user_request("default", "review the quarterly plan")
        self.assertEqual(routed["route_kind"], "nancy")
        self.assertEqual(routed["tool"], "office.nancy_route")
        self.assertEqual(routed["arguments"]["workspace_id"], "default")


if __name__ == "__main__":
    unittest.main()
