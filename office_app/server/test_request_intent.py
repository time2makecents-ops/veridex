from __future__ import annotations

import unittest

from office_app.server.request_intent import RequestIntentAnalyzer, RequestIntentConfig
from office_app.server.request_pipeline import RequestPipeline


class RequestIntentAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = RequestPipeline(
            kernel=None,
            navigator_control={"id": "NAVIGATOR", "status": "ACTIVE", "visibility": "INVISIBLE"},
            utc_now_fn=lambda: "2026-05-09T12:00:00Z",
            tool_names=[],
            app_version="1.3.0",
        )
        self.analyzer = RequestIntentAnalyzer(
            RequestIntentConfig(
                artifact_create_triggers=RequestPipeline.ARTIFACT_CREATE_TRIGGERS,
                artifact_list_triggers=RequestPipeline.ARTIFACT_LIST_TRIGGERS,
                artifact_open_triggers=RequestPipeline.ARTIFACT_OPEN_TRIGGERS,
                factual_entity_lookup_patterns=RequestPipeline.FACTUAL_ENTITY_LOOKUP_PATTERNS,
                factual_entity_search_patterns=RequestPipeline.FACTUAL_ENTITY_SEARCH_PATTERNS,
                file_id_re=RequestPipeline.FILE_ID_RE,
                file_name_re=RequestPipeline.FILE_NAME_RE,
                intent_advice_hints=RequestPipeline.INTENT_ADVICE_HINTS,
                intent_meta_hints=RequestPipeline.INTENT_META_HINTS,
                ocr_explicit_hints=RequestPipeline.OCR_EXPLICIT_HINTS,
                room_status_hints=RequestPipeline.ROOM_STATUS_HINTS,
                search_business_advice_hints=RequestPipeline.SEARCH_BUSINESS_ADVICE_HINTS,
                search_place_hints=RequestPipeline.SEARCH_PLACE_HINTS,
                search_review_hints=RequestPipeline.SEARCH_REVIEW_HINTS,
                search_web_hints=RequestPipeline.SEARCH_WEB_HINTS,
                session_create_hints=RequestPipeline.SESSION_CREATE_HINTS,
            ),
            normalize_place_query=self.pipeline.normalize_place_query,
            is_explicit_room_navigation=self.pipeline.is_explicit_room_navigation,
        )

    def test_classifies_meta_intent(self) -> None:
        self.assertEqual(self.analyzer.classify_intent("why did you respond that way"), "meta")

    def test_classifies_reflective_question_as_meta_intent(self) -> None:
        self.assertEqual(self.analyzer.classify_intent("what was wrong with the question"), "meta")

    def test_classifies_advice_intent(self) -> None:
        self.assertEqual(self.analyzer.classify_intent("what are the best restaurants to model mine after"), "advice")

    def test_classifies_place_lookup_as_task(self) -> None:
        self.assertEqual(self.analyzer.classify_intent("find restaurants in Portland"), "task")

    def test_extracts_entity_lookup_request(self) -> None:
        request = self.analyzer.extract_factual_entity_request("what can you tell me about blairally")
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request["entity_subject"], "blairally")
        self.assertFalse(request["search_requested"])

    def test_ignores_business_advice_as_entity_lookup(self) -> None:
        request = self.analyzer.extract_factual_entity_request("what can you tell me about restaurant marketing")
        self.assertIsNone(request)

    def test_detects_place_search_signals_without_confusing_advice(self) -> None:
        advice_signals = self.analyzer.place_search_signals("what are the best restaurants to model mine after")
        self.assertTrue(advice_signals["has_place_hint"])
        self.assertFalse(advice_signals["discovery_signal"])

        task_signals = self.analyzer.place_search_signals("find thai restaurants near me")
        self.assertTrue(task_signals["has_place_hint"])
        self.assertTrue(task_signals["discovery_signal"])
        self.assertTrue(task_signals["location_signal"])
