from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from office_app.server.handlers.ai_handlers import build_ai_handlers
from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.model_router import ModelRouteResult, ModelRoutingError
from office_app.server.ocr_service import OcrServiceError


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


class FailingOcrService:
    def extract_text(self, *, file_name: str, mime_type: Optional[str], content_bytes: bytes) -> Dict[str, Any]:
        raise OcrServiceError("Gemini API key is not configured for OCR.")


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
    def __init__(
        self,
        *,
        summary: str = "",
        recent_turns: Optional[List[str]] = None,
        room_memory_refs: Optional[List[Dict[str, Any]]] = None,
        persona_memory_refs: Optional[List[Dict[str, Any]]] = None,
        session_facts_text: str = "",
    ) -> None:
        self.summary = summary
        self.recent_turns = recent_turns or []
        self.room_memory_refs = room_memory_refs or []
        self.persona_memory_refs = persona_memory_refs or []
        self.session_facts_text = session_facts_text

    def build_model_context(self, *, workspace_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "active_room": "sales_department",
            "active_persona": "Sales Director",
            "session_id": session_id,
            "session_summary_text": self.summary,
            "recent_turns_text": list(self.recent_turns),
            "session_facts_text": self.session_facts_text,
            "room_behavior_memory_refs": list(self.room_memory_refs),
            "persona_behavior_memory_refs": list(self.persona_memory_refs),
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


class CapturingModelRouter:
    def __init__(self, text: str = "Default model response.") -> None:
        self.text = text
        self.contexts: List[Dict[str, Any]] = []
        self.system_prompts: List[str] = []

    def generate_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
        task_type: str = "conversation",
    ) -> ModelRouteResult:
        self.system_prompts.append(system_prompt)
        self.contexts.append(dict(context or {}))
        return ModelRouteResult(
            provider="gemini",
            model="gemini-2.5-flash-lite",
            text=self.text,
            task_type=task_type,
            fallback_used=False,
            attempts=[],
        )


class FakeArchiveService:
    def get_artifact(self, workspace_id: str, artifact_id: str) -> Dict[str, Any]:
        return {
            "artifact_id": artifact_id,
            "workspace_id": workspace_id,
            "type": "room_behavior_memory",
            "content": "Sales questions pertain to Oregon businesses.",
            "metadata": {"memory_kind": "room_behavior", "target_room": "sales_department"},
        }


