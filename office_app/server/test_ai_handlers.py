from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from office_app.server.handlers.ai_handlers import build_ai_handlers
from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.model_router import ModelRouteResult, ModelRoutingError


class FakeKernel:
    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
        }


@dataclass
class FakeFileService:
    rows: List[Dict[str, Any]]
    content_by_id: Dict[str, bytes]

    def __post_init__(self) -> None:
        self.store = self

    def list_files(self, workspace_id: str, scope: Optional[str] = None, scope_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        filtered = [row for row in self.rows if row["workspace_id"] == workspace_id]
        if scope:
            filtered = [row for row in filtered if row.get("scope") == scope]
        if scope_ref:
            filtered = [row for row in filtered if row.get("scope_ref") == scope_ref]
        return filtered

    def file_bytes(self, workspace_id: str, file_id: str) -> Tuple[Dict[str, Any], bytes]:
        for row in self.rows:
            if row["workspace_id"] == workspace_id and row["file_id"] == file_id:
                return row, self.content_by_id[file_id]
        raise FileNotFoundError(file_id)


class FakeOcrService:
    def extract_text(self, *, file_name: str, mime_type: Optional[str], content_bytes: bytes) -> Dict[str, Any]:
        return {
            "method": "local_text",
            "mime_type": mime_type or "application/octet-stream",
            "text": content_bytes.decode("utf-8"),
            "file_name": file_name,
        }


class FakeSearchService:
    def __init__(self) -> None:
        self.place_calls: List[Dict[str, Any]] = []

    def search_places(
        self,
        *,
        query: str,
        location: Optional[str] = None,
        category: Optional[str] = None,
        needs_location: bool = False,
        limit: int = 5,
    ) -> Dict[str, Any]:
        self.place_calls.append(
            {
                "query": query,
                "location": location,
                "category": category,
                "needs_location": needs_location,
                "limit": limit,
            }
        )
        return {
            "query": query,
            "location": location,
            "category": category,
            "needs_location": needs_location,
            "limit": limit,
            "results": [],
            "summary_text": "I need your location or a city/area to search nearby restaurants.",
        }


class FakeReceptionistContextService:
    def __init__(self, *, summary: str = "", recent_turns: Optional[List[str]] = None) -> None:
        self.summary = summary
        self.recent_turns = recent_turns or []

    def build_model_context(self, *, workspace_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
            "session_id": session_id,
            "session_summary_text": self.summary,
            "recent_turns_text": list(self.recent_turns),
        }


class FakeModelRouter:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        return ModelRouteResult(
            provider="gemini",
            model="gemini-2.5-flash-lite",
            text=self.text,
            task_type=task_type,
            fallback_used=False,
            attempts=[],
        )


class SequenceModelRouter:
    def __init__(self, texts: List[str]) -> None:
        self.texts = list(texts)
        self.user_prompts: List[str] = []

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        self.user_prompts.append(user_prompt)
        text = self.texts.pop(0) if self.texts else ""
        return ModelRouteResult(
            provider="gemini",
            model="gemini-2.5-flash-lite",
            text=text,
            task_type=task_type,
            fallback_used=False,
            attempts=[],
        )


class PartialThenFailingModelRouter:
    def __init__(self) -> None:
        self.user_prompts: List[str] = []

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        self.user_prompts.append(user_prompt)
        if len(self.user_prompts) == 1:
            return ModelRouteResult(
                provider="gemini",
                model="gemini-2.5-flash-lite",
                text="1. Loyalty programs",
                task_type=task_type,
                fallback_used=False,
                attempts=[],
            )
        raise ModelRoutingError(
            "No model provider available or all providers failed.",
            attempts=["gemini: request failed: 429 quota exceeded"],
        )


class FailingModelRouter:
    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        raise ModelRoutingError(
            "No model provider available or all providers failed.",
            attempts=[
                "gemini: request failed: 429 quota exceeded",
                "groq: unavailable",
            ],
        )


class AiHandlerTests(unittest.TestCase):
    def _deps(
        self,
        workspace_rows: List[Dict[str, Any]],
        search_service: Optional[Any] = None,
        *,
        model_text: Optional[str] = None,
        receptionist_summary: str = "",
        receptionist_recent_turns: Optional[List[str]] = None,
    ) -> HandlerDeps:
        workspace_service = FakeFileService(
            rows=workspace_rows,
            content_by_id={row["file_id"]: b"Extracted contents" for row in workspace_rows},
        )
        private_service = FakeFileService(rows=[], content_by_id={})
        return HandlerDeps(
            kernel=FakeKernel(),
            store=None,
            pipeline=None,
            archive_service=None,
            memo_service=None,
            nancy_service=None,
            receptionist_context_service=FakeReceptionistContextService(
                summary=receptionist_summary,
                recent_turns=receptionist_recent_turns,
            ),
            workspace_file_service=workspace_service,
            private_file_service=private_service,
            search_service=search_service,
            ocr_service=FakeOcrService(),
            model_router=FakeModelRouter(model_text or "Default model response."),
            user_service=None,
            utc_now=lambda: "2026-04-24T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
        )

    def test_ocr_extract_resolves_room_scoped_file_by_name(self) -> None:
        deps = self._deps(
            [
                {
                    "workspace_id": "ws_1",
                    "file_id": "file_123",
                    "original_name": "JW_Cover.rtf",
                    "mime_type": "application/rtf",
                    "scope": "room",
                    "scope_ref": "sales_department",
                }
            ]
        )
        handlers = build_ai_handlers(deps)
        result = handlers["office.ocr_extract"](
            {
                "workspace_id": "ws_1",
                "file_name": "JW_Cover.rtf",
                "session_id": "sess_1",
            }
        )
        self.assertEqual(result["structuredContent"]["file_id"], "file_123")
        self.assertEqual(result["structuredContent"]["original_name"], "JW_Cover.rtf")
        self.assertEqual(result["content"][0]["text"], "Extracted contents")

    def test_search_places_passes_needs_location_to_service(self) -> None:
        search_service = FakeSearchService()
        handlers = build_ai_handlers(self._deps([], search_service=search_service))
        result = handlers["office.search_places"](
            {
                "workspace_id": "ws_1",
                "query": "restaurants",
                "category": "restaurants",
                "needs_location": True,
            }
        )
        self.assertEqual(result["content"][0]["text"], "I need your location or a city/area to search nearby restaurants.")
        self.assertEqual(search_service.place_calls[0]["query"], "restaurants")
        self.assertTrue(search_service.place_calls[0]["needs_location"])

    def test_ai_generate_adds_compliance_note_for_bar_reward_tactics(self) -> None:
        handlers = build_ai_handlers(
            self._deps(
                [],
                model_text=(
                    "A loyalty program can work well for a bar by offering discounts and rewards to frequent customers."
                ),
            )
        )
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "what are the best ways bars increase repeat customers?",
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertIn("Compliance note:", text)
        self.assertIn("Verify the applicable local rules before implementing incentives, claims, or offers.", text)

    def test_ai_generate_adds_oregon_specific_note_when_context_mentions_oregon(self) -> None:
        handlers = build_ai_handlers(
            self._deps(
                [],
                model_text=(
                    "A punch-card loyalty program with free items can motivate bar regulars to come back."
                ),
                receptionist_recent_turns=["User is operating a bar in Oregon."],
            )
        )
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "which bar loyalty tactic works best?",
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertIn("Compliance note:", text)
        self.assertIn("If this is in Oregon, verify OLCC rules before using alcohol-based incentives.", text)

    def test_ai_generate_does_not_duplicate_existing_caution(self) -> None:
        handlers = build_ai_handlers(
            self._deps(
                [],
                model_text=(
                    "A loyalty program can help bar regulars return.\n\n"
                    "Caution: Review local alcohol promotion rules before offering rewards."
                ),
            )
        )
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "what are the best ways bars increase repeat customers?",
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertEqual(text.count("Compliance note:"), 0)
        self.assertEqual(text.lower().count("caution:"), 1)

    def test_ai_generate_does_not_apply_stale_bar_risk_to_cellphone_question(self) -> None:
        handlers = build_ai_handlers(
            self._deps(
                [],
                model_text="Loyalty programs and upgrade reminders can help cellphone stores increase repeat customers.",
                receptionist_recent_turns=[
                    "User previously asked about bars, alcohol promotions, and loyalty rewards.",
                ],
            )
        )
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "what are the main ways cellphone stores increase repeat customers?",
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertNotIn("Compliance note:", text)

    def test_ai_generate_ignores_generic_risk_instruction_for_cellphone_plan(self) -> None:
        handlers = build_ai_handlers(
            self._deps(
                [],
                model_text=(
                    "1. Loyalty programs with upgrade rewards\n"
                    "2. Personalized accessory recommendations\n"
                    "3. Fast device setup help\n"
                    "4. Reliable repair guidance\n"
                    "5. Follow-up reminders"
                ),
            )
        )
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": (
                    "User request: what are the main ways cellphone stores increase repeat customers?\n\n"
                    "Answer plan:\n"
                    "- Provide a complete numbered list of 5 substantive items unless fewer genuinely exist.\n"
                    "- If any recommendation touches legal, regulatory, safety, financial, or policy risk, include one brief verification caution only if the answer has not already included one."
                ),
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertNotIn("Compliance note:", text)

    def test_ai_generate_still_applies_risk_note_for_bar_plan(self) -> None:
        handlers = build_ai_handlers(
            self._deps(
                [],
                model_text=(
                    "1. Loyalty programs with rewards\n"
                    "2. Event nights\n"
                    "3. Faster service\n"
                    "4. Consistent atmosphere\n"
                    "5. Customer feedback"
                ),
            )
        )
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": (
                    "User request: what are the main ways bars increase repeat customers?\n\n"
                    "Answer plan:\n"
                    "- Provide a complete numbered list of 5 substantive items unless fewer genuinely exist.\n"
                    "- If any recommendation touches legal, regulatory, safety, financial, or policy risk, include one brief verification caution only if the answer has not already included one."
                ),
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertIn("Compliance note:", text)

    def test_ai_generate_retries_incomplete_planned_numbered_list_once(self) -> None:
        router = SequenceModelRouter(
            [
                "1. Service quality",
                "1. Service quality\n2. Atmosphere\n3. Consistency\n4. Community\n5. Practical follow-up",
            ]
        )
        deps = self._deps([])
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "model_router": router,
            }
        )
        handlers = build_ai_handlers(deps)
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": (
                    "User request: what are the main ways stores increase repeat customers?\n\n"
                    "Answer plan:\n"
                    "- Provide a complete numbered list of 5 substantive items unless fewer genuinely exist.\n"
                    "- Do not stop after the first item."
                ),
                "session_id": "sess_1",
            }
        )
        self.assertEqual(len(router.user_prompts), 2)
        self.assertIn("did not complete the requested numbered list", router.user_prompts[1])
        self.assertIn("5. Practical follow-up", result["content"][0]["text"])

    def test_ai_generate_rejects_incomplete_list_when_retry_is_still_incomplete(self) -> None:
        router = SequenceModelRouter(
            [
                "1. Loyalty programs",
                "1. Loyalty programs\n2. Atmosphere",
            ]
        )
        deps = self._deps([])
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "model_router": router,
            }
        )
        handlers = build_ai_handlers(deps)
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": (
                    "User request: what are the main ways stores increase repeat customers?\n\n"
                    "Answer plan:\n"
                    "- Provide a complete numbered list of 5 substantive items unless fewer genuinely exist.\n"
                    "- Do not stop after the first item."
                ),
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertIn("The AI returned an incomplete list (2 of 5 requested items)", text)
        self.assertIn("Automatic retry also returned an incomplete answer.", text)

    def test_ai_generate_reports_retry_failure_for_incomplete_planned_list(self) -> None:
        router = PartialThenFailingModelRouter()
        deps = self._deps([])
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "model_router": router,
            }
        )
        handlers = build_ai_handlers(deps)
        result = handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": (
                    "User request: what are the main ways stores increase repeat customers?\n\n"
                    "Answer plan:\n"
                    "- Provide a complete numbered list of 5 substantive items unless fewer genuinely exist.\n"
                    "- Do not stop after the first item."
                ),
                "session_id": "sess_1",
            }
        )
        text = result["content"][0]["text"]
        self.assertIn("The AI returned an incomplete list (1 of 5 requested items)", text)
        self.assertIn("Automatic retry failed.", text)
        self.assertIn("429 quota exceeded", text)

    def test_ai_generate_includes_provider_attempts_in_failure_message(self) -> None:
        deps = self._deps([])
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "model_router": FailingModelRouter(),
            }
        )
        handlers = build_ai_handlers(deps)
        with self.assertRaises(HTTPException) as raised:
            handlers["office.ai_generate"](
                {
                    "workspace_id": "ws_1",
                    "user_prompt": "what are the main ways bars increase repeat customers?",
                    "session_id": "sess_1",
                }
            )
        detail = raised.exception.detail
        self.assertIn("Attempts:", detail["message"])
        self.assertIn("gemini: request failed: 429 quota exceeded", detail["message"])
        self.assertIn("groq: unavailable", detail["message"])


if __name__ == "__main__":
    unittest.main()
