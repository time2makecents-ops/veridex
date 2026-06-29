from __future__ import annotations

import unittest

from fastapi import HTTPException

from office_app.server.request_pipeline import RequestPipeline
from office_app.server.room_capability_registry import RoomCapabilityRegistry
from office_app.server.room_router import rooms_payload
from office_app.server.tool_context import ToolContext
from office_app.server.tool_definitions import VERIDEX_TOOL_DEFINITIONS
from office_app.server.tool_policies import ToolPolicyEngine


class RoomCapabilityRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = RoomCapabilityRegistry()

    def test_every_active_room_has_a_valid_profile(self) -> None:
        active_room_ids = sorted(str(room["id"]) for room in rooms_payload() if room.get("is_active", True))
        profile_ids = sorted(profile["room_id"] for profile in self.registry.profiles_payload())
        self.assertEqual(active_room_ids, profile_ids)

    def test_art_department_owns_image_generation(self) -> None:
        self.assertTrue(self.registry.is_tool_allowed("art_department", "office.image_generate"))
        self.assertFalse(self.registry.is_tool_allowed("marketing_room", "office.image_generate"))
        self.assertFalse(self.registry.is_tool_allowed("sales_department", "office.image_generate"))

    def test_sales_profile_has_research_and_marketing_collaboration(self) -> None:
        profile = self.registry.profile_for_room("sales_department").as_dict()
        self.assertIn("office.search_web", profile["allowed_tools"])
        self.assertIn("office.search_places", profile["allowed_tools"])
        self.assertIn("marketing_room", profile["preferred_collaborators"])

    def test_policy_engine_enforces_room_capability_profile(self) -> None:
        engine = ToolPolicyEngine(room_capability_registry=self.registry)
        definition = VERIDEX_TOOL_DEFINITIONS["office.image_generate"]
        with self.assertRaises(HTTPException) as blocked:
            engine.authorize(
                definition,
                ToolContext(
                    tool_name="office.image_generate",
                    capability="image.generate",
                    workspace_id="ws_test",
                    active_room="marketing_room",
                    active_persona="Marketing Director",
                    arguments={},
                ),
            )
        self.assertEqual(403, blocked.exception.status_code)

        engine.authorize(
            definition,
            ToolContext(
                tool_name="office.image_generate",
                capability="image.generate",
                workspace_id="ws_test",
                active_room="art_department",
                active_persona="Creative Director",
                arguments={},
            ),
        )

    def test_room_capability_request_routes_to_tool(self) -> None:
        pipeline = RequestPipeline(kernel=None, navigator_control={}, utc_now_fn=lambda: "2026-06-29T00:00:00Z")
        route = pipeline.route_room_capability_request("ws_test", "what tools does sales department have?")
        self.assertIsNotNone(route)
        self.assertEqual("office.room_capabilities", route["tool"])
        self.assertEqual({"room_id": "sales_department"}, route["arguments"])


if __name__ == "__main__":
    unittest.main()