class FakeWorkContextService:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: List[Dict[str, Any]] = []

    def list_contexts(self, workspace_id: str, *, status: str = "active", limit: int = 10) -> List[Dict[str, Any]]:
        self.calls.append({"workspace_id": workspace_id, "status": status, "limit": limit})
        return list(self.rows[:limit])


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
        ocr_service: Optional[Any] = None,
        model_text: Optional[str] = None,
        receptionist_summary: str = "",
        receptionist_recent_turns: Optional[List[str]] = None,
        receptionist_room_memory_refs: Optional[List[Dict[str, Any]]] = None,
        work_context_rows: Optional[List[Dict[str, Any]]] = None,
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
                room_memory_refs=receptionist_room_memory_refs,
            ),
            workspace_file_service=workspace_service,
            private_file_service=private_service,
            search_service=search_service,
            ocr_service=ocr_service or FakeOcrService(),
            model_router=FakeModelRouter(model_text or "Default model response."),
            user_service=None,
            utc_now=lambda: "2026-04-24T12:00:00Z",
            stable_state_sha=lambda state: "sha",
            append_incident=lambda **kwargs: "inc",
            error_missing_required_field=lambda field: ValueError(field),
            resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
            work_context_service=FakeWorkContextService(work_context_rows or []),
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

    def test_ocr_extract_surfaces_specific_ocr_failure_message(self) -> None:
        deps = self._deps(
            [
                {
                    "workspace_id": "ws_1",
                    "file_id": "file_123",
                    "original_name": "scan.pdf",
                    "mime_type": "application/pdf",
                    "scope": "workspace",
                    "scope_ref": "workspace",
                }
            ],
            ocr_service=FailingOcrService(),
        )
        handlers = build_ai_handlers(deps)
        with self.assertRaises(HTTPException) as cm:
            handlers["office.ocr_extract"](
                {
                    "workspace_id": "ws_1",
                    "file_id": "file_123",
                }
            )
        self.assertEqual(cm.exception.status_code, 502)
        self.assertEqual(cm.exception.detail["message"], "Gemini API key is not configured for OCR.")

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

    def test_ai_generate_resolves_room_behavior_memory_refs_into_context(self) -> None:
        router = CapturingModelRouter()
        deps = self._deps(
            [],
            receptionist_room_memory_refs=[{"workspace_id": "ws_1", "artifact_id": "art_oregon"}],
        )
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "archive_service": FakeArchiveService(),
                "model_router": router,
            }
        )
        handlers = build_ai_handlers(deps)
        handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "what are the main ways bars increase repeat customers?",
                "session_id": "sess_1",
            }
        )
        self.assertIn("Sales questions pertain to Oregon businesses.", router.contexts[0]["room_behavior_memory_text"])

    def test_ai_generate_includes_active_work_context(self) -> None:
        router = CapturingModelRouter()
        deps = self._deps(
            [],
            work_context_rows=[
                {
                    "context_id": "ctx_nancy_email_sess_1",
                    "title": "Email to James",
                    "summary": "Nancy is waiting for the email body.",
                    "status": "active",
                    "source_type": "nancy_email",
                    "active_room": "my_office",
                    "active_persona": "Nancy",
                    "updated_at": "2026-07-03T08:00:00Z",
                }
            ],
        )
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "model_router": router,
            }
        )
        handlers = build_ai_handlers(deps)

        handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "what should I do next?",
                "session_id": "sess_1",
            }
        )

        context = router.contexts[0]
        self.assertEqual(deps.work_context_service.calls[0], {"workspace_id": "ws_1", "status": "active", "limit": 8})
        self.assertEqual(context["active_work_context"][0]["title"], "Email to James")
        self.assertIn("Email to James - Nancy is waiting for the email body.", context["active_work_context_text"])
        self.assertIn("(my_office/Nancy)", context["active_work_context_text"])

    def test_ai_generate_separates_persona_style_memory_from_room_memory(self) -> None:
        router = CapturingModelRouter()
        deps = self._deps(
            [],
            receptionist_room_memory_refs=[{"workspace_id": "ws_1", "artifact_id": "art_oregon"}],
        )
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "receptionist_context_service": FakeReceptionistContextService(
                    summary="",
                    recent_turns=[],
                    room_memory_refs=[{"workspace_id": "ws_1", "artifact_id": "art_oregon"}],
                    persona_memory_refs=[{"workspace_id": "ws_1", "artifact_id": "art_carnegie"}],
                ),
                "archive_service": FakeArchiveService(),
                "model_router": router,
            }
        )
        original_get_artifact = deps.archive_service.get_artifact

        def get_artifact(workspace_id: str, artifact_id: str) -> Dict[str, Any]:
            if artifact_id == "art_carnegie":
                return {
                    "artifact_id": artifact_id,
                    "workspace_id": workspace_id,
                    "type": "persona_behavior_memory",
                    "content": "Answer sales questions with How to Win Friends and Influence People in mind.",
                    "metadata": {"memory_kind": "persona_behavior", "target_room": "sales_department", "target_persona": "Sales Director"},
                }
            return original_get_artifact(workspace_id, artifact_id)

        deps.archive_service.get_artifact = get_artifact  # type: ignore[method-assign]
        handlers = build_ai_handlers(deps)
        handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "what are the best ways bars increase repeat customers?",
                "session_id": "sess_1",
            }
        )
        context = router.contexts[0]
        self.assertIn("Sales questions pertain to Oregon businesses.", context["room_behavior_memory_text"])
        self.assertIn("friendly, empathetic, relationship-first style", context["persona_behavior_memory_text"])
        self.assertNotIn("How to Win Friends and Influence People", context["persona_behavior_memory_text"])

    def test_ai_generate_propagates_session_facts_into_context(self) -> None:
        router = CapturingModelRouter()
        deps = self._deps([], model_text="Default model response.")
        deps = HandlerDeps(
            **{
                **deps.__dict__,
                "receptionist_context_service": FakeReceptionistContextService(
                    summary="",
                    recent_turns=["You [user]: I live in Oregon."],
                    room_memory_refs=[],
                    session_facts_text="- User lives in Oregon.",
                ),
                "model_router": router,
            }
        )
        handlers = build_ai_handlers(deps)
        handlers["office.ai_generate"](
            {
                "workspace_id": "ws_1",
                "user_prompt": "where do I live?",
                "session_id": "sess_1",
            }
        )
        self.assertIn("session_facts_text", router.contexts[0])
        self.assertIn("Use session facts as transient thread-local context", router.system_prompts[0])
        self.assertIn("Do not invent unsupported factual details", router.system_prompts[0])

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

    def test_ai_generate_retries_yes_no_question_until_direct_answer(self) -> None:
        router = SequenceModelRouter(
            [
                "The evidence suggests it does.",
                "Yes. The evidence suggests it does.",
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
                "user_prompt": "does it have live music?",
                "session_id": "sess_1",
            }
        )
        self.assertEqual(len(router.user_prompts), 2)
        self.assertIn("Internal answer contract:", router.user_prompts[0])
        self.assertIn("Answer the question directly in the first word: Yes or No.", router.user_prompts[1])
        self.assertEqual(result["content"][0]["text"], "Yes. The evidence suggests it does.")

    def test_ai_generate_renders_structured_yes_no_contract_response(self) -> None:
        router = SequenceModelRouter(
            [
                "Direct answer: Yes\nReason: Search results describe it as a music venue.\nCaveat: Check the current event calendar for specific dates.",
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
                    "User request: does it have live music?\n\n"
                    "Search results:\n"
                    "1. Blairally (Google): Music Venue/Arcade in Eugene, Oregon.\n\n"
                    "Write the response the user should see."
                ),
                "session_id": "sess_1",
            }
        )
        self.assertIn("Direct answer: Yes, No, or Uncertain", router.user_prompts[0])
        self.assertEqual(
            result["content"][0]["text"],
            "Yes. Search results describe it as a music venue. Check the current event calendar for specific dates.",
        )

    def test_ai_generate_retries_single_choice_question_until_one_answer(self) -> None:
        router = SequenceModelRouter(
            [
                "The strongest options are service quality and consistency.",
                "Service quality. It builds trust and affects every repeat interaction.",
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
                "user_prompt": "which one is most effective?",
                "session_id": "sess_1",
            }
        )
        self.assertEqual(len(router.user_prompts), 2)
        self.assertIn("Direct answer: one single best option only", router.user_prompts[0])
        self.assertIn("single best option", router.user_prompts[1].lower())
        self.assertEqual(
            result["content"][0]["text"],
            "Service quality. It builds trust and affects every repeat interaction.",
        )

    def test_ai_generate_renders_structured_single_choice_contract_response(self) -> None:
        router = SequenceModelRouter(
            [
                "Direct answer: Service quality\nReason: It builds trust and affects every repeat interaction.\nCaveat: none",
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
                "user_prompt": "which one is most effective?",
                "session_id": "sess_1",
            }
        )
        self.assertEqual(
            result["content"][0]["text"],
            "Service quality. It builds trust and affects every repeat interaction.",
        )

    def test_ai_generate_renders_structured_comparison_contract_response(self) -> None:
        router = SequenceModelRouter(
            [
                "Summary: Referrals are stronger for conversion, while ads scale faster.\n"
                "Side A: Referrals bring warmer leads and stronger trust.\n"
                "Side B: Digital ads reach more people but convert less efficiently.\n"
                "Recommendation: Start with referrals, then add ads to scale."
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
                "user_prompt": "compare referrals vs digital ads for insurance leads",
                "session_id": "sess_1",
            }
        )
        self.assertIn("Summary: one sentence that answers the comparison directly", router.user_prompts[0])
        self.assertIn("Referrals are stronger for conversion", result["content"][0]["text"])
        self.assertIn("Start with referrals, then add ads to scale.", result["content"][0]["text"])

    def test_ai_generate_renders_structured_grounded_entity_summary_response(self) -> None:
        router = SequenceModelRouter(
            [
                "Summary: Blairally appears to be a music venue and arcade in Eugene, Oregon.\n"
                "Evidence: Search snippets describe it as a Music Venue/Arcade and mention events.\n"
                "Unknowns: I do not have verified current event dates."
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
                    "User request: what can you tell me about Blairally?\n\n"
                    "Search results:\n"
                    "1. Blairally (Google): Music Venue/Arcade in Eugene, Oregon.\n"
                    "2. Blairally (Facebook): Events and live performances.\n\n"
                    "Write the response the user should see."
                ),
                "session_id": "sess_1",
            }
        )
        self.assertIn("Use only grounded facts from the provided results.", router.user_prompts[0])
        self.assertIn("Blairally appears to be a music venue and arcade in Eugene, Oregon.", result["content"][0]["text"])
        self.assertIn("I do not have verified current event dates.", result["content"][0]["text"])

    def test_ai_generate_fails_closed_for_grounded_yes_no_when_retry_is_still_indirect(self) -> None:
        router = SequenceModelRouter(
            [
                "The search results suggest it may host events.",
                "The available information suggests that possibility.",
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
                    "User request: does it have live music?\n\n"
                    "Search results:\n"
                    "1. Blairally (Google): Music Venue/Arcade in Eugene, Oregon.\n\n"
                    "Write the response the user should see."
                ),
                "session_id": "sess_1",
            }
        )
        self.assertEqual(
            result["content"][0]["text"],
            "I could not produce a complete grounded yes/no answer from the available information without guessing.",
        )

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
