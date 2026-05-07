from __future__ import annotations

import unittest

from office_app.server.request_response_helpers import request_text_from_response
from office_app.server.search_response_synthesis import (
    grounded_entity_followup_response,
    synthesize_search_response,
)


class FakeKernel:
    def get_state(self, workspace_id: str):
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
        }


class CapturingRouter:
    def __init__(self, response_text: str = "Verified summary from results only.") -> None:
        self.response_text = response_text
        self.calls = []

    def dispatch_capability(self, capability: str, args: dict, preferred_tool: str | None = None):
        self.calls.append(
            {
                "capability": capability,
                "args": args,
                "preferred_tool": preferred_tool,
            }
        )
        return {
            "structuredContent": {
                "response_text": self.response_text,
            },
            "content": [{"type": "text", "text": self.response_text}],
        }


class FailingRouter:
    def dispatch_capability(self, capability: str, args: dict, preferred_tool: str | None = None):
        raise RuntimeError("provider down")


class SearchResponseSynthesisTests(unittest.TestCase):
    def test_grounded_entity_search_adds_fail_closed_prompt_rule(self) -> None:
        router = CapturingRouter()
        routed = {
            "capability": "search.web",
            "request": "search for blairally and give me information about the company",
            "grounding_required": True,
            "entity_subject": "blairally",
        }
        result = {
            "structuredContent": {
                "summary_text": "Source: Example. URL: https://example.com/blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a Music Venue/Arcade in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
            "content": [{"type": "text", "text": "Source: Example. URL: https://example.com/blairally"}],
        }
        synthesized = synthesize_search_response(
            routed=routed,
            result=result,
            workspace_id="ws_1",
            session_id="sess_1",
            user_profile=None,
            kernel=FakeKernel(),
            router=router,
            request_text_from_response=request_text_from_response,
        )
        self.assertIn("search results describe blairally as a music venue/arcade", synthesized["content"][0]["text"].lower())
        self.assertIn("Verified summary from results only.", synthesized["content"][0]["text"])
        self.assertIn("use only the returned search facts", router.calls[0]["args"]["system_prompt"].lower())
        self.assertIn("Blairally Vintage Arcade", router.calls[0]["args"]["user_prompt"])
        self.assertIn("search results describe blairally as a music venue/arcade", router.calls[0]["args"]["user_prompt"].lower())
        self.assertEqual(
            synthesized["structuredContent"]["grounding_evidence_profile"]["topics"]["music_events"]["best_match"],
            "music venue/arcade",
        )

    def test_grounded_entity_search_returns_raw_tool_result_when_synthesis_provider_fails(self) -> None:
        routed = {
            "capability": "search.web",
            "request": "search for blairally and give me information about the company",
            "grounding_required": True,
            "entity_subject": "blairally",
        }
        result = {
            "structuredContent": {
                "summary_text": "Source: Example. URL: https://example.com/blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a Music Venue/Arcade in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
            "content": [{"type": "text", "text": "Source: Example. URL: https://example.com/blairally"}],
        }
        synthesized = synthesize_search_response(
            routed=routed,
            result=result,
            workspace_id="ws_1",
            session_id="sess_1",
            user_profile=None,
            kernel=FakeKernel(),
            router=FailingRouter(),
            request_text_from_response=request_text_from_response,
        )
        self.assertEqual(synthesized, result)

    def test_grounded_entity_followup_uses_music_venue_evidence(self) -> None:
        response = grounded_entity_followup_response(
            "does it have live music?",
            "Search results describe Blairally as a music venue/arcade in Eugene, Oregon.",
        )
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("Yes, search results describe it as a music venue/arcade", response)
        self.assertIn("Check the current event calendar for specific dates.", response)
        self.assertNotIn("Friday", response)

    def test_grounded_entity_followup_reports_when_music_terms_are_absent(self) -> None:
        response = grounded_entity_followup_response(
            "does it have live music?",
            "Search results describe Blairally as a vintage arcade in Eugene, Oregon.",
        )
        self.assertEqual(response, "I did not find live music or event terms in the grounded search results I have here.")

    def test_grounded_entity_followup_does_not_trigger_on_unrelated_question(self) -> None:
        response = grounded_entity_followup_response(
            "what state is it in?",
            "Search results describe Blairally as a music venue/arcade in Eugene, Oregon.",
        )
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
