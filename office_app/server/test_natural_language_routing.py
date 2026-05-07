from __future__ import annotations

import unittest

from office_app.server.request_pipeline import RequestPipeline


class DummyKernel:
    def __init__(
        self,
        active_room: str = "lobby",
        active_persona: str = "Receptionist",
        transcript_rows: list[dict[str, str]] | None = None,
    ):
        self.active_room = active_room
        self.active_persona = active_persona
        self.store = DummyStore(transcript_rows or [])

    def current_context(self, workspace_id: str):
        return {
            "active_room": self.active_room,
            "active_persona": self.active_persona,
            "active_persona_profile": {"name": self.active_persona},
        }

    def list_workspaces(self):
        return {"workspaces": []}


class DummyStore:
    def __init__(self, transcript_rows: list[dict[str, str]]):
        self.transcript_rows = transcript_rows

    def load_transcript(self, workspace_id: str, limit: int = 100, session_id: str | None = None):
        return self.transcript_rows[-limit:]


class NaturalLanguageRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = RequestPipeline(
            kernel=DummyKernel(),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        self.sales_pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
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
        self.assertEqual(routed["route_kind"], "navigation")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "it_department")
        self.assertEqual(routed["tool"], "office.room_set")

    def test_go_to_my_office_routes_to_my_office(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to my office")
        self.assertEqual(routed["route_kind"], "navigation")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "my_office")
        self.assertEqual(routed["room_title"], "My Office")
        self.assertFalse(routed.get("requires_confirmation", False))
        self.assertEqual(routed["tool"], "office.room_set")

    def test_go_to_conference_room_routes_to_conference_room(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to conference room")
        self.assertEqual(routed["route_kind"], "navigation")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "conference_room")
        self.assertEqual(routed["room_title"], "Conference Room")
        self.assertFalse(routed.get("requires_confirmation", False))
        self.assertEqual(routed["tool"], "office.room_set")

    def test_meta_question_stays_in_model_route(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "why did you respond that way")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_advice_question_stays_in_model_route(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "what are the best restaurants to model mine after")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_restaurant_marketing_advice_stays_in_model_route(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "how should I improve my restaurant marketing")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_read_last_response_stays_in_model_route(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "read your last response")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_meta_question_with_tool_keyword_stays_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "why did you use reviews in that answer?")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_conversational_room_reference_requires_confirmation(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you talk to my office manager?")
        self.assertEqual(routed["route_kind"], "navigation")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "my_office")
        self.assertTrue(routed.get("requires_confirmation", False))
        self.assertEqual(routed["tool"], "office.room_set")

    def test_review_request_routes_to_review_search(self) -> None:
        routed = self.pipeline.route_user_request(
            "default",
            "based on yelp reviews over the last month, what are a few of the highest rated restaurants in Eugene?",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")
        self.assertEqual(routed["arguments"]["location"], "Eugene")

    def test_top_bars_request_routes_to_review_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "what are the top 5 bars in Eugene? check reviews")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")

    def test_best_restaurants_with_location_routes_to_review_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "what are the best italian restaurants in eugene?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")
        self.assertEqual(routed["arguments"]["query"], "italian restaurants")
        self.assertEqual(routed["arguments"]["location"], "eugene")

    def test_restaurant_followup_uses_recent_search_context(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "what about ambrosia?",
            [
                {
                    "role": "user",
                    "text": "what are the best italian restaurants in eugene?",
                },
                {
                    "role": "assistant",
                    "text": "Review-oriented results for 'italian restaurants':",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")
        self.assertEqual(routed["arguments"]["query"], "ambrosia italian restaurant")
        self.assertEqual(routed["arguments"]["location"], "eugene")

    def test_entity_followup_uses_grounded_search_evidence(self) -> None:
        routed = self.sales_pipeline.route_contextual_followup(
            "default",
            "does it have live music?",
            [
                {
                    "role": "user",
                    "text": "search for blairally and give me information about the company",
                },
                {
                    "role": "assistant",
                    "text": "Search results describe Blairally as a music venue/arcade in Eugene, Oregon.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.entity_followup")
        self.assertIn("Yes, search results describe it as a music venue/arcade", routed["arguments"]["response_text"])
        self.assertIn("Check the current event calendar for specific dates.", routed["arguments"]["response_text"])

    def test_numbered_list_followup_rewrites_to_model_question(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "what the most powerful one used in marketing?",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
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
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "Which single level of Maslow's hierarchy of needs is most powerful in marketing? "
            "Answer with one level first, then a brief reason.",
        )

    def test_numbered_list_followup_rewrites_explicit_level_reference(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "whats the most powerful level used in marketing?",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
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
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "Which single level of Maslow's hierarchy of needs is most powerful in marketing? "
            "Answer with one level first, then a brief reason.",
        )

    def test_numbered_list_followup_can_recover_after_intervening_bad_answer(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "what the most powerful one used in marketing?",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
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
                {
                    "role": "user",
                    "text": "whats the most powerful level used in marketing?",
                },
                {
                    "role": "assistant",
                    "text": "The most powerful tool in marketing is subjective and depends on the campaign.",
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

    def test_numbered_list_followup_rewrites_first_one_reference(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "tell me more about the first one",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Maslow's Hierarchy of Needs is a theory of motivation.\n\n"
                        "The levels are:\n"
                        "1. Physiological Needs\n"
                        "2. Safety Needs\n"
                        "3. Love and Belonging Needs"
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "Tell me more about the first level in Maslow's hierarchy of needs.",
        )

    def test_numbered_list_followup_rewrites_compare_reference(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "how does that compare?",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Maslow's Hierarchy of Needs is a theory of motivation.\n\n"
                        "The levels are:\n"
                        "1. Physiological Needs\n"
                        "2. Safety Needs\n"
                        "3. Love and Belonging Needs"
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "How does that compare with the other levels in Maslow's hierarchy of needs?",
        )

    def test_numbered_list_followup_rewrites_work_reference(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "would that work for bars too?",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Maslow's Hierarchy of Needs is a theory of motivation.\n\n"
                        "The levels are:\n"
                        "1. Physiological Needs\n"
                        "2. Safety Needs\n"
                        "3. Love and Belonging Needs"
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "Would that level from Maslow's hierarchy of needs also work for bars?",
        )

    def test_meta_followup_rewrites_to_previous_claim(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "how did you come to that conclusion?",
            [
                {
                    "role": "user",
                    "text": "what is maslow's hierarchy of needs?",
                },
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
                {
                    "role": "user",
                    "text": "whats the most powerful level used in marketing?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "The most powerful single level of Maslow's hierarchy of needs in marketing is **Esteem**.\n\n"
                        "This is because once basic needs are met, consumers are motivated by a desire for self-respect, "
                        "status, recognition, and achievement."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("Explain why you concluded that Esteem is the most powerful single level of Maslow's hierarchy of needs in marketing.", prompt)
        self.assertIn("Tie the explanation to the immediately previous answer", prompt)
        self.assertIn("Use plain text only, not a table", prompt)

    def test_meta_followup_what_makes_you_say_that_rewrites_to_previous_claim(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "what makes you say that?",
            [
                {
                    "role": "user",
                    "text": "whats the most powerful level used in marketing?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "The most powerful single level of Maslow's hierarchy of needs in marketing is **Esteem**.\n\n"
                        "This is because consumers are often motivated by status and recognition."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("Explain why you concluded that Esteem is the most powerful single level of Maslow's hierarchy of needs in marketing.", prompt)
        self.assertIn("Tie the explanation to the immediately previous answer", prompt)
        self.assertIn("Use plain text only, not a table", prompt)

    def test_meta_followup_rewrites_short_label_claim(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "how did you come to that conclusion?",
            [
                {
                    "role": "user",
                    "text": "what is maslo's heirachy of needs?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Maslow's Hierarchy of Needs is a psychological theory.\n\n"
                        "The levels are:\n"
                        "1. Physiological Needs\n"
                        "2. Safety Needs\n"
                        "3. Love and Belonging Needs\n"
                        "4. Esteem Needs\n"
                        "5. Self-Actualization Needs"
                    ),
                },
                {
                    "role": "user",
                    "text": "whats the most powerful level used in marketing?",
                },
                {
                    "role": "assistant",
                    "text": "Esteem. It taps into consumers' desire for recognition, status, and self-respect, which can be powerful motivators for purchasing decisions.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("Explain why you concluded that Esteem is the most powerful single level of Maslow's hierarchy of needs in marketing.", prompt)
        self.assertIn("Tie the explanation to the immediately previous answer", prompt)
        self.assertIn("Use plain text only, not a table", prompt)

    def test_plain_sentence_list_followup_rewrites_which_one(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "which one is most effective?",
            [
                {
                    "role": "user",
                    "text": "what are the main ways bars increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Bars typically increase repeat customers through a combination of excellent service, "
                        "a welcoming atmosphere, loyalty programs, consistent quality in food and drinks, "
                        "and engaging with customers to build relationships."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("For bars increase repeat customers, choose the single strongest option from this list:", prompt)
        self.assertIn("excellent service", prompt)
        self.assertIn("loyalty programs", prompt)
        self.assertIn("state the criteria you used", prompt)
        self.assertIn("Use plain text only, not a table", prompt)
        self.assertIn("legal, regulatory, safety, financial, or policy risk", prompt)

    def test_plain_sentence_list_followup_rewrites_most_powerful_one_to_use(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "whats the most powerful one to use?",
            [
                {
                    "role": "user",
                    "text": "what are the main ways bars increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "The main ways bars increase repeat customers are by excellent service, "
                        "creating a unique atmosphere and experience, implementing a loyalty program, "
                        "ensuring consistent quality of service and products, and building a sense of community."
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("For bars increase repeat customers, choose the single strongest option from this list:", prompt)
        self.assertIn("creating a unique atmosphere and experience", prompt)
        self.assertIn("implementing a loyalty program", prompt)
        self.assertIn("Answer with one option first", prompt)
        self.assertIn("Use plain text only, not a table", prompt)

    def test_plain_sentence_list_meta_followup_rewrites_why_that_one(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "why that one?",
            [
                {
                    "role": "user",
                    "text": "what are the main ways bars increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Bars typically increase repeat customers through a combination of excellent service, "
                        "a welcoming atmosphere, loyalty programs, consistent quality in food and drinks, "
                        "and engaging with customers to build relationships."
                    ),
                },
                {
                    "role": "user",
                    "text": "which one is most effective?",
                },
                {
                    "role": "assistant",
                    "text": "Excellent service is typically the most effective factor because it creates positive experiences that naturally encourage customers to return.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("Explain why you concluded that Excellent service is the strongest option", prompt)
        self.assertIn("bars increase repeat customers", prompt)
        self.assertIn("state the criteria used", prompt)
        self.assertIn("next strongest alternative", prompt)
        self.assertIn("Use plain text only, not a table", prompt)

    def test_what_about_new_industry_rewrites_against_prior_sales_thread(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "what about cellphone companies?",
            [
                {
                    "role": "user",
                    "text": "what are the main ways bars increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": "1. Service quality\n2. Atmosphere\n3. Community\n4. Consistency\n5. Events",
                },
                {
                    "role": "user",
                    "text": "which one is most effective?",
                },
                {
                    "role": "assistant",
                    "text": "Service quality is the strongest option.",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("previous discussion about bars increase repeat customers", prompt)
        self.assertIn("cellphone companies", prompt)
        self.assertIn("same thread", prompt)

    def test_what_about_cold_calling_uses_current_insurance_thread_not_older_cellphone_topic(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "what about cold calling?",
            [
                {
                    "role": "user",
                    "text": "what are the main ways cellphone stores increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": "1. Promotions\n2. Loyalty programs\n3. Service quality",
                },
                {
                    "role": "user",
                    "text": "whats the most effective one of those?",
                },
                {
                    "role": "assistant",
                    "text": "Service quality is the strongest option.",
                },
                {
                    "role": "user",
                    "text": "whats the best way for an insurance agent to find new customers?",
                },
                {
                    "role": "assistant",
                    "text": "The best way is building a strong referral network.",
                },
                {
                    "role": "user",
                    "text": "list the top 5 ways",
                },
                {
                    "role": "assistant",
                    "text": (
                        "Here are the top 5 ways for an insurance agent to find new customers, ranked by effectiveness:\n"
                        "1. Build a strong referral network\n"
                        "2. Targeted digital marketing\n"
                        "3. Networking at local events"
                    ),
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("insurance agent to find new customers", prompt)
        self.assertIn("cold calling", prompt)
        self.assertNotIn("cellphone", prompt)

    def test_non_list_followup_does_not_rewrite_which_one(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "which one?",
            [
                {
                    "role": "user",
                    "text": "what can you do?",
                },
                {
                    "role": "assistant",
                    "text": "I can chat, search the web, and manage files.",
                },
            ],
        )
        self.assertIsNone(routed)

    def test_bar_repeat_customer_advice_prompt_is_rewritten(self) -> None:
        routed = self.pipeline.route_user_request("default", "what are the main ways bars increase repeat customers?")
        self.assertEqual(routed["route_kind"], "model")
        prompt = routed["arguments"]["user_prompt"]
        self.assertIn("User request: what are the main ways bars increase repeat customers?", prompt)
        self.assertIn("Provide a complete numbered list of 5 substantive items", prompt)
        self.assertIn("Do not stop after the first item.", prompt)
        self.assertIn("legal, regulatory, safety, financial, or policy risk", prompt)

    def test_partial_list_feedback_rewrites_to_continue_numbered_list(self) -> None:
        routed = self.pipeline.route_contextual_followup(
            "default",
            "you only listed 1...service quality",
            [
                {
                    "role": "user",
                    "text": "what are the main ways bars increase repeat customers?",
                },
                {
                    "role": "assistant",
                    "text": "1. Service Quality",
                },
            ],
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(
            routed["arguments"]["user_prompt"],
            "Continue the incomplete list for bars increase repeat customers. "
            "Keep the existing item 1 unless the user explicitly asks to revise it. "
            "Provide items 2 through 5 as concise numbered lines only. "
            "Use plain text only: no markdown tables, no pipe tables, and no markdown bold.",
        )

    def test_find_restaurants_near_me_routes_to_places_with_missing_location(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "Find restaurants near me")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "restaurants")
        self.assertEqual(routed["arguments"]["category"], "restaurants")
        self.assertIsNone(routed["arguments"]["location"])
        self.assertTrue(routed["arguments"]["needs_location"])

    def test_misspelled_local_restaurants_routes_to_places_with_missing_location(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "what local resaurnats are the best")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "restaurants")
        self.assertEqual(routed["arguments"]["category"], "restaurants")
        self.assertIsNone(routed["arguments"]["location"])
        self.assertTrue(routed["arguments"]["needs_location"])

    def test_unknown_misspelling_asks_for_clarification(self) -> None:
        routed = self.pipeline.route_user_request("default", "uplod my document")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.spelling")
        self.assertEqual(routed["arguments"]["word"], "uplod")
        self.assertEqual(routed["arguments"]["suggestion"], "upload")

    def test_find_restaurants_in_portland_routes_to_places_with_location(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "Find restaurants in Portland")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "restaurants")
        self.assertEqual(routed["arguments"]["category"], "restaurants")
        self.assertEqual(routed["arguments"]["location"], "Portland")
        self.assertFalse(routed["arguments"]["needs_location"])

    def test_find_thai_restaurants_near_me_routes_to_places_with_normalized_query(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "Find Thai restaurants near me")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "thai restaurants")
        self.assertEqual(routed["arguments"]["category"], "thai")
        self.assertTrue(routed["arguments"]["needs_location"])

    def test_search_reviews_for_restaurants_in_portland_routes_to_reviews(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "search reviews for restaurants in Portland")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")
        self.assertEqual(routed["arguments"]["location"], "Portland")

    def test_unqualified_bar_question_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "how do you increase food sales in a bar")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_business_advice_question_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "how do you increase food sales in a bar")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_conceptual_restaurant_question_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "what makes a restaurant successful?")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_explicit_search_of_advice_topic_routes_to_web_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "search the web for restaurant marketing strategy")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")

    def test_search_capability_question_gets_deterministic_answer(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you search the internet?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.search.info")
        self.assertIn("Yes. I can search the internet", routed["arguments"]["response_text"])
        self.assertIn("Here in Lobby", routed["arguments"]["response_text"])
        self.assertIn("memo system", routed["arguments"]["response_text"])

    def test_upload_capability_question_gets_deterministic_answer(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you upload files?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.upload.info")
        self.assertIn("Use the Save/Upload controls", routed["arguments"]["response_text"])

    def test_download_help_gets_deterministic_answer(self) -> None:
        routed = self.pipeline.route_user_request("default", "how do i download files here?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.download.info")
        self.assertIn("Open Load", routed["arguments"]["response_text"])

    def test_document_read_capability_question_gets_deterministic_answer(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you read uploaded documents?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.document_read.info")
        self.assertIn("extract text", routed["arguments"]["response_text"])

    def test_room_capability_question_gets_deterministic_answer(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you switch rooms?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.rooms.info")
        self.assertIn("go to Sales Department", routed["arguments"]["response_text"])

    def test_session_capability_question_gets_deterministic_answer(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you create sessions?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.sessions.info")
        self.assertIn("new session for", routed["arguments"]["response_text"])

    def test_general_capability_question_gets_overview(self) -> None:
        routed = self.pipeline.route_user_request("default", "what can you do?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.overview.info")
        self.assertIn("search the web", routed["arguments"]["response_text"])
        self.assertIn("Greets users", routed["arguments"]["response_text"])
        self.assertIn("coordinate with other departments through the memo system", routed["arguments"]["response_text"])

    def test_general_capability_question_in_marketing_includes_room_role(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="marketing_room", active_persona="Marketing Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what can you do?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.overview.info")
        self.assertIn("Here in Marketing & Advertising", routed["arguments"]["response_text"])
        self.assertIn("Market research, campaign planning", routed["arguments"]["response_text"])
        self.assertIn("memo system", routed["arguments"]["response_text"])

    def test_general_capability_question_in_it_includes_room_role(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="it_department", active_persona="IT Administrator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what can you do?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "capability.overview.info")
        self.assertIn("Here in IT Department", routed["arguments"]["response_text"])
        self.assertIn("Technical support", routed["arguments"]["response_text"])
        self.assertIn("memo system", routed["arguments"]["response_text"])

    def test_search_capability_with_query_routes_to_web_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you search the internet for Eugene events?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")

    def test_explicit_web_search_routes_to_web_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "search the internet for Eugene networking events")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")

    def test_ocr_request_routes_to_document_ocr(self) -> None:
        routed = self.pipeline.route_user_request("default", "extract text from file_abc123")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "document.ocr")
        self.assertEqual(routed["tool"], "office.ocr_extract")
        self.assertEqual(routed["arguments"]["file_id"], "file_abc123")

    def test_read_file_request_routes_to_document_ocr(self) -> None:
        routed = self.pipeline.route_user_request("default", "read file test_file_4")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "document.ocr")
        self.assertEqual(routed["tool"], "office.ocr_extract")

    def test_ocr_request_routes_to_document_ocr_by_filename(self) -> None:
        routed = self.pipeline.route_user_request("default", "extract text from JW_Cover.rtf")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "document.ocr")
        self.assertEqual(routed["tool"], "office.ocr_extract")
        self.assertEqual(routed["arguments"]["file_name"], "JW_Cover.rtf")

    def test_read_named_file_is_not_intercepted_as_capability_question(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you read file JW_Cover.rtf?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "document.ocr")
        self.assertEqual(routed["tool"], "office.ocr_extract")

    def test_ocr_request_routes_from_show_me_followup(self) -> None:
        routed = self.pipeline.route_user_request("default", "show me the extracted text from JW_Cover.rtf")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "document.ocr")
        self.assertEqual(routed["tool"], "office.ocr_extract")
        self.assertEqual(routed["arguments"]["file_name"], "JW_Cover.rtf")

    def test_show_me_alone_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "show me")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_model_route_forbids_fake_background_work(self) -> None:
        routed = self.pipeline.route_user_request("default", "help me think through a menu idea")
        self.assertEqual(routed["route_kind"], "model")
        self.assertIn("Do not claim you are searching", routed["arguments"]["system_prompt"])
        self.assertIn("Use the provided session conversation history", routed["arguments"]["system_prompt"])
        self.assertIn("Answer normal advice", routed["arguments"]["system_prompt"])
        self.assertIn("how did you come to that conclusion?", routed["arguments"]["system_prompt"])
        self.assertIn("do not invent unsupported details", routed["arguments"]["system_prompt"].lower())

    def test_broad_room_help_stays_model_with_room_context_instruction(self) -> None:
        routed = self.pipeline.route_user_request("default", "what can you help me with here?")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertIn("answer from the active room and persona", routed["arguments"]["system_prompt"])
        self.assertIn("Do not deny these Veridex capabilities", routed["arguments"]["system_prompt"])
        self.assertIn("Apply active-room behavior memory", routed["arguments"]["system_prompt"])

    def test_remember_in_sales_routes_to_room_memory_tool(self) -> None:
        routed = self.pipeline.route_user_request(
            "default",
            "remember in sales that the sales questions I'm asking pertain to businesses in Oregon",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.remember")
        self.assertEqual(routed["tool"], "office.room_memory_remember")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertEqual(
            routed["arguments"]["instruction"],
            "the sales questions I'm asking pertain to businesses in Oregon",
        )

    def test_remember_that_defaults_to_active_room(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "remember that sales questions pertain to Oregon businesses",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.remember")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")

    def test_from_now_on_sales_instruction_routes_to_room_memory_tool(self) -> None:
        routed = self.pipeline.route_user_request(
            "default",
            "i want you to answer my sales questions from now on with the book how to win friends and influence people in mind",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.remember")
        self.assertEqual(routed["tool"], "office.room_memory_remember")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertIn("how to win friends", routed["arguments"]["instruction"])

    def test_remember_to_filter_advice_routes_to_room_memory_tool(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "i want you to remember to filter your advice with the book 48 laws of power in mind",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.remember")
        self.assertEqual(routed["tool"], "office.room_memory_remember")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertIn("48 laws of power", routed["arguments"]["instruction"])

    def test_forget_sales_behavior_routes_to_room_memory_forget(self) -> None:
        routed = self.pipeline.route_user_request(
            "default",
            "forget in sales that how to win friends",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.forget")
        self.assertEqual(routed["tool"], "office.room_memory_forget")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertEqual(routed["arguments"]["match_text"], "how to win friends")

    def test_forget_without_room_uses_current_room(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "forget using how to win friends and influence people",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.forget")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertEqual(routed["arguments"]["match_text"], "using how to win friends and influence people")

    def test_forget_first_one_routes_to_numbered_room_memory_forget(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "forget the first one")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.forget")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertEqual(routed["arguments"]["memory_index"], 1)

    def test_forget_phrase_ending_in_mind_does_not_treat_mind_as_room(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "forget answer my sales questions from now on with the book how to win friends and influence people in mind",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.forget")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")
        self.assertIn("in mind", routed["arguments"]["match_text"])

    def test_ambiguous_forget_memory_asks_for_clarification(self) -> None:
        routed = self.pipeline.route_user_request("default", "forget that")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.room_memory")
        self.assertIn("Which remembered behavior", routed["arguments"]["response_text"])

    def test_memory_objects_question_routes_to_room_memory_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        for text in ("what memory objects do you have saved?", "what memory objects do i have saved?"):
            routed = pipeline.route_user_request("default", text)
            self.assertEqual(routed["route_kind"], "tool")
            self.assertEqual(routed["capability"], "room.memory.list")
            self.assertEqual(routed["tool"], "office.room_memory_list")
            self.assertEqual(routed["arguments"]["room_id"], "sales_department")

    def test_memory_items_saved_now_routes_to_room_memory_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what memory items are saved now?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.list")
        self.assertEqual(routed["tool"], "office.room_memory_list")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")

    def test_read_file_alone_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "read file")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_unknown_entity_lookup_fails_closed_without_search(self) -> None:
        routed = self.sales_pipeline.route_user_request(
            "default",
            "what can you tell me about blairally",
            session_id="sess_sales",
        )
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.entity_grounding")
        self.assertIn("I do not have verified information about blairally", routed["arguments"]["response_text"])

    def test_unknown_entity_lookup_does_not_trust_prior_hallucinated_assistant_turn(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "Blairally is a modern homegoods brand with premium pricing and AR previews.",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "what can you tell me about blairally",
            session_id="sess_sales",
        )
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("I do not have verified information about blairally", routed["arguments"]["response_text"])

    def test_search_for_entity_routes_to_web_search_with_grounding_required(self) -> None:
        routed = self.sales_pipeline.route_user_request(
            "default",
            "search for blairally and give me information about the company",
            session_id="sess_sales",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")
        self.assertTrue(routed["grounding_required"])
        self.assertEqual(routed["entity_subject"], "blairally")

    def test_non_navigation_break_phrase_does_not_switch_rooms(self) -> None:
        routed = self.pipeline.route_user_request("default", "did i break the thread?")
        self.assertEqual(routed["route_kind"], "model")

    def test_room_name_alone_does_not_switch_rooms(self) -> None:
        routed = self.pipeline.route_user_request("default", "break room")
        self.assertEqual(routed["route_kind"], "model")

    def test_room_status_query_routes_to_state_get(self) -> None:
        routed = self.pipeline.route_user_request("default", "where am i?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.state.get")
        self.assertEqual(routed["tool"], "office.state_get")

    def test_new_session_routes_to_session_create(self) -> None:
        routed = self.pipeline.route_user_request("default", "new session for event flier")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.create")
        self.assertEqual(routed["tool"], "office.session_create")
        self.assertEqual(routed["arguments"]["title"], "event flier")

    def test_new_session_without_name_routes_to_clarification(self) -> None:
        routed = self.pipeline.route_user_request("default", "start new session")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "session.create.name_required")
        self.assertEqual(routed["arguments"]["response_text"], "What should I name the new session?")

    def test_list_sessions_routes_to_sessions_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "list sessions")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.list")
        self.assertEqual(routed["tool"], "office.sessions_list")

    def test_go_to_session_number_routes_to_session_activate(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to session 3")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.activate")
        self.assertEqual(routed["tool"], "office.session_activate")
        self.assertEqual(routed["arguments"]["session_ref"], "3")

    def test_show_this_session_thread_routes_to_transcript(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you show this sessions thread?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.transcript.get")
        self.assertEqual(routed["tool"], "office.transcript_get")


if __name__ == "__main__":
    unittest.main()
