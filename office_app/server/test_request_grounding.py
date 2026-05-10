from __future__ import annotations

import unittest

from office_app.server.request_grounding import EntityGroundingRouter


class EntityGroundingRouterTests(unittest.TestCase):
    def test_search_requested_routes_to_web_search(self) -> None:
        router = EntityGroundingRouter(
            extract_factual_entity_request=lambda _text: {
                "entity_subject": "blairally",
                "search_requested": True,
            },
            load_recent_transcript_turns=lambda _workspace_id, _session_id=None: [],
            resolve_active_room_title=lambda _workspace_id: "Sales Department",
        )
        routed = router.route_factual_entity_request("ws1", "search for blairally")
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["entity_subject"], "blairally")

    def test_unknown_entity_without_grounding_fails_closed(self) -> None:
        router = EntityGroundingRouter(
            extract_factual_entity_request=lambda _text: {
                "entity_subject": "blairally",
                "search_requested": False,
            },
            load_recent_transcript_turns=lambda _workspace_id, _session_id=None: [],
            resolve_active_room_title=lambda _workspace_id: "Sales Department",
        )
        routed = router.route_factual_entity_request("ws1", "what can you tell me about blairally")
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.entity_grounding")
        self.assertEqual(
            routed["arguments"]["response_text"],
            "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
        )

    def test_user_fact_counts_as_verified_grounding(self) -> None:
        router = EntityGroundingRouter(
            extract_factual_entity_request=lambda _text: {
                "entity_subject": "wireless unlimited",
                "search_requested": False,
            },
            load_recent_transcript_turns=lambda _workspace_id, _session_id=None: [
                {
                    "role": "user",
                    "text": "I helped start Wireless Unlimited in Oregon.",
                }
            ],
            resolve_active_room_title=lambda _workspace_id: "Sales Department",
        )
        routed = router.route_factual_entity_request("ws1", "what can you tell me about wireless unlimited")
        self.assertIsNone(routed)
