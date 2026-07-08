from __future__ import annotations

import unittest

from office_app.server.persona_registry import persona_profile_for_name
from office_app.server.request_pipeline import RequestPipeline


class DummyKernel:
    def __init__(
        self,
        active_room: str = "lobby",
        active_persona: str = "Receptionist",
        gates: dict[str, bool] | None = None,
        transcript_rows: list[dict[str, str]] | None = None,
        grounded_search_by_session: dict[str, dict[str, object]] | None = None,
        pending_break_room_jokes: dict[str, dict[str, str]] | None = None,
        state: dict[str, object] | None = None,
    ):
        self.active_room = active_room
        self.active_persona = active_persona
        self.gates = gates or {"SAVE_GATE": True, "PREFLIGHT": True, "VERIFICATION": True}
        self.store = DummyStore(transcript_rows or [])
        self.grounded_search_by_session = grounded_search_by_session or {}
        self.pending_break_room_jokes = pending_break_room_jokes or {}
        self.state = state or {}

    def current_context(self, workspace_id: str):
        return {
            "active_room": self.active_room,
            "active_persona": self.active_persona,
            "active_persona_profile": persona_profile_for_name(self.active_persona),
        }

    def list_workspaces(self):
        return {"workspaces": []}

    def get_state(self, workspace_id: str):
        state = {
            "active_room": self.active_room,
            "active_persona": self.active_persona,
            "gates": self.gates,
            "grounded_search_by_session": self.grounded_search_by_session,
            "pending_break_room_jokes": self.pending_break_room_jokes,
        }
        state.update(self.state)
        return state


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

    def test_show_all_sessions_in_workspace_routes_to_session_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "show me all sessions in this workspace")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.list")
        self.assertEqual(routed["tool"], "office.sessions_list")

    def test_what_are_we_working_on_routes_to_work_context_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "what are we working on")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "work_context.list")
        self.assertEqual(routed["tool"], "office.work_context_list")
        self.assertEqual(routed["arguments"]["status"], "active")

    def test_clear_active_work_context_routes_to_work_context_complete(self) -> None:
        routed = self.pipeline.route_user_request("default", "clear active work context")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "work_context.complete")
        self.assertEqual(routed["tool"], "office.work_context_complete")
        self.assertTrue(routed["arguments"]["all_active"])

    def test_navigator_status_report_routes_to_diagnostics_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "Navigator, run a Veridex status report")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.status_report")
        self.assertEqual(routed["tool"], "office.navigator_status_report")

    def test_navigator_recent_errors_routes_to_recent_errors_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "Navigator, show recent errors")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.recent_errors")
        self.assertEqual(routed["tool"], "office.navigator_recent_errors")

    def test_navigator_explain_error_routes_to_error_explanation_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "Navigator, why did that fail?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.explain_error")
        self.assertEqual(routed["tool"], "office.navigator_explain_error")

    def test_navigator_explain_this_error_routes_to_error_explanation_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "Navigator, explain this error: connection refused")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.explain_error")
        self.assertEqual(routed["tool"], "office.navigator_explain_error")

    def test_navigator_what_is_wrong_routes_to_status_report(self) -> None:
        routed = self.pipeline.route_user_request("default", "Navigator, what is wrong?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.status_report")
        self.assertEqual(routed["tool"], "office.navigator_status_report")

    def test_navigator_run_smoke_test_routes_to_allowed_check_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "Navigator, run the standard smoke test")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.run_check")
        self.assertEqual(routed["tool"], "office.navigator_run_check")
        self.assertEqual(routed["arguments"]["check_name"], "standard_smoke")

    def test_bare_run_tests_does_not_route_to_navigator_check(self) -> None:
        routed = self.pipeline.route_navigator_diagnostics_request("ws_test", "run tests")
        self.assertIsNone(routed)

    def test_navigator_evidence_followup_routes_to_recent_errors(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Navigator",
                        "text": (
                            "I can see the failure text, but it does not match a known diagnostic category. "
                            "Next step: Run recent errors and a status report so I can compare it with logs and incidents."
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "do that", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.recent_errors")
        self.assertEqual(routed["tool"], "office.navigator_recent_errors")

    def test_navigator_report_followup_routes_to_status_report(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Navigator",
                        "text": (
                            "Navigator found 1 recent incident(s), 2 backend log line(s), "
                            "and 0 frontend log line(s)."
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "give me a detailed report", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.status_report")
        self.assertEqual(routed["tool"], "office.navigator_status_report")

    def test_navigator_check_followup_routes_to_allowlisted_check(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Navigator",
                        "text": (
                            "A local backend or frontend connection failed. "
                            "Next step: Restart Veridex and run the standard smoke test before retrying."
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "run the standard smoke", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.run_check")
        self.assertEqual(routed["tool"], "office.navigator_run_check")
        self.assertEqual(routed["arguments"]["check_name"], "standard_smoke")

    def test_navigator_recommendation_followup_routes_to_first_allowlisted_check(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Navigator",
                        "text": (
                            "A local backend or frontend connection failed. Next step: Restart Veridex and run the standard smoke test before retrying.\n"
                            "Recommendations:\n"
                            "1. Run standard smoke test (run_standard_smoke, standard_smoke)."
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "run the first one", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.run_check")
        self.assertEqual(routed["tool"], "office.navigator_run_check")
        self.assertEqual(routed["arguments"]["check_name"], "standard_smoke")

    def test_navigator_report_recommendation_followup_routes_to_status_report(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Navigator",
                        "text": (
                            "I can see the failure text, but it does not match a known diagnostic category.\n"
                            "Recommendations:\n"
                            "1. Run recent errors (run_recent_errors).\n"
                            "2. Run status report (run_status_report)."
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "show me the report", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "navigator.status_report")
        self.assertEqual(routed["tool"], "office.navigator_status_report")

    def test_complete_active_work_number_routes_to_work_context_complete_index(self) -> None:
        routed = self.pipeline.route_user_request("default", "complete active work 2")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "work_context.complete")
        self.assertEqual(routed["tool"], "office.work_context_complete")
        self.assertEqual(routed["arguments"]["active_index"], 2)

    def test_track_active_work_routes_to_work_context_save(self) -> None:
        routed = self.pipeline.route_user_request("default", "track active work: finalize the launch plan with marketing")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "work_context.save")
        self.assertEqual(routed["tool"], "office.work_context_save")
        self.assertEqual(routed["arguments"]["title"], "finalize the launch plan with marketing")
        self.assertEqual(routed["arguments"]["summary"], "finalize the launch plan with marketing")

    def test_set_current_work_routes_to_replacing_work_context_save(self) -> None:
        routed = self.pipeline.route_user_request("default", "set current work to finalize the launch plan with marketing")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "work_context.save")
        self.assertEqual(routed["tool"], "office.work_context_save")
        self.assertEqual(routed["arguments"]["title"], "finalize the launch plan with marketing")
        self.assertEqual(routed["arguments"]["summary"], "finalize the launch plan with marketing")
        self.assertTrue(routed["arguments"]["replace_active_manual"])

    def test_list_rooms_routes_to_room_directory(self) -> None:
        routed = self.pipeline.route_user_request("default", "list rooms")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "room.directory")
        self.assertEqual(routed["tool"], "office.capability_info")

    def test_list_all_departments_and_rooms_routes_to_room_directory(self) -> None:
        routed = self.pipeline.route_user_request("default", "list all departments and rooms")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "room.directory")
        self.assertEqual(routed["tool"], "office.capability_info")

    def test_control_room_role_question_routes_to_capability_info(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="control_room", active_persona="Navigator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what is your role in the app?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "room.persona_role")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("Navigator", routed["arguments"]["response_text"])
        self.assertIn("system governance authority", routed["arguments"]["response_text"].lower())

    def test_control_room_guidelines_question_routes_to_governance_registry_answer(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="control_room", active_persona="Navigator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what are the veridex guidelines?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "control_room.governance")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("one active room at a time", routed["arguments"]["response_text"])
        self.assertIn("Veridex_Governance_Guide_v1.0.0.md", routed["arguments"]["response_text"])
        self.assertIn("registry.csv", routed["arguments"]["response_text"])

    def test_control_room_gates_question_routes_to_governance_registry_answer(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="control_room", active_persona="Navigator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what gates do you enforce?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "control_room.governance")
        self.assertIn("SAVE_GATE", routed["arguments"]["response_text"])
        self.assertIn("GATE-PREFLIGHT", routed["arguments"]["response_text"])

    def test_what_sessions_are_in_this_workspace_routes_to_clarify(self) -> None:
        routed = self.pipeline.route_user_request("default", "what sessions are in this workspace")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "session.list.confirmation")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("list the sessions in this workspace", routed["arguments"]["response_text"])

    def test_what_sessions_are_there_routes_to_clarify(self) -> None:
        routed = self.pipeline.route_user_request("default", "what sessions are there")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "session.list.confirmation")
        self.assertEqual(routed["tool"], "office.capability_info")

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

    def test_numbered_delete_after_artifact_list_routes_to_artifact_delete(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "Found 2 artifact(s) (this workspace).\n1. room_behavior_memory: Sales Department behavior memory (art_1) - follow up with the client.\n2. room_behavior_memory: Sales Department behavior memory (art_2) - grow repeat customers.",
                    }
                ]
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "delete 1", session_id="sess_123")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.delete")
        self.assertEqual(routed["tool"], "office.artifact_delete")
        self.assertEqual(routed["arguments"]["artifact_id"], "art_1")

    def test_numbered_delete_without_recent_artifact_list_asks_for_clarification(self) -> None:
        routed = self.pipeline.route_user_request("default", "delete 1", session_id="sess_123")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.artifact_delete")
        self.assertIn("Which listed workspace artifact should I delete?", routed["arguments"]["response_text"])

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

    def test_art_room_routes_to_art_department_not_vr_room(self) -> None:
        for phrase in (
            "go to art room",
            "take me to art room",
            "send me to art room",
            "route me to art room",
            "direct me to art room",
        ):
            with self.subTest(phrase=phrase):
                routed = self.pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "navigation")
                self.assertEqual(routed["room_id"], "art_department")
                self.assertEqual(routed["room_title"], "Art Department")

    def test_room_navigation_aliases_route_to_correct_rooms(self) -> None:
        cases = (
            ("go to reception", "lobby"),
            ("go to conference room", "conference_room"),
            ("go to navigator room", "control_room"),
            ("go to infrastructure room", "infrastructure_room"),
            ("go to sales room", "sales_department"),
            ("go to marketing room", "marketing_room"),
            ("go to hr room", "hr_department"),
            ("go to it room", "it_department"),
            ("go to art room", "art_department"),
            ("go to law room", "law_office"),
            ("go to finance room", "finance_department"),
            ("go to my office", "my_office"),
            ("go to vr room", "vr_room"),
            ("go to records room", "records_archive"),
            ("go to rnd room", "rnd_room"),
            ("go to security room", "security_room"),
            ("go to break room", "break_room"),
        )
        for phrase, expected_room in cases:
            with self.subTest(phrase=phrase):
                routed = self.pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "navigation")
                self.assertEqual(routed["room_id"], expected_room)
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

    def test_phone_camera_question_stays_in_model_route(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "what cellphones have the best cameras?")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertEqual(routed["reason"], "Conversation-first intent matched before broad tool routing.")

    def test_explicit_product_search_still_routes_to_web_search(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "search the web for cellphones with the best cameras")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")

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

    def test_entity_hours_followup_uses_preserved_grounded_search_context(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                grounded_search_by_session={
                    "sess_sales": {
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
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_contextual_followup(
            "default",
            "what are the hours again?",
            [],
            session_id="sess_sales",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("4 PM to 2 AM", routed["arguments"]["response_text"])

    def test_entity_location_followup_uses_preserved_grounded_search_context(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                grounded_search_by_session={
                    "sess_sales": {
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
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_contextual_followup(
            "default",
            "what state is it in?",
            [],
            session_id="sess_sales",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("Eugene, Oregon", routed["arguments"]["response_text"])

    def test_entity_provenance_followup_reports_wrong_time_was_not_grounded(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                grounded_search_by_session={
                    "sess_sales": {
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
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_contextual_followup(
            "default",
            "what search result said 4am instead of 4pm?",
            [],
            session_id="sess_sales",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertIn("I do not have a preserved search result snippet that says 4 AM", routed["arguments"]["response_text"])
        self.assertIn("The preserved result I have says 4 PM", routed["arguments"]["response_text"])

    def test_entity_unsupported_attribute_followup_fails_closed(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                grounded_search_by_session={
                    "sess_sales": {
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
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_contextual_followup(
            "default",
            "who owns it?",
            [],
            session_id="sess_sales",
        )
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(
            routed["arguments"]["response_text"],
            "I do not have a preserved search result snippet that answers that ownership question.",
        )

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

    def test_ambiguous_choice_followup_with_unverified_entity_fails_closed(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "tell me about blairally"},
                    {"role": "assistant", "text": "I do not have verified information about blairally."},
                ]
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "which one?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.unsafe_followup")
        self.assertIn("do not have a verified answer", routed["arguments"]["response_text"])

    def test_ambiguous_choice_followup_after_unverified_entity_asks_for_clarification(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "tell me about blairally"},
                    {"role": "assistant", "text": "I do not have verified information about blairally."},
                ]
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "why that one?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.unsafe_followup")
        self.assertIn("do not have a verified answer", routed["arguments"]["response_text"])

    def test_reflective_followup_after_unverified_entity_does_not_invent_reasoning(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "tell me about blairally"},
                    {"role": "assistant", "text": "I do not have verified information about blairally."},
                ]
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "how did you come to that conclusion?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.unsafe_followup")
        self.assertIn("There was no verified conclusion", routed["arguments"]["response_text"])

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

    def test_mall_question_with_location_routes_to_places(self) -> None:
        routed = self.sales_pipeline.route_user_request(
            "default",
            "in eugene we have two major malls. can you tell me which ones they are?",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "malls")
        self.assertEqual(routed["arguments"]["category"], "malls")
        self.assertEqual(routed["arguments"]["location"], "eugene")

    def test_major_bars_with_location_routes_to_places(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "what are the major bars in Eugene?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.places")
        self.assertEqual(routed["tool"], "office.search_places")
        self.assertEqual(routed["arguments"]["query"], "bars")
        self.assertEqual(routed["arguments"]["category"], "bars")
        self.assertEqual(routed["arguments"]["location"], "Eugene")

    def test_local_bars_with_saved_session_location_routes_to_review_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                transcript_rows=[
                    {"role": "user", "text": "save that i am located in Oregon."},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what local bars have the highest reviews?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")
        self.assertEqual(routed["arguments"]["location"], "Oregon")

    def test_best_local_bars_with_saved_session_location_routes_to_review_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                transcript_rows=[
                    {"role": "assistant", "text": "I've saved that you're located in Oregon."},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what are the best local bars?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.reviews")
        self.assertEqual(routed["tool"], "office.search_reviews")
        self.assertEqual(routed["arguments"]["location"], "Oregon")

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
        self.assertIn("Records Archive", routed["arguments"]["response_text"])

    def test_lobby_room_directory_phrases_get_complete_room_directory(self) -> None:
        phrases = (
            "What rooms are there",
            "What departments are there?",
            "Is there a list of places I can go in Veridex?",
            "List all offices",
            "All departments",
            "What offices?",
            "where can I go",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                routed = self.pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "clarify")
                self.assertEqual(routed["capability"], "room.directory")
                self.assertEqual(routed["tool"], "office.capability_info")
                text = routed["arguments"]["response_text"]
                self.assertIn("Sales Department", text)
                self.assertIn("Marketing & Advertising", text)
                self.assertIn("Law Office", text)
                self.assertIn("Records Archive", text)
                self.assertIn("Research & Development", text)

    def test_lobby_room_directory_followups_use_recent_room_context(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "What rooms are there"},
                    {"role": "assistant", "text": "This workspace has rooms, departments, and offices."},
                ]
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        for phrase in ("Can you list all of them please", "Specific offices"):
            with self.subTest(phrase=phrase):
                routed = pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "clarify")
                self.assertEqual(routed["capability"], "room.directory")
                self.assertIn("Records Archive", routed["arguments"]["response_text"])

    def test_break_room_joke_request_pauses_before_punchline(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="break_room", active_persona="Break Room Host"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "tell me a joke")
        self.assertEqual(routed["route_kind"], "break_room_joke")
        self.assertEqual(routed["capability"], "break_room.joke.generate")
        self.assertEqual(routed["tool"], "office.ai_generate")

    def test_break_room_joke_followup_reveals_punchline(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="break_room",
                active_persona="Break Room Host",
                pending_break_room_jokes={
                    "sess_1": {
                        "setup": "Why did the project manager bring a ladder to the meeting?",
                        "punchline": "Because the team said the goals were too high.",
                    }
                },
                transcript_rows=[
                    {"role": "user", "text": "tell me a joke"},
                    {
                        "role": "assistant",
                        "text": "Why did the project manager bring a ladder to the meeting?",
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "because the room was upstairs?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "break_room.joke.punchline")
        self.assertIn("Because the team said the goals were too high.", routed["arguments"]["response_text"])
        self.assertTrue(routed["arguments"]["clear_pending_break_room_joke"])

    def test_break_room_cancel_clears_pending_joke_without_revealing_punchline(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="break_room",
                active_persona="Break Room Host",
                pending_break_room_jokes={
                    "sess_1": {
                        "setup": "Why did the project manager bring a ladder to the meeting?",
                        "punchline": "Because the team said the goals were too high.",
                    }
                },
                transcript_rows=[
                    {"role": "user", "text": "tell me a joke"},
                    {
                        "role": "assistant",
                        "text": "Why did the project manager bring a ladder to the meeting?",
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "cancel", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "break_room.joke.cancelled")
        self.assertEqual(routed["arguments"]["response_text"], "Okay. I cleared the pending Break Room joke.")
        self.assertTrue(routed["arguments"]["clear_pending_break_room_joke"])
        self.assertNotIn("Because the team said the goals were too high.", routed["arguments"]["response_text"])

    def test_break_room_correct_joke_guess_is_acknowledged(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="break_room",
                active_persona="Break Room Host",
                pending_break_room_jokes={
                    "sess_1": {
                        "setup": "Why did the project manager bring a ladder to the meeting?",
                        "punchline": "Because the team said the goals were too high.",
                    }
                },
                transcript_rows=[
                    {"role": "user", "text": "tell me a joke"},
                    {"role": "assistant", "text": "Why did the project manager bring a ladder to the meeting?"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "because the goals were too high", session_id="sess_1")
        self.assertEqual(routed["capability"], "break_room.joke.punchline")
        self.assertIn("Exactly.", routed["arguments"]["response_text"])

    def test_break_room_yes_after_another_offer_starts_setup_only(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="break_room",
                active_persona="Break Room Host",
                transcript_rows=[
                    {"role": "assistant", "text": "Why did the project manager bring a ladder to the meeting?"},
                    {
                        "role": "assistant",
                        "text": "Because the team said the goals were too high.\n\nWant another one?",
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "sure")
        self.assertEqual(routed["route_kind"], "break_room_joke")
        self.assertEqual(routed["capability"], "break_room.joke.generate")
        self.assertEqual(routed["tool"], "office.ai_generate")

    def test_pending_break_room_joke_does_not_block_navigation(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="break_room",
                active_persona="Break Room Host",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "Why did the project manager bring a ladder to the meeting?",
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "go to the lobby")
        self.assertEqual(routed["route_kind"], "navigation")
        self.assertEqual(routed["room_id"], "lobby")

    def test_repeating_joke_setup_with_go_to_does_not_trigger_navigation(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="break_room", active_persona="Break Room Host"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            'you asked why did the mushroom go to the party, which is a fungi and sounds like "fun guy"',
            session_id="sess_1",
        )
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")

    def test_send_memo_to_navigator_routes_to_mailroom_dispatch(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="lobby", active_persona="Receptionist"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send a memo to the navigator. how is system health?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "memo.dispatch")
        self.assertEqual(routed["tool"], "mailroom.dispatch")
        self.assertEqual(routed["arguments"]["to_room"], "control_room")
        self.assertEqual(routed["arguments"]["explicit_persona"], "Navigator")
        self.assertEqual(routed["arguments"]["body"], "how is system health?")

    def test_send_memo_to_routes_to_mailroom_dispatch_in_all_rooms(self) -> None:
        rooms = (
            ("lobby", "Receptionist"),
            ("sales_department", "Sales Director"),
            ("marketing_room", "Marketing Director"),
        )
        for active_room, active_persona in rooms:
            with self.subTest(active_room=active_room):
                pipeline = RequestPipeline(
                    kernel=DummyKernel(active_room=active_room, active_persona=active_persona),
                    navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
                    utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                    tool_names=[],
                    app_version="1.3.0",
                )
                routed = pipeline.route_user_request("default", "send a memo to sales. please review this lead")
                self.assertEqual(routed["route_kind"], "tool")
                self.assertEqual(routed["capability"], "memo.dispatch")
                self.assertEqual(routed["tool"], "mailroom.dispatch")
                self.assertEqual(routed["arguments"]["to_room"], "sales_department")
                self.assertEqual(routed["arguments"]["explicit_persona"], "Sales Director")
                self.assertEqual(routed["arguments"]["body"], "please review this lead")

    def test_break_room_memo_dispatch_is_blocked_by_room_capability(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="break_room", active_persona="Break Room Host"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send a memo to sales. please review this lead")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "memo.dispatch.blocked")
        self.assertIn("Break Room is non-operational", routed["arguments"]["response_text"])

    def test_memo_list_requests_route_to_memos_list(self) -> None:
        for phrase in ("show recent memos", "list memos", "show mailroom", "memo inbox"):
            with self.subTest(phrase=phrase):
                routed = self.pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "tool")
                self.assertEqual(routed["capability"], "memo.list")
                self.assertEqual(routed["tool"], "office.memos_list")
                self.assertEqual(routed["arguments"]["limit"], 25)

    def test_memo_get_requests_route_to_memo_get(self) -> None:
        for phrase in ("read memo memo_123", "open memo abc123", "show memo 2f6e9a"):
            with self.subTest(phrase=phrase):
                routed = self.pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "tool")
                self.assertEqual(routed["capability"], "memo.get")
                self.assertEqual(routed["tool"], "office.memo_get")
                self.assertTrue(routed["arguments"]["memo_id"])

    def test_sales_collaboration_request_routes_to_marketing_memo(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "ask marketing to turn this research into a campaign plan")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "memo.dispatch")
        self.assertEqual(routed["tool"], "mailroom.dispatch")
        self.assertEqual(routed["arguments"]["to_room"], "marketing_room")
        self.assertEqual(routed["arguments"]["explicit_persona"], "Marketing Director")
        self.assertEqual(routed["arguments"]["body"], "turn this research into a campaign plan")

    def test_cross_room_host_question_requires_memo_body_without_switching_rooms(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="hr_department", active_persona="HR Manager"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "is there a way you could ask the host in the marketing department?",
        )
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "memo.dispatch.body_required")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertEqual(routed["arguments"]["to_room"], "marketing_room")
        self.assertEqual(routed["arguments"]["active_room"], "hr_department")
        self.assertIn("does not switch rooms", routed["arguments"]["response_text"])

    def test_identity_followup_after_model_claim_uses_authoritative_room_state(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="hr_department",
                active_persona="HR Manager",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "I've switched to the Marketing Department. I am now the Marketing Director.",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "ok your title still says HR manager. who are you now?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "room.persona_role")
        self.assertEqual(routed["arguments"]["active_room"], "hr_department")
        self.assertEqual(routed["arguments"]["active_persona"], "HR Manager")
        self.assertIn("HR Manager", routed["arguments"]["response_text"])
        self.assertNotIn("Marketing Director", routed["arguments"]["response_text"])

    def test_department_status_after_model_claim_uses_authoritative_room_state(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="hr_department",
                active_persona="HR Manager",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "I am now in the Marketing Department.",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what department am I in?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.state.get")
        self.assertEqual(routed["tool"], "office.state_get")

    def test_ack_after_model_switch_claim_does_not_continue_fake_navigation(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="hr_department",
                active_persona="HR Manager",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "Okay, I will switch to the Marketing Department now.",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "ok", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "room.authority")
        self.assertEqual(routed["arguments"]["active_room"], "hr_department")
        self.assertEqual(routed["arguments"]["active_persona"], "HR Manager")
        self.assertIn("still in HR Department", routed["arguments"]["response_text"])

    def test_model_route_forbids_unbacked_room_or_persona_switch_claims(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="hr_department", active_persona="HR Manager"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "can you help me think through the policy?")
        self.assertEqual(routed["route_kind"], "model")
        system_prompt = routed["arguments"]["system_prompt"]
        self.assertIn("Never claim you switched rooms", system_prompt)
        self.assertIn("Only a navigation route", system_prompt)

    def test_marketing_collaboration_request_routes_to_art_department_memo(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="marketing_room", active_persona="Marketing Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "loop in art department for launch visuals")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "memo.dispatch")
        self.assertEqual(routed["tool"], "mailroom.dispatch")
        self.assertEqual(routed["arguments"]["to_room"], "art_department")
        self.assertEqual(routed["arguments"]["explicit_persona"], "Creative Director")
        self.assertEqual(routed["arguments"]["body"], "launch visuals")

    def test_expanded_department_collaboration_phrases_route_to_memos(self) -> None:
        cases = (
            (
                self.sales_pipeline,
                "have marketing review this",
                "marketing_room",
                "Marketing Director",
                "review this",
            ),
            (
                RequestPipeline(
                    kernel=DummyKernel(active_room="marketing_room", active_persona="Marketing Director"),
                    navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
                    utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                    tool_names=[],
                    app_version="1.3.0",
                ),
                "get art department to make visuals",
                "art_department",
                "Creative Director",
                "make visuals",
            ),
            (
                self.sales_pipeline,
                "send this to finance for pricing",
                "finance_department",
                "Finance Director",
                "pricing",
            ),
            (
                self.sales_pipeline,
                "coordinate with law office on this",
                "law_office",
                "Legal Counsel",
                "this",
            ),
        )
        for pipeline, phrase, room_id, persona, body in cases:
            with self.subTest(phrase=phrase):
                routed = pipeline.route_user_request("default", phrase)
                self.assertEqual(routed["route_kind"], "tool")
                self.assertEqual(routed["capability"], "memo.dispatch")
                self.assertEqual(routed["tool"], "mailroom.dispatch")
                self.assertEqual(routed["arguments"]["to_room"], room_id)
                self.assertEqual(routed["arguments"]["explicit_persona"], persona)
                self.assertEqual(routed["arguments"]["body"], body)

    def test_sales_research_demographics_request_routes_to_search_web(self) -> None:
        routed = self.sales_pipeline.route_user_request(
            "default",
            "research demographics for family restaurants in Seattle",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")
        self.assertEqual(routed["arguments"]["query"], "demographics for family restaurants in Seattle")

    def test_marketing_research_trends_request_routes_to_search_web(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="marketing_room", active_persona="Marketing Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "find social media trends for coffee shops",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")
        self.assertEqual(routed["arguments"]["query"], "social media trends for coffee shops")

    def test_conference_room_schedule_meeting_routes_to_calendar_create(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "schedule meeting quarterly planning on 2026-07-03 from 2pm to 3pm with sam@example.com, lee@example.com",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.calendar.create")
        self.assertEqual(routed["tool"], "office.calendar_create")
        event = routed["arguments"]["event"]
        self.assertEqual(event["summary"], "quarterly planning")
        self.assertEqual(event["start"]["dateTime"], "2026-07-03T14:00:00")
        self.assertEqual(event["end"]["dateTime"], "2026-07-03T15:00:00")
        self.assertEqual(event["start"]["timeZone"], "America/Los_Angeles")
        self.assertEqual(
            event["attendees"],
            [{"email": "sam@example.com"}, {"email": "lee@example.com"}],
        )

    def test_conference_room_start_meeting_routes_to_internal_meeting_state(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "start meeting vendor kickoff", session_id="session_a")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "meeting_state.start")
        self.assertEqual(routed["tool"], "office.meeting_state_start")
        self.assertEqual(routed["arguments"]["title"], "vendor kickoff")
        self.assertEqual(routed["arguments"]["workspace_id"], "default")
        self.assertEqual(routed["arguments"]["session_id"], "session_a")

    def test_conference_room_meeting_state_item_requests_route_to_internal_tools(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        cases = [
            ("add agenda item review launch budget", "meeting_state.agenda.add", "office.meeting_state_add_agenda", "review launch budget"),
            ("record decision use option b", "meeting_state.decision.record", "office.meeting_state_record_decision", "use option b"),
            ("add action item Sam will send notes", "meeting_state.action_item.add", "office.meeting_state_add_action_item", "Sam will send notes"),
            ("add parking lot item pricing follow-up", "meeting_state.parking_lot.add", "office.meeting_state_add_parking_lot", "pricing follow-up"),
        ]
        for request_text, capability, tool, item in cases:
            with self.subTest(request_text=request_text):
                routed = pipeline.route_user_request("default", request_text, session_id="session_a")
                self.assertEqual(routed["route_kind"], "tool")
                self.assertEqual(routed["capability"], capability)
                self.assertEqual(routed["tool"], tool)
                self.assertEqual(routed["arguments"]["item"], item)
                self.assertEqual(routed["arguments"]["workspace_id"], "default")
                self.assertEqual(routed["arguments"]["session_id"], "session_a")

    def test_conference_room_show_meeting_state_routes_to_internal_tool(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "show meeting state", session_id="session_a")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "meeting_state.show")
        self.assertEqual(routed["tool"], "office.meeting_state_show")
        self.assertEqual(routed["arguments"]["workspace_id"], "default")
        self.assertEqual(routed["arguments"]["session_id"], "session_a")

    def test_conference_room_meeting_state_routes_do_not_override_calendar_scheduling(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "schedule meeting quarterly planning on 2026-07-03 from 2pm to 3pm with sam@example.com",
            session_id="session_a",
        )
        self.assertEqual(routed["capability"], "integration.calendar.create")
        self.assertEqual(routed["tool"], "office.calendar_create")

    def test_conference_room_schedule_meeting_without_details_clarifies(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "schedule a meeting with marketing")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "conference_room.meeting.details_required")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("schedule meeting quarterly planning", routed["arguments"]["response_text"])

    def test_conference_room_reschedule_meeting_routes_to_calendar_update(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "reschedule meeting evt_12345 to 2026-07-03 from 3pm to 4pm called quarterly planning with sam@example.com",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.calendar.update")
        self.assertEqual(routed["tool"], "office.calendar_update")
        self.assertEqual(routed["arguments"]["event_id"], "evt_12345")
        event = routed["arguments"]["event"]
        self.assertEqual(event["summary"], "quarterly planning")
        self.assertEqual(event["start"]["dateTime"], "2026-07-03T15:00:00")
        self.assertEqual(event["end"]["dateTime"], "2026-07-03T16:00:00")
        self.assertEqual(event["attendees"], [{"email": "sam@example.com"}])

    def test_conference_room_cancel_meeting_routes_to_calendar_cancel(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "cancel meeting evt_12345")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.calendar.cancel")
        self.assertEqual(routed["tool"], "office.calendar_cancel")
        self.assertEqual(routed["arguments"]["event_id"], "evt_12345")

    def test_conference_room_create_agenda_routes_to_artifact_create(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "create agenda quarterly planning for vendor kickoff",
        )
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.create")
        self.assertEqual(routed["tool"], "office.artifact_create")
        self.assertEqual(routed["arguments"]["artifact_type"], "agenda")
        self.assertEqual(routed["arguments"]["title"], "quarterly planning")
        self.assertIn("vendor kickoff", routed["arguments"]["content"])
        self.assertEqual(routed["arguments"]["metadata"]["source"], "conference_room_agenda")

    def test_conference_room_create_agenda_without_title_clarifies(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="conference_room", active_persona="Facilitator"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "create agenda")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "conference_room.agenda.title_required")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("create agenda quarterly planning", routed["arguments"]["response_text"])

    def test_break_room_can_dispatch_question_memo(self) -> None:
        self.pipeline.assert_mailroom_allowed("break_room", "control_room")

    def test_memo_response_uses_real_newlines(self) -> None:
        header = self.pipeline.mailroom_header("Navigator", "Control Room", "System Health")
        self.assertIn("\nSubject: System Health\n", header)
        self.assertNotIn("\\n", header)

        text = self.pipeline.memo_get_text(
            {
                "memo_id": "memo_1",
                "from_room": "break_room",
                "to_room": "control_room",
                "to_persona": "Navigator",
                "subject": "System Health",
            },
            "How is system health?",
        )
        self.assertIn("\nFrom: break_room\n", text)
        self.assertNotIn("\\n", text)

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

    def test_my_office_email_capability_uses_nancy_guidance(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "can you send emails for me?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.capability.info")
        text = routed["arguments"]["response_text"]
        self.assertIn("Nancy can draft email", text)
        self.assertIn("Gmail", text)
        self.assertIn("Profile", text)
        self.assertIn("Calendar", text)

    def test_my_office_overview_uses_nancy_guidance(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what can you do for me?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.capability.info")
        self.assertIn("Nancy can draft email", routed["arguments"]["response_text"])
        self.assertIn("memo system", routed["arguments"]["response_text"])

    def test_nancy_prefixed_capability_uses_nancy_guidance_from_other_room(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "Nancy, what can you do for me?")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.capability.info")
        self.assertIn("Nancy can draft email", routed["arguments"]["response_text"])

    def test_nancy_prefixed_calendar_create_routes_to_calendar_tool(self) -> None:
        routed = self.sales_pipeline.route_user_request(
            "default",
            "Nancy, schedule meeting quarterly planning on 2026-07-03 from 2pm to 3pm with sam@example.com",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.calendar.create")
        self.assertEqual(routed["tool"], "office.calendar_create")
        self.assertEqual(routed["arguments"]["event"]["summary"], "quarterly planning")
        self.assertEqual(routed["arguments"]["event"]["attendees"], [{"email": "sam@example.com"}])

    def test_nancy_email_review_confirmation_routes_to_gmail_send_not_model(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": (
                            "Nancy: I've prepared the email to time2makecents@gmail.com with the subject line "
                            "\"testing\" and the body \"This is a test email.\" Here's the email for your review:\n\n"
                            "Subject: testing\nBody: This is a test email.\n\nIs this correct?"
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.send")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "testing")
        self.assertEqual(routed["arguments"]["body"], "This is a test email.")

    def test_nancy_recipient_only_email_request_asks_for_subject(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send an email to time2makecents@gmail.com.", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.subject_required")
        self.assertEqual(routed["arguments"]["to"], "time2makecents@gmail.com")
        self.assertIn("what subject should i use", routed["arguments"]["response_text"].lower())

    def test_nancy_contact_card_email_request_asks_for_subject(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "Nancy, email time2makecents@gmail.com", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.subject_required")
        self.assertEqual(routed["arguments"]["to"], "time2makecents@gmail.com")
        self.assertEqual(routed["arguments"]["nancy_email_compose"]["stage"], "subject")
        self.assertEqual(routed["arguments"]["nancy_email_compose"]["source"], "direct")

    def test_nancy_message_to_recipient_asks_for_subject_without_reusing_stale_body(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "Subject: old subject\nBody: stale body",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send message to youlookifind@gmail.com", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.subject_required")
        self.assertEqual(routed["arguments"]["to"], "youlookifind@gmail.com")
        self.assertNotEqual(routed["tool"], "office.gmail_send")

    def test_nancy_subject_followup_asks_for_body(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "send an email to time2makecents@gmail.com."},
                    {"role": "assistant", "text": "What subject should I use for the email to time2makecents@gmail.com?"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "subject this is a test", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.body_required")
        self.assertEqual(routed["arguments"]["to"], "time2makecents@gmail.com")
        self.assertEqual(routed["arguments"]["subject"], "this is a test")
        self.assertIn("body", routed["arguments"]["response_text"].lower())

    def test_nancy_body_followup_prepares_send_confirmation(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "send an email to time2makecents@gmail.com."},
                    {"role": "assistant", "text": "What subject should I use for the email to time2makecents@gmail.com?"},
                    {"role": "user", "text": "subject this is a test"},
                    {"role": "assistant", "text": "What should the body say?\nTo: time2makecents@gmail.com\nSubject: this is a test"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "body hello from nancy", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.send")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "this is a test")
        self.assertEqual(routed["arguments"]["body"], "hello from nancy")
        self.assertEqual(routed["arguments"]["assistant_persona"], "Nancy")

    def test_nancy_pending_subject_state_asks_for_body(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                state={
                    "pending_nancy_email_by_session": {
                        "sess_1": {
                            "mode": "compose",
                            "stage": "subject",
                            "to": "time2makecents@gmail.com",
                            "subject": "",
                            "body": "",
                            "source": "contact",
                        }
                    }
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "project update", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.body_required")
        self.assertEqual(routed["arguments"]["to"], "time2makecents@gmail.com")
        self.assertEqual(routed["arguments"]["subject"], "project update")
        self.assertEqual(routed["arguments"]["nancy_email_compose"]["stage"], "body")

    def test_nancy_pending_body_state_prepares_gmail_send(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                state={
                    "pending_nancy_email_by_session": {
                        "sess_1": {
                            "mode": "compose",
                            "stage": "body",
                            "to": "time2makecents@gmail.com",
                            "subject": "project update",
                            "body": "",
                            "source": "contact",
                        }
                    }
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "body hello from nancy", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.send")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "project update")
        self.assertEqual(routed["arguments"]["body"], "hello from nancy")

    def test_nancy_pending_email_cancel_clears_compose_state(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                state={
                    "pending_nancy_email_by_session": {
                        "sess_1": {
                            "mode": "compose",
                            "stage": "body",
                            "to": "time2makecents@gmail.com",
                            "subject": "project update",
                            "body": "",
                            "source": "contact",
                        }
                    }
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "cancel", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.cancelled")
        self.assertTrue(routed["arguments"]["clear_pending_nancy_email"])

    def test_nancy_complete_email_request_still_routes_to_gmail_send(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "send an email to time2makecents@gmail.com subject: testing body: hello from nancy",
            session_id="sess_1",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "testing")
        self.assertEqual(routed["arguments"]["body"], "hello from nancy")

    def test_nancy_send_same_message_to_new_recipient_routes_to_gmail_send(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "I've sent the email to timetomakecents@gmail.com with the subject line \"testing\" and the body \"This is a test email.\"",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send the same message but to time2makecents@gmail.com", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "testing")
        self.assertEqual(routed["arguments"]["body"], "This is a test email.")

    def test_nancy_verify_sent_email_routes_to_gmail_sent_search_not_model(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "I've sent the email to timetomakecents@gmail.com with the subject line \"testing\" and the body \"This is a test email.\"",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "verify email was sent", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertIn("in:sent", routed["arguments"]["query"])
        self.assertIn("timetomakecents@gmail.com", routed["arguments"]["query"])
        self.assertIn("testing", routed["arguments"]["query"])

    def test_nancy_google_connected_disagreement_stays_deterministic(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": "Nancy: Google is configured but not connected. Connect Google from Profile before I can send Gmail.",
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "profile says its connected", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.google_connection_status")
        self.assertIn("backend integration state", routed["arguments"]["response_text"])

    def test_nancy_check_my_inbox_routes_to_gmail_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "check my inbox", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "in:inbox")

    def test_nancy_who_are_they_from_after_inbox_search_repeats_gmail_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "check my inbox"},
                    {"role": "assistant", "text": "Found 3 Gmail message(s).\n1. From: Alex <alex@example.com> | Subject: Update"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "who are they from", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "in:inbox")

    def test_nancy_inbox_followup_outranks_unfinished_compose_prompt(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "send an email to time2makecents@gmail.com."},
                    {"role": "assistant", "text": "What subject should I use for the email to time2makecents@gmail.com?"},
                    {"role": "user", "text": "check my inbox"},
                    {"role": "assistant", "text": "Found 3 Gmail message(s).\n1. From: Alex <alex@example.com> | Subject: Update"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "who are they from", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "in:inbox")

    def test_nancy_read_number_after_inbox_outranks_unfinished_compose_prompt(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "send an email to time2makecents@gmail.com."},
                    {"role": "assistant", "text": "What subject should I use for the email to time2makecents@gmail.com?"},
                    {"role": "user", "text": "who are they from"},
                    {"role": "assistant", "text": "What should the body say?\nTo: time2makecents@gmail.com\nSubject: who are they from"},
                    {"role": "user", "text": "Do I have unread emails?"},
                    {"role": "assistant", "text": "Found 2 Gmail message(s).\n1. From: James Willis <time2makecents@gmail.com> | Subject: Re: this is a test"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "read 1", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.read")
        self.assertEqual(routed["tool"], "office.gmail_read")
        self.assertEqual(routed["arguments"]["message_index"], 1)

    def test_nancy_show_message_from_sender_outranks_unfinished_compose_prompt(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "send an email to time2makecents@gmail.com."},
                    {"role": "assistant", "text": "What should the body say?\nTo: time2makecents@gmail.com\nSubject: who are they from"},
                    {"role": "user", "text": "Do I have unread emails?"},
                    {"role": "assistant", "text": "Found 2 Gmail message(s).\n1. From: James Willis <time2makecents@gmail.com> | Subject: Re: this is a test"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "SHOW.\nMe the message from time2makecents", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "from:time2makecents")

    def test_nancy_reply_question_searches_gmail_instead_of_session_memory(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "did i get a reply back from time2makecents?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertIn("time2makecents", routed["arguments"]["query"])

    def test_nancy_reply_after_loaded_gmail_thread_asks_for_reply_body(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "read 1"},
                    {
                        "role": "assistant",
                        "text": (
                            "Loaded Gmail thread with 2 message(s).\n\n"
                            "1. From: James Willis <time2makecents@gmail.com>\n"
                            "   To: James Willis <veridexcorp@gmail.com>\n"
                            "   Subject: Re: this is a test\n\n"
                            "This is a test email.\n\n"
                            "Would you like to reply?"
                        ),
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "reply", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.reply_body_required")
        self.assertEqual(routed["arguments"]["response_text"], "What would you like to say?")
        self.assertNotIn("Loaded Gmail thread", routed["arguments"]["response_text"])

    def test_nancy_reply_body_after_loaded_gmail_thread_routes_to_send_confirmation(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "read 1"},
                    {
                        "role": "assistant",
                        "text": (
                            "Loaded Gmail thread with 2 message(s).\n\n"
                            "1. From: James Willis <time2makecents@gmail.com>\n"
                            "   To: James Willis <veridexcorp@gmail.com>\n"
                            "   Subject: Re: this is a test\n\n"
                            "This is a test email.\n\n"
                            "Would you like to reply?"
                        ),
                    },
                    {"role": "user", "text": "reply"},
                    {"role": "assistant", "text": "What would you like to say?"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "i appreciate your prompt response.\n\nkind regards,\nJR",
            session_id="sess_1",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.send")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "Re: this is a test")
        self.assertEqual(routed["arguments"]["body"], "i appreciate your prompt response.\n\nkind regards,\nJR")
        self.assertEqual(routed["arguments"]["assistant_persona"], "Nancy")

    def test_nancy_prefixed_reply_body_keeps_newlines_and_routes_to_send_confirmation(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                transcript_rows=[
                    {
                        "role": "assistant",
                        "text": (
                            "Loaded Gmail message.\n"
                            "From: James Willis <time2makecents@gmail.com>\n"
                            "To: James Willis <veridexcorp@gmail.com>\n"
                            "Subject: this is a test\n\n"
                            "Would you like to reply?"
                        ),
                    },
                    {"role": "user", "text": "Nancy, reply"},
                    {"role": "assistant", "text": "What would you like to say?"},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request(
            "default",
            "Nancy, i appreciate your prompt response.\n\nkind regards,\nJR",
            session_id="sess_1",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["tool"], "office.gmail_send")
        self.assertEqual(routed["arguments"]["to"], ["time2makecents@gmail.com"])
        self.assertEqual(routed["arguments"]["subject"], "Re: this is a test")
        self.assertEqual(routed["arguments"]["body"], "i appreciate your prompt response.\n\nkind regards,\nJR")

    def test_nancy_new_messages_routes_to_unread_gmail_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "do i have any new messages?", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "in:inbox is:unread")

    def test_nancy_read_new_messages_routes_to_unread_gmail_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "read new messages", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "in:inbox is:unread")

    def test_nancy_read_and_timeframe_message_requests_build_gmail_queries(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        read_week = pipeline.route_user_request("default", "list read messages in the last week", session_id="sess_1")
        all_day = pipeline.route_user_request("default", "list all messages in the last day", session_id="sess_1")

        self.assertEqual(read_week["tool"], "office.gmail_search")
        self.assertEqual(read_week["arguments"]["query"], "in:inbox is:read newer_than:7d")
        self.assertEqual(all_day["tool"], "office.gmail_search")
        self.assertEqual(all_day["arguments"]["query"], "in:inbox newer_than:1d")

    def test_nancy_help_me_compose_email_starts_guided_compose(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "help me compose an email", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "nancy.email.recipient_required")
        self.assertIn("Who should I send it to", routed["arguments"]["response_text"])

    def test_nancy_named_recipient_routes_to_contact_resolution(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="my_office", active_persona="Nancy"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "send email to James", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "contact.email.resolve")
        self.assertEqual(routed["tool"], "office.contact_resolve_email")
        self.assertEqual(routed["arguments"]["name"], "James")

    def test_nancy_check_again_after_email_check_repeats_gmail_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="my_office",
                active_persona="Nancy",
                transcript_rows=[
                    {"role": "user", "text": "can you check my email?"},
                    {"role": "assistant", "text": "Found 2 Gmail message(s)."},
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "check again", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "integration.gmail.search")
        self.assertEqual(routed["tool"], "office.gmail_search")
        self.assertEqual(routed["arguments"]["query"], "in:inbox")

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

    def test_contextual_search_the_internet_uses_recent_entity_before_capability_info(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                transcript_rows=[
                    {"role": "user", "text": "tell me about blairally"},
                    {
                        "role": "assistant",
                        "text": "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "search the internet", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")
        self.assertEqual(routed["arguments"]["query"], "blairally")

    def test_contextual_yes_after_search_offer_routes_to_web_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                active_room="sales_department",
                active_persona="Sales Director",
                transcript_rows=[
                    {"role": "user", "text": "tell me about blairally"},
                    {
                        "role": "assistant",
                        "text": "I can search the web for more information about blairally if you'd like.",
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "yes", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "search.web")
        self.assertEqual(routed["tool"], "office.search_web")
        self.assertEqual(routed["arguments"]["query"], "blairally")

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

    def test_ocr_request_routes_to_document_ocr_by_filename_with_spaces(self) -> None:
        routed = self.pipeline.route_user_request("default", "extract text from chicken blues lyrics.pdf")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "document.ocr")
        self.assertEqual(routed["tool"], "office.ocr_extract")
        self.assertEqual(routed["arguments"]["file_name"], "chicken blues lyrics.pdf")

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

    def test_conversation_first_keeps_normal_chat_in_model_route(self) -> None:
        routed = self.pipeline.route_user_request("default", "help me think through a menu idea")
        self.assertEqual(routed["route_kind"], "model")
        self.assertEqual(routed["capability"], "ai.respond")
        self.assertEqual(routed["reason"], "Conversation-first intent matched before broad tool routing.")

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

    def test_memory_objects_question_routes_to_workspace_artifact_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        for text in ("what memory objects do you have saved?", "what memory objects do i have saved?"):
            routed = pipeline.route_user_request("default", text)
            self.assertEqual(routed["route_kind"], "artifact")
            self.assertEqual(routed["capability"], "artifact.list")
            self.assertEqual(routed["tool"], "office.artifact_list")
            self.assertEqual(routed["arguments"]["retrieval_scope"], "workspace")

    def test_workspace_objects_question_routes_to_workspace_artifact_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "what objects are saved in the workspace")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.list")
        self.assertEqual(routed["tool"], "office.artifact_list")
        self.assertEqual(routed["arguments"]["retrieval_scope"], "workspace")

    def test_room_objects_question_routes_to_room_memory_list(self) -> None:
        routed = self.pipeline.route_user_request("default", "what objects are saved in this room")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.list")
        self.assertEqual(routed["tool"], "office.room_memory_list")
        self.assertEqual(routed["arguments"]["room_id"], "lobby")

    def test_behavior_objects_question_routes_to_room_memory_list(self) -> None:
        routed = self.sales_pipeline.route_user_request("default", "what behavior objects are saved?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "room.memory.list")
        self.assertEqual(routed["tool"], "office.room_memory_list")
        self.assertEqual(routed["arguments"]["room_id"], "sales_department")

    def test_bare_objects_saved_asks_for_scope(self) -> None:
        routed = self.pipeline.route_user_request("default", "what are the objects saved")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "clarification.object_scope")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("workspace objects, session objects, or behavior memories", routed["arguments"]["response_text"])

    def test_session_objects_question_routes_to_session_objects_list(self) -> None:
        routed = self.pipeline.route_user_request(
            "default",
            "what objects are saved in the session",
            session_id="sess_123",
        )
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.objects.list")
        self.assertEqual(routed["tool"], "office.session_objects_list")
        self.assertEqual(routed["arguments"]["session_id"], "sess_123")

    def test_session_objects_question_variants_route_to_session_objects_list(self) -> None:
        for text in (
            "what are the objects saved in this session",
            "what are the session objects saved",
            "show session objects",
            "list session objects",
        ):
            routed = self.pipeline.route_user_request("default", text, session_id="sess_123")
            self.assertEqual(routed["route_kind"], "tool")
            self.assertEqual(routed["capability"], "session.objects.list")
            self.assertEqual(routed["tool"], "office.session_objects_list")

    def test_behavior_memories_saved_now_routes_to_room_memory_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="sales_department", active_persona="Sales Director"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what behavior memories are saved now?")
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
        self.assertEqual(
            routed["arguments"]["response_text"],
            "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
        )

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
        self.assertEqual(
            routed["arguments"]["response_text"],
            "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
        )

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

    def test_marketing_navigation_still_switches_rooms(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to marketing department")
        self.assertEqual(routed["route_kind"], "navigation")
        self.assertEqual(routed["capability"], "room.navigate")
        self.assertEqual(routed["room_id"], "marketing_room")
        self.assertEqual(routed["tool"], "office.room_set")

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

    def test_create_workspace_routes_to_real_workspace_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "create workspace werkin test list")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.create")
        self.assertEqual(routed["tool"], "office.workspace_new")
        self.assertEqual(routed["arguments"]["label"], "werkin test list")

    def test_create_new_workspace_routes_to_real_workspace_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "create new workspace werkin test list")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.create")
        self.assertEqual(routed["tool"], "office.workspace_new")
        self.assertEqual(routed["arguments"]["label"], "werkin test list")

    def test_create_workspace_list_ambiguous_phrase_requires_clarification(self) -> None:
        routed = self.pipeline.route_user_request("default", "create workspace/list werkin test list")
        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "workspace_or_list.create.confirmation")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("workspace or a saved list artifact", routed["arguments"]["response_text"])

    def test_create_list_routes_to_artifact_create(self) -> None:
        routed = self.pipeline.route_user_request("default", "create list weekly targets")
        self.assertEqual(routed["route_kind"], "artifact")
        self.assertEqual(routed["capability"], "artifact.create")
        self.assertEqual(routed["tool"], "office.artifact_create")
        self.assertEqual(routed["arguments"]["artifact_type"], "list")
        self.assertEqual(routed["arguments"]["title"], "weekly targets")

    def test_session_name_question_routes_to_session_info(self) -> None:
        routed = self.pipeline.route_user_request("default", "what is the name of this session?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.info")
        self.assertEqual(routed["tool"], "office.session_info")

    def test_rename_session_routes_to_session_rename(self) -> None:
        routed = self.pipeline.route_user_request("default", "rename this session newest test")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.rename")
        self.assertEqual(routed["tool"], "office.session_rename")
        self.assertEqual(routed["arguments"]["title"], "newest test")

    def test_list_sessions_routes_to_sessions_tool(self) -> None:
        routed = self.pipeline.route_user_request("default", "list sessions")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.list")
        self.assertEqual(routed["tool"], "office.sessions_list")

    def test_records_archive_chat_threads_question_routes_to_session_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="records_archive", active_persona="Archivist"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "can you show me any of my chat threads?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.list")
        self.assertEqual(routed["tool"], "office.sessions_list")

    def test_records_archive_named_thread_question_routes_to_session_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="records_archive", active_persona="Archivist"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "can you show me my thread with Navigator?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "Navigator")
        self.assertTrue(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_records_archive_named_thread_with_room_routes_to_session_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="records_archive", active_persona="Archivist"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "can you show me my thread with Nancy in my office?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "Nancy in my office")
        self.assertTrue(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_records_archive_saved_files_question_routes_to_file_list(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(active_room="records_archive", active_persona="Archivist"),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "what saved files do I have?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "file.list")
        self.assertEqual(routed["tool"], "office.file_list")
        self.assertEqual(routed["arguments"], {})

    def test_go_to_session_number_routes_to_session_activate(self) -> None:
        routed = self.pipeline.route_user_request("default", "go to session 3")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.activate")
        self.assertEqual(routed["tool"], "office.session_activate")
        self.assertEqual(routed["arguments"]["session_ref"], "3")

    def test_search_other_sessions_routes_to_sessions_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "search other sessions for blairally")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertFalse(routed["arguments"]["include_current"])

    def test_search_all_sessions_routes_to_sessions_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "search all sessions for blairally information")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertTrue(routed["arguments"]["include_current"])

    def test_direct_session_search_detail_request_routes_to_detailed_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "display the information the sessions gave about blairally")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertFalse(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_workspace_reference_search_routes_to_detailed_session_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you search the current workspace for references to blairally?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertTrue(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_explicit_session_search_wins_over_grounded_followup(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "search for blairally and give me information"},
                    {"role": "assistant", "text": "Search results describe blairally as a music venue/arcade."},
                ],
                grounded_search_by_session={
                    "sess_1": {
                        "entity_subject": "blairally",
                        "results": [
                            {
                                "title": "Blairally",
                                "snippet": "Blairally is a music venue/arcade in Eugene, Oregon.",
                                "url": "https://example.com/blairally",
                                "source": "Example",
                            }
                        ],
                    }
                },
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "search all sessions for blairally information", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")

    def test_session_search_detail_followup_routes_to_detailed_session_search(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "search other sessions"},
                    {
                        "role": "assistant",
                        "text": (
                            "I found 3 matching session(s) for \"blairally\":\n"
                            "1. Nav test (sess_99a66e8dfc21) - Navigator: Veridex doesn't have any verified information about blairally.\n"
                            "2. Session_A (sess_66c6c2f0dfd3) - Sales Director: Blairally is a music venue and arcade."
                        ),
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "can you list the information it gave in those sessions", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertFalse(routed["arguments"]["include_current"])
        self.assertTrue(routed["arguments"]["detail"])

    def test_show_me_the_rest_of_numbered_session_result_routes_to_full_answer(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {"role": "user", "text": "search other sessions"},
                    {
                        "role": "assistant",
                        "text": (
                            "I found 3 matching session(s) for \"blairally\":\n"
                            "1. Nav test (sess_99a66e8dfc21) - Navigator: Veridex doesn't have any verified information about blairally.\n"
                            "2. Session_A (sess_66c6c2f0dfd3) - Sales Director: Blairally is a music venue and arcade...\n"
                            "3. Session_B (sess_0772e3abaec1) - Sales Director: Blairally has live music."
                        ),
                    },
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        routed = pipeline.route_user_request("default", "show me the rest of 2", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "session.search")
        self.assertEqual(routed["tool"], "office.sessions_search")
        self.assertEqual(routed["arguments"]["query"], "blairally")
        self.assertEqual(routed["arguments"]["target_session_id"], "sess_66c6c2f0dfd3")
        self.assertTrue(routed["arguments"]["detail"])
        self.assertTrue(routed["arguments"]["expand_full"])

    def test_show_this_session_thread_routes_to_transcript(self) -> None:
        routed = self.pipeline.route_user_request("default", "can you show this sessions thread?")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.transcript.get")
        self.assertEqual(routed["tool"], "office.transcript_get")

    def test_art_department_chat_log_routes_to_room_filtered_transcript(self) -> None:
        routed = self.pipeline.route_user_request("default", "pull up my latest chat log from the art department", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["capability"], "workspace.transcript.get")
        self.assertEqual(routed["tool"], "office.transcript_get")
        self.assertEqual(routed["arguments"]["room_id"], "art_department")
        self.assertEqual(routed["arguments"]["session_id"], "sess_1")
        self.assertFalse(routed["arguments"]["include_system"])

    def test_display_art_department_chat_log_routes_to_transcript_not_session_search(self) -> None:
        routed = self.pipeline.route_user_request("default", "display chat log from art department", session_id="sess_1")
        self.assertEqual(routed["route_kind"], "tool")
        self.assertEqual(routed["tool"], "office.transcript_get")
        self.assertEqual(routed["arguments"]["room_id"], "art_department")

    def test_room_log_provenance_followup_confirms_requested_room(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Archivist",
                        "session_id": "sess_1",
                        "text": (
                            "Transcript entries for art_department in this session:\n"
                            "[2026-07-07T13:09:07Z] art_department | You: what is visual marketing?\n"
                            "[2026-07-07T13:09:16Z] art_department | Creative Director: Storytelling matters."
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "was that the chat log for art department?", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "workspace.transcript.provenance")
        self.assertEqual(routed["tool"], "office.capability_info")
        self.assertIn("Yes.", routed["arguments"]["response_text"])
        self.assertIn("Art Department (art_department)", routed["arguments"]["response_text"])
        self.assertIn("session sess_1", routed["arguments"]["response_text"])
        self.assertIn("2 entries", routed["arguments"]["response_text"])

    def test_room_log_provenance_followup_rejects_wrong_room(self) -> None:
        pipeline = RequestPipeline(
            kernel=DummyKernel(
                transcript_rows=[
                    {
                        "role": "assistant",
                        "speaker": "Archivist",
                        "session_id": "sess_1",
                        "text": (
                            "Transcript entries for art_department in this session:\n"
                            "[2026-07-07T13:09:07Z] art_department | You: what is visual marketing?"
                        ),
                    }
                ],
            ),
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )

        routed = pipeline.route_user_request("default", "isn't that from the control room chat?", session_id="sess_1")

        self.assertEqual(routed["route_kind"], "clarify")
        self.assertEqual(routed["capability"], "workspace.transcript.provenance")
        self.assertIn("No.", routed["arguments"]["response_text"])
        self.assertIn("Art Department (art_department)", routed["arguments"]["response_text"])
        self.assertIn("not filtered to Control Room (control_room)", routed["arguments"]["response_text"])


if __name__ == "__main__":
    unittest.main()
