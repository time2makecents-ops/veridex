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

    def test_go_to_my_office_routes_to_my_office(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to my office")
        self.assertEqual(routed["route_kind"], "nancy")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "my_office")
        self.assertEqual(routed["room_title"], "My Office")
        self.assertFalse(routed.get("requires_confirmation", False))

    def test_go_to_conference_room_routes_to_conference_room(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to conference room")
        self.assertEqual(routed["route_kind"], "nancy")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "conference_room")
        self.assertEqual(routed["room_title"], "Conference Room")
        self.assertFalse(routed.get("requires_confirmation", False))

    def test_meta_question_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "why did you respond that way")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_advice_question_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "what are the best restaurants to model mine after")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_read_last_response_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "read your last response")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_meta_question_with_tool_keyword_stays_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "why did you use reviews in that answer?")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_conversational_room_reference_requires_confirmation(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you talk to my office manager?")
        self.assertEqual(routed["route_kind"], "nancy")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "my_office")
        self.assertTrue(routed.get("requires_confirmation", False))

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

    def test_find_restaurants_near_me_routes_to_places_with_missing_location(self) -> None:
        routed = self.pipeline.route_user_request("default", "Find restaurants near me")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "restaurants")
        self.assertEqual(routed["arguments"]["category"], "restaurants")
        self.assertIsNone(routed["arguments"]["location"])
        self.assertTrue(routed["arguments"]["needs_location"])

    def test_misspelled_local_restaurants_routes_to_places_with_missing_location(self) -> None:
        routed = self.pipeline.route_user_request("default", "what local resaurnats are the best")
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
        routed = self.pipeline.route_user_request("default", "Find restaurants in Portland")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "restaurants")
        self.assertEqual(routed["arguments"]["category"], "restaurants")
        self.assertEqual(routed["arguments"]["location"], "Portland")
        self.assertFalse(routed["arguments"]["needs_location"])

    def test_find_thai_restaurants_near_me_routes_to_places_with_normalized_query(self) -> None:
        routed = self.pipeline.route_user_request("default", "Find Thai restaurants near me")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "thai restaurants")
        self.assertEqual(routed["arguments"]["category"], "thai")
        self.assertTrue(routed["arguments"]["needs_location"])

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
        self.assertIn("Use recent turns only", routed["arguments"]["system_prompt"])
        self.assertIn("Answer normal advice", routed["arguments"]["system_prompt"])

    def test_broad_room_help_stays_model_with_room_context_instruction(self) -> None:
        routed = self.pipeline.route_user_request("default", "what can you help me with here?")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertIn("answer from the active room and persona", routed["arguments"]["system_prompt"])
        self.assertIn("Do not deny these Veridex capabilities", routed["arguments"]["system_prompt"])

    def test_read_file_alone_stays_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "read file")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

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


if __name__ == "__main__":
    unittest.main()
