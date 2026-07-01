from __future__ import annotations

import unittest

from fastapi import HTTPException

from office_app.server.request_response_helpers import request_text_from_response
from office_app.server.search_response_synthesis import (
    build_grounded_search_context,
    grounded_entity_followup_response,
    grounded_search_followup_response,
    handle_search_tool_result,
    remember_grounded_search_context,
    synthesize_search_response,
)


class FakeKernel:
    def __init__(self, state=None) -> None:
        self.state = state or {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
        }

    def get_state(self, workspace_id: str):
        return self.state


class CapturingStore:
    def __init__(self) -> None:
        self.saved = []

    def save_state(self, workspace_id: str, state: dict) -> None:
        self.saved.append({"workspace_id": workspace_id, "state": state})


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


def apply_navigator_activation(response: dict, **kwargs) -> dict:
    enriched = dict(response)
    structured = dict(enriched.get("structuredContent") or {})
    structured["navigator_activation"] = {
        "activated": True,
        "capability": kwargs.get("capability"),
        "reason": kwargs.get("reason"),
    }
    enriched["structuredContent"] = structured
    return enriched


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

    def test_web_search_synthesis_appends_source_sites(self) -> None:
        router = CapturingRouter("Best cameras summary.")
        routed = {
            "capability": "search.web",
            "request": "what cellphones have the best cameras?",
        }
        result = {
            "structuredContent": {
                "summary_text": "Search results for best camera phones",
                "results": [
                    {
                        "title": "Phone A",
                        "source": "CNET",
                        "snippet": "Top camera phone",
                        "url": "https://www.cnet.com/reviews/phone-a",
                    },
                    {
                        "title": "Phone B",
                        "source": "The Verge",
                        "snippet": "Excellent photos",
                        "url": "https://www.theverge.com/phone-b",
                    },
                ],
            },
            "content": [{"type": "text", "text": "Search results for best camera phones"}],
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
        text = synthesized["content"][0]["text"]
        self.assertIn("Sources:", text)
        self.assertIn("cnet.com", text.lower())
        self.assertIn("theverge.com", text.lower())
        self.assertEqual(synthesized["structuredContent"]["source_sites"], ["CNET (cnet.com)", "The Verge (theverge.com)"])

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

    def test_grounded_entity_followup_does_not_trigger_on_fresh_music_lookup(self) -> None:
        response = grounded_entity_followup_response(
            "what music venues have famous bands play?",
            "Search results describe Blairally as a music venue/arcade in Eugene, Oregon.",
        )
        self.assertIsNone(response)

    def test_build_grounded_search_context_preserves_result_rows(self) -> None:
        routed = {
            "capability": "search.web",
            "request": "search for blairally and give me information about the company",
            "grounding_required": True,
            "entity_subject": "blairally",
        }
        result = {
            "structuredContent": {
                "provider": "serpapi",
                "summary_text": "Web results for 'blairally'",
                "response_text": "Search results describe Blairally as a music venue/arcade.",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Hours: Monday through Thursday 4 PM to 2 AM.",
                        "url": "https://example.com/blairally",
                    }
                ],
            }
        }
        context = build_grounded_search_context(routed=routed, result=result)
        self.assertEqual(context["entity_subject"], "blairally")
        self.assertEqual(context["provider"], "serpapi")
        self.assertEqual(context["results"][0]["title"], "Blairally Vintage Arcade")
        self.assertIn("4 PM to 2 AM", context["results"][0]["snippet"])

    def test_remember_grounded_search_context_persists_session_context(self) -> None:
        kernel = FakeKernel({"grounded_search_by_session": {"old_session": {"results": [{"title": "Old"}]}}})
        store = CapturingStore()
        routed = {
            "capability": "search.web",
            "request": "search for blairally",
            "grounding_required": True,
            "entity_subject": "blairally",
        }
        result = {
            "structuredContent": {
                "provider": "serpapi",
                "summary_text": "Web results for blairally",
                "response_text": "Search results describe Blairally as a music venue.",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a music venue in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            }
        }

        remember_grounded_search_context(
            workspace_id="ws_1",
            session_id="sess_1",
            routed=routed,
            result=result,
            kernel=kernel,
            store=store,
            utc_now=lambda: "2026-06-28T00:00:00Z",
        )

        self.assertEqual(len(store.saved), 1)
        saved_context = store.saved[0]["state"]["grounded_search_by_session"]["sess_1"]
        self.assertEqual(saved_context["ts"], "2026-06-28T00:00:00Z")
        self.assertEqual(saved_context["entity_subject"], "blairally")
        self.assertEqual(saved_context["results"][0]["title"], "Blairally Vintage Arcade")
        self.assertIn("old_session", store.saved[0]["state"]["grounded_search_by_session"])

    def test_remember_grounded_search_context_skips_without_grounded_results(self) -> None:
        kernel = FakeKernel({})
        store = CapturingStore()

        remember_grounded_search_context(
            workspace_id="ws_1",
            session_id="sess_1",
            routed={"capability": "search.web", "grounding_required": False},
            result={"structuredContent": {"results": [{"title": "Ignored"}]}},
            kernel=kernel,
            store=store,
            utc_now=lambda: "2026-06-28T00:00:00Z",
        )
        remember_grounded_search_context(
            workspace_id="ws_1",
            session_id="sess_1",
            routed={"capability": "search.web", "grounding_required": True},
            result={"structuredContent": {"results": []}},
            kernel=kernel,
            store=store,
            utc_now=lambda: "2026-06-28T00:00:00Z",
        )

        self.assertEqual(store.saved, [])

    def test_handle_search_tool_result_synthesizes_and_remembers_search_context(self) -> None:
        kernel = FakeKernel({"active_room": "sales_department", "active_persona": "Sales Director"})
        store = CapturingStore()
        router = CapturingRouter("Verified summary from results only.")
        routed = {
            "capability": "search.web",
            "tool": "office.search_web",
            "request": "search for blairally",
            "grounding_required": True,
            "entity_subject": "blairally",
        }
        result = {
            "structuredContent": {
                "provider": "serpapi",
                "summary_text": "Web results for blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a music venue in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
            "content": [{"type": "text", "text": "Web results for blairally"}],
        }

        handled = handle_search_tool_result(
            routed=routed,
            dispatch_tool=lambda: result,
            workspace_id="ws_1",
            session_id="sess_1",
            user_profile=None,
            kernel=kernel,
            store=store,
            router=router,
            request_text_from_response=request_text_from_response,
            utc_now=lambda: "2026-06-28T00:00:00Z",
            apply_navigator_activation=apply_navigator_activation,
        )

        self.assertIn("Verified summary from results only.", handled["content"][0]["text"])
        self.assertEqual(len(store.saved), 1)
        self.assertEqual(
            store.saved[0]["state"]["grounded_search_by_session"]["sess_1"]["results"][0]["title"],
            "Blairally Vintage Arcade",
        )

    def test_handle_search_tool_result_returns_non_search_result_unchanged(self) -> None:
        kernel = FakeKernel({})
        store = CapturingStore()
        result = {"structuredContent": {"response_text": "Created."}, "content": [{"type": "text", "text": "Created."}]}

        handled = handle_search_tool_result(
            routed={"capability": "workspace.create", "tool": "office.workspace_new"},
            dispatch_tool=lambda: result,
            workspace_id="ws_1",
            session_id="sess_1",
            user_profile=None,
            kernel=kernel,
            store=store,
            router=CapturingRouter(),
            request_text_from_response=request_text_from_response,
            utc_now=lambda: "2026-06-28T00:00:00Z",
            apply_navigator_activation=apply_navigator_activation,
        )

        self.assertIs(handled, result)
        self.assertEqual(store.saved, [])

    def test_handle_search_tool_result_fails_closed_for_grounded_search_http_error(self) -> None:
        def dispatch_tool():
            raise HTTPException(status_code=502, detail={"message": "provider down"})

        handled = handle_search_tool_result(
            routed={
                "capability": "search.web",
                "tool": "office.search_web",
                "grounding_required": True,
                "entity_subject": "blairally",
            },
            dispatch_tool=dispatch_tool,
            workspace_id="ws_1",
            session_id="sess_1",
            user_profile=None,
            kernel=FakeKernel({}),
            store=CapturingStore(),
            router=CapturingRouter(),
            request_text_from_response=request_text_from_response,
            utc_now=lambda: "2026-06-28T00:00:00Z",
            apply_navigator_activation=apply_navigator_activation,
        )

        structured = handled["structuredContent"]
        self.assertEqual(structured["routing"]["capability"], "clarification.entity_grounding")
        self.assertIn("I could not verify information about blairally", structured["response_text"])
        self.assertTrue(structured["navigator_activation"]["activated"])

    def test_grounded_search_followup_can_answer_hours_from_preserved_results(self) -> None:
        response = grounded_search_followup_response(
            "what are the hours again?",
            {
                "entity_subject": "blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Hours: Monday through Thursday 4 PM to 2 AM; Friday through Sunday 2 PM to 2 AM.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
        )
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("4 PM to 2 AM", response)
        self.assertIn("Blairally Vintage Arcade", response)

    def test_grounded_search_followup_reuses_preserved_summary_for_explicit_entity_request(self) -> None:
        response = grounded_search_followup_response(
            "what can you tell me about blairally?",
            {
                "entity_subject": "blairally",
                "response_text": "Search results describe blairally as a music venue/arcade in Eugene, Oregon.",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
        )
        self.assertEqual(
            response,
            "Search results describe blairally as a music venue/arcade in Eugene, Oregon.",
        )

    def test_grounded_search_followup_can_answer_location_from_preserved_results(self) -> None:
        response = grounded_search_followup_response(
            "what state is it in?",
            {
                "entity_subject": "blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
        )
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("Eugene, Oregon", response)
        self.assertIn("Blairally Vintage Arcade", response)

    def test_grounded_search_followup_can_report_wrong_time_was_not_grounded(self) -> None:
        response = grounded_search_followup_response(
            "what search result said 4am instead of 4pm?",
            {
                "entity_subject": "blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Hours: Monday through Thursday 4 PM to 2 AM; Friday through Sunday 2 PM to 2 AM.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
        )
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("I do not have a preserved search result snippet that says 4 AM", response)
        self.assertIn("The preserved result I have says 4 PM", response)

    def test_grounded_search_followup_fails_closed_when_attribute_not_supported(self) -> None:
        response = grounded_search_followup_response(
            "who owns it?",
            {
                "entity_subject": "blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
        )
        self.assertEqual(
            response,
            "I do not have a preserved search result snippet that answers that ownership question.",
        )

    def test_grounded_search_followup_does_not_reuse_music_context_for_fresh_lookup(self) -> None:
        response = grounded_search_followup_response(
            "what are the biggest music venues in oregon?",
            {
                "entity_subject": "blairally",
                "results": [
                    {
                        "title": "Blairally Vintage Arcade",
                        "source": "Example",
                        "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                        "url": "https://example.com/blairally",
                    }
                ],
            },
        )
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
