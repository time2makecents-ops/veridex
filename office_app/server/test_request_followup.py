from __future__ import annotations

import unittest

from office_app.server.conversation_planner import ConversationPlanner
from office_app.server.request_followup import RequestFollowupRouter


class RequestFollowupRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grounded_context = None
        self.router = RequestFollowupRouter(
            conversation_planner=ConversationPlanner(),
            model_route=self._model_route,
            extract_location=self._extract_location,
            load_grounded_search_context=self._load_grounded_search_context,
        )

    def _model_route(self, workspace_id: str, user_prompt: str, **kwargs):
        return {
            "route_kind": "model",
            "capability": "ai.respond",
            "tool": "office.ai_generate",
            "arguments": {
                "workspace_id": workspace_id,
                "user_prompt": user_prompt,
            },
            "reason": str(kwargs.get("reason") or ""),
        }

    @staticmethod
    def _extract_location(text: str):
        lowered = text.lower()
        if "eugene" in lowered:
            return "eugene"
        if "portland" in lowered:
            return "portland"
        return None

    def _load_grounded_search_context(self, workspace_id: str, session_id: str | None = None):
        return self.grounded_context

    def test_entity_followup_uses_grounded_search_evidence(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "does it have live music?",
            [
                {"role": "user", "text": "search for blairally and give me information about the company"},
                {"role": "assistant", "text": "Search results describe Blairally as a music venue/arcade in Eugene, Oregon."},
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("music venue/arcade", routed["arguments"]["response_text"])

    def test_hours_followup_uses_preserved_grounded_search_snippet(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Hours: Monday through Thursday 4 PM to 2 AM; Friday through Sunday 2 PM to 2 AM.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "what are the hours again?",
            [],
            session_id="sess_1",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("4 PM to 2 AM", routed["arguments"]["response_text"])
        self.assertIn("Blairally Vintage Arcade", routed["arguments"]["response_text"])

    def test_location_followup_uses_preserved_grounded_search_snippet(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "what state is it in?",
            [],
            session_id="sess_1",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("Eugene, Oregon", routed["arguments"]["response_text"])

    def test_source_followup_reports_when_wrong_time_was_not_grounded(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Hours: Monday through Thursday 4 PM to 2 AM; Friday through Sunday 2 PM to 2 AM.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "what search result said 4am instead of 4pm?",
            [],
            session_id="sess_1",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("I do not have a preserved search result snippet that says 4 AM", routed["arguments"]["response_text"])
        self.assertIn("The preserved result I have says 4 PM", routed["arguments"]["response_text"])

    def test_unsupported_attribute_followup_fails_closed(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "who owns it?",
            [],
            session_id="sess_1",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(
            routed["arguments"]["response_text"],
            "I do not have a preserved search result snippet that answers that ownership question.",
        )

    def test_fresh_music_lookup_does_not_reuse_preserved_grounded_context(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "what are the biggest music venues in oregon?",
            [],
        )
        self.assertIsNone(routed)

    def test_show_all_sessions_in_workspace_does_not_reuse_grounded_context(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "show me all sessions in this workspace",
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                },
            ],
        )
        self.assertIsNone(routed)

    def test_what_sessions_are_in_this_workspace_does_not_reuse_grounded_context(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally Vintage Arcade",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "what sessions are in this workspace",
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                },
            ],
        )
        self.assertIsNone(routed)

    def test_restaurant_followup_routes_to_reviews(self) -> None:
        self.grounded_context = None
        routed = self.router.route_contextual_followup(
            "ws1",
            "what about ambrosia?",
            [
                {"role": "user", "text": "what are the best italian restaurants in eugene?"},
                {"role": "assistant", "text": "Review-oriented results for 'italian restaurants':"},
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["arguments"]["query"], "ambrosia italian restaurant")
        self.assertEqual(routed["arguments"]["location"], "eugene")

    def test_conversation_followup_rewrites_to_model_prompt(self) -> None:
        self.grounded_context = None
        routed = self.router.route_contextual_followup(
            "ws1",
            "what the most powerful one used in marketing?",
            [
                {"role": "user", "text": "what is maslow's hierarchy of needs?"},
                {
                    "role": "assistant",
                    "text": (
                        "Maslow's Hierarchy of Needs is a theory of motivation.\n\n"
                        "The levels are:\n"
                        "1. Physiological Needs\n"
                        "2. Safety Needs\n"
                        "3. Love and Belonging Needs\n"
                        "4. Esteem Needs\n"
                        "5. Self-Actualization Needs"
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "Which single level of Maslow's hierarchy of needs is most powerful in marketing? "
            "Answer with one level first, then a brief reason.",
        )

    def test_yes_after_offer_routes_to_web_search_for_recent_entity(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "yes",
            [
                {"role": "user", "text": "what can you tell me about blairally?"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Marketing & Advertising do an internet search or search your other sessions if you want to know more.",
                },
                {
                    "role": "assistant",
                    "text": "I can search the web for more information about blairally if you'd like.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertEqual(routed["entity_subject"], "blairally")

    def test_search_other_sessions_without_subject_uses_recent_entity(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "search other sessions",
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertFalse(routed["arguments"]["include_current"])

    def test_search_the_internet_without_subject_uses_recent_entity(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "search the internet",
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["arguments"]["query"], "blairally")

    def test_bare_search_without_subject_uses_recent_entity(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "search",
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["arguments"]["query"], "blairally")

    def test_recent_entity_subject_ignores_session_search_result_numbering(self) -> None:
        subject = RequestFollowupRouter._recent_entity_subject(
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": (
                        "I found 3 matching session(s) for \"blairally\":\n"
                        "1. Nav test (sess_99a66e8dfc21) - You: tell me about blairally\n"
                        "2. Session_A (sess_66c6c2f0dfd3) - You: what can you tell me about blairally\n"
                        "3. Session_B (sess_0772e3abaec1) - You: what can you tell me about blairally?"
                    ),
                },
            ]
        )
        self.assertEqual(subject, "blairally")

    def test_recent_entity_subject_strips_trailing_information_from_session_search(self) -> None:
        subject = RequestFollowupRouter._recent_entity_subject(
            [
                {"role": "user", "text": "search all sessions for blairally information"},
            ]
        )
        self.assertEqual(subject, "blairally")

    def test_thread_context_ignores_source_checks_when_collecting_meaningful_turns(self) -> None:
        context = RequestFollowupRouter._build_thread_context(
            [
                {"role": "user", "text": "why are malls dying in oregon?"},
                {
                    "role": "assistant",
                    "text": "Malls are struggling in Oregon because of online shopping and changing consumer preferences.",
                },
                {
                    "role": "user",
                    "text": 'where did you gather your information from when answering my question "why are malls dying in oregon"?',
                },
                {
                    "role": "assistant",
                    "text": 'The text you quoted came from my prior response: "Malls are struggling in Oregon..."',
                },
            ]
        )
        self.assertIn("why are malls dying in oregon?", context.meaningful_user_turns)
        self.assertNotIn("where did you gather your information from when answering my question \"why are malls dying in oregon\"?", context.meaningful_user_turns)

    def test_session_search_detail_followup_reuses_recent_session_search(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "can you list the information it gave in those sessions",
            [
                {"role": "user", "text": "search other sessions"},
                {
                    "role": "assistant",
                    "text": (
                        "I found 3 matching session(s) for \"blairally\":\n"
                        "1. Nav test (sess_99a66e8dfc21) - Navigator: Veridex doesn't have any verified information about blairally.\n"
                        "2. Session_A (sess_66c6c2f0dfd3) - Sales Director: Blairally is a music venue and arcade.\n"
                        "3. Session_B (sess_0772e3abaec1) - Sales Director: Blairally is a music venue and arcade."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertFalse(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_session_search_detail_followup_wins_over_grounded_search_context(self) -> None:
        self.grounded_context = {
            "entity_subject": "blairally",
            "results": [
                {
                    "title": "Blairally",
                    "source": "Example",
                    "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                    "url": "https://example.com/blairally",
                }
            ],
        }
        routed = self.router.route_contextual_followup(
            "ws1",
            "can you list the information it gave in those sessions",
            [
                {"role": "user", "text": "search other sessions"},
                {
                    "role": "assistant",
                    "text": 'I found 2 matching session(s) for "blairally":\n1. Session_A (sess_1) - Sales Director: Blairally is a music venue and arcade.',
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertTrue(routed["arguments"]["detail"])

    def test_generic_session_search_in_room_uses_recent_entity(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "search the sessions in sales department",
            [
                {"role": "user", "text": "tell me about blairally"},
                {
                    "role": "assistant",
                    "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertTrue(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_session_item_detail_followup_routes_to_target_session(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "show me the info from number 2",
            [
                {"role": "user", "text": "search sessions for info about blairally"},
                {
                    "role": "assistant",
                    "text": (
                        "I found 3 matching session(s) for \"blairally\":\n"
                        "1. Nav test (sess_99a66e8dfc21) - Sales Director: Blairally is a music venue.\n"
                        "2. Session_A (sess_66c6c2f0dfd3) - Sales Director: Blairally has hours.\n"
                        "3. Session_B (sess_0772e3abaec1) - Sales Director: Blairally is a nightclub."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertEqual(routed["arguments"]["target_session_id"], "sess_66c6c2f0dfd3")
        self.assertTrue(routed["arguments"]["detail"])
        self.assertFalse(routed["arguments"]["expand_full"])

    def test_show_me_the_rest_of_item_routes_to_full_session_answer(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "show me the rest of 2",
            [
                {"role": "user", "text": "search sessions for info about blairally"},
                {
                    "role": "assistant",
                    "text": (
                        "I found 3 matching session(s) for \"blairally\":\n"
                        "1. Nav test (sess_99a66e8dfc21) - Sales Director: Blairally is a music venue.\n"
                        "2. Session_A (sess_66c6c2f0dfd3) - Sales Director: Blairally has hours...\n"
                        "3. Session_B (sess_0772e3abaec1) - Sales Director: Blairally is a nightclub."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertEqual(routed["arguments"]["target_session_id"], "sess_66c6c2f0dfd3")
        self.assertTrue(routed["arguments"]["detail"])
        self.assertTrue(routed["arguments"]["expand_full"])

    def test_source_followup_reports_unsupported_generalization_in_prior_answer(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "where did you gather your information from when answering my question?",
            [
                {
                    "role": "assistant",
                    "text": (
                        "Considering the principles from How to Win Friends and Influence People by Dale Carnegie, "
                        "I'll provide you with some insights on why malls might be dying in Oregon.\n\n"
                        "Malls are struggling nationwide, and Oregon is no exception. "
                        "Oregon has seen a surge in new developments."
                    ),
                }
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.source_reference")
        self.assertIn("unsupported generalization", routed["arguments"]["response_text"].lower())
        self.assertIn("prior response", routed["arguments"]["response_text"].lower())

    def test_memory_reference_followup_returns_prior_topic_summary(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            "do you remember when i asked about malls dying in oregon?",
            [
                {"role": "user", "text": "why are malls dying in oregon?"},
                {
                    "role": "assistant",
                    "text": (
                        "Malls are struggling in Oregon, much like the rest of the country, due to a combination of factors. "
                        "The primary drivers include the significant shift towards online shopping, which offers convenience and often better prices, "
                        "and changing consumer preferences that increasingly favor unique, personalized experiences over traditional retail environments."
                    ),
                },
                {
                    "role": "user",
                    "text": 'where did you gather your information from when answering my question "why are malls dying in oregon"?',
                },
                {
                    "role": "assistant",
                    "text": (
                        'The text you quoted came from my prior response: "Malls are struggling in Oregon, much like the rest of the country..." '
                        "I do not have a verified source for that claim."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.memory_reference")
        response_text = routed["arguments"]["response_text"]
        self.assertIn("Yes.", response_text)
        self.assertIn("malls dying in oregon", response_text.lower())
        self.assertIn("Malls are struggling in Oregon", response_text)
        self.assertNotIn("where did you gather your information", response_text.lower())

    def test_source_followup_uses_quoted_prior_question_to_find_matching_answer(self) -> None:
        routed = self.router.route_contextual_followup(
            "ws1",
            'where did you gather your information from when answering my question "why are malls dying in oregon"?',
            [
                {"role": "user", "text": "why are malls dying in oregon?"},
                {
                    "role": "assistant",
                    "text": (
                        "Malls are struggling in Oregon, much like the rest of the country, due to a combination of factors. "
                        "The primary drivers include the significant shift towards online shopping, which offers convenience and often better prices, "
                        "and changing consumer preferences that increasingly favor unique, personalized experiences over traditional retail environments."
                    ),
                },
                {"role": "user", "text": "how do you pick a good beer to go with fish?"},
                {"role": "assistant", "text": "When pairing beer with fish, I consider the principles from How to Win Friends and Influence People."},
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        response_text = routed["arguments"]["response_text"]
        self.assertIn("Malls are struggling in Oregon", response_text)
        self.assertNotIn("beer with fish", response_text)
