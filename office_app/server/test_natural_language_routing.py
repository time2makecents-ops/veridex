from __future__ import annotations

import unittest

from office_app.server.request_pipeline import RequestPipeline


class DummyKernel:
    def __init__(self, active_room: str = "lobby"):
        self.active_room = active_room

    def current_context(self, workspace_id: str):
        return {
            "active_room": self.active_room,
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
        self.assertEqual(routed["capability"], "artifact.create")
        self.assertEqual(routed["tool"], "office.artifact_create")
        self.assertEqual(routed["workspace_id"], "default")
        self.assertEqual(routed["arguments"]["created_by"], "user")

    def test_list_artifacts_routes_to_artifact_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "show artifacts")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.list")
        self.assertEqual(routed["tool"], "office.artifact_list")
        self.assertEqual(routed["arguments"]["retrieval_scope"], "workspace")

    def test_saved_so_far_routes_to_workspace_scoped_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "what have we saved so far")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.list")
        self.assertEqual(routed["tool"], "office.artifact_list")
        self.assertEqual(routed["arguments"]["retrieval_scope"], "workspace")

    def test_archive_room_forces_global_artifact_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="records_archive"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "list artifacts")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.list")
        self.assertEqual(routed["tool"], "office.artifact_list")
        self.assertEqual(routed["arguments"]["retrieval_scope"], "archive_global")
        self.assertTrue(routed["arguments"]["include_archived"])

    def test_explicit_global_request_routes_to_global_artifact_get(self) -> None:
        routed = self.pipeline.route_user_request("default", "open artifact art_123abc across workspaces")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.get")
        self.assertEqual(routed["tool"], "office.artifact_get")
        self.assertEqual(routed["arguments"]["artifact_id"], "art_123abc")
        self.assertEqual(routed["arguments"]["retrieval_scope"], "archive_global")

    def test_open_artifact_routes_to_artifact_get(self) -> None:
        routed = self.pipeline.route_user_request("default", "open artifact art_123abc")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.get")
        self.assertEqual(routed["tool"], "office.artifact_get")
        self.assertEqual(routed["arguments"]["artifact_id"], "art_123abc")
        self.assertEqual(routed["arguments"]["retrieval_scope"], "workspace")

    def test_unknown_text_falls_back_to_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "review the quarterly plan")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertEqual(routed["tool"], "office.ai_generate")
        self.assertEqual(routed["arguments"]["workspace_id"], "default")
        self.assertEqual(routed["arguments"]["task_type"], "conversation")
        self.assertIn("system_prompt", routed["arguments"])

    def test_explicit_room_navigation_routes_to_room_change(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to it department")
        self.assertEqual(routed["route_kind"], "nancy")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "it_department")

    def test_non_navigation_break_phrase_does_not_switch_rooms(self) -> None:
        routed = self.pipeline.route_user_request("default", "did i break the thread?")
        self.assertEqual(routed["route_kind"], "model")

    def test_room_name_alone_does_not_switch_rooms(self) -> None:
        routed = self.pipeline.route_user_request("default", "break room")
        self.assertEqual(routed["route_kind"], "model")


if __name__ == "__main__":
    unittest.main()
