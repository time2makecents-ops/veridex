from __future__ import annotations

import shutil
import uuid
from pathlib import Path
import unittest

from fastapi import HTTPException

from office_app.server.app import (
    LobbyOnboardRequest,
    NaturalLanguageRequest,
    RequestPipeline,
    ArchiveService,
    MemoService,
    NancyService,
    CommandRouter,
    WorkspaceKernel,
    WorkspaceStore,
    NAVIGATOR_CONTROL,
    RUNTIME_DIR,
    WORKSPACES_DIR,
    LEGACY_MEMOS_DIR,
    utc_now,
    app as fastapi_app,
    handle_natural_language_request,
    lobby_onboard,
)
import office_app.server.app as app_module
from office_app.server.search_service import SearchServiceError


class SessionRoutingTests(unittest.TestCase):
    def test_grounded_entity_search_failure_fails_closed_in_sales_department(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_grounded_entity_search"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        class FailingSearchService:
            def search_web(self, *, query, limit=5, recency_days=None):
                raise SearchServiceError("provider down")

            def search_reviews(self, *, query, location=None, time_window=None, limit=5):
                raise SearchServiceError("provider down")

            def search_places(self, *, query, location=None, category=None, needs_location=False, limit=5):
                raise SearchServiceError("provider down")

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
            "search_service": app_module.search_service,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.search_service = FailingSearchService()
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            session_id = onboard_result["structuredContent"]["session_id"]
            temp_user.remember_session_room(session_id, active_room="sales_department", active_persona="Sales Director")

            response = handle_natural_language_request(
                NaturalLanguageRequest(
                    text="search for blairally and give me information about the company",
                    session_id=session_id,
                )
            )
            self.assertEqual(
                response["structuredContent"]["response_text"],
                "I could not verify information about blairally because the search failed. I should not guess.",
            )
            self.assertEqual(response["structuredContent"]["routing"]["route_kind"], "clarify")
            self.assertEqual(response["structuredContent"]["speaker"], "Navigator")
            self.assertTrue(response["structuredContent"]["navigator_activation"]["activated"])
            self.assertEqual(response["structuredContent"]["navigator_activation"]["visibility"], "VISIBLE")
            transcript = temp_store.load_transcript(onboard_result["structuredContent"]["workspace_id"], session_id=session_id)
            self.assertEqual(transcript[-1]["speaker"], "Navigator")
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.search_service = original["search_service"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_unknown_entity_lookup_shows_visible_navigator_response_in_sales_department(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_entity_grounding_navigator"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            workspace_id = onboard_result["structuredContent"]["workspace_id"]
            session_id = onboard_result["structuredContent"]["session_id"]
            temp_user.remember_session_room(session_id, active_room="sales_department", active_persona="Sales Director")

            response = handle_natural_language_request(
                NaturalLanguageRequest(
                    text="what can you tell me about blairally",
                    session_id=session_id,
                )
            )

            self.assertEqual(
                response["structuredContent"]["response_text"],
                "Veridex doesn't have any verified information about blairally. Have the Sales Department do an internet search or search your other sessions if you want to know more.",
            )
            self.assertEqual(response["structuredContent"]["speaker"], "Navigator")
            self.assertEqual(response["structuredContent"]["routing"]["capability"], "clarification.entity_grounding")
            self.assertTrue(response["structuredContent"]["navigator_activation"]["activated"])
            self.assertEqual(response["structuredContent"]["navigator_activation"]["visibility"], "VISIBLE")
            transcript = temp_store.load_transcript(workspace_id, session_id=session_id)
            self.assertEqual(transcript[-1]["speaker"], "Navigator")
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_unknown_entity_lookup_shows_navigator_in_marketing_room(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_entity_grounding_marketing_navigator"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            workspace_id = onboard_result["structuredContent"]["workspace_id"]
            session_id = onboard_result["structuredContent"]["session_id"]
            temp_user.remember_session_room(session_id, active_room="marketing_room", active_persona="Marketing Director")

            response = handle_natural_language_request(
                NaturalLanguageRequest(
                    text="what can you tell me about blairally",
                    session_id=session_id,
                )
            )

            self.assertEqual(
                response["structuredContent"]["response_text"],
                "Veridex doesn't have any verified information about blairally. Have the Marketing & Advertising do an internet search or search your other sessions if you want to know more.",
            )
            self.assertEqual(response["structuredContent"]["speaker"], "Navigator")
            transcript = temp_store.load_transcript(workspace_id, session_id=session_id)
            self.assertEqual(transcript[-1]["speaker"], "Navigator")
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_model_style_unsupported_entity_answer_is_normalized_to_navigator(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_model_governance_normalize"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            workspace_id = onboard_result["structuredContent"]["workspace_id"]
            session_id = onboard_result["structuredContent"]["session_id"]
            temp_user.remember_session_room(session_id, active_room="marketing_room", active_persona="Marketing Director")

            response = {
                "structuredContent": {
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "provider": "groq",
                    "model": "llama-3.1-8b-instant",
                    "response_text": (
                        'As the Marketing Director in the Marketing & Advertising room, I can tell you that '
                        'Veridex does not have any verified information about "blairally." '
                        "If you'd like to learn more, I can ask the Lobby to perform an internet search or check your other sessions."
                    ),
                    "routing": {
                        "route_kind": "model",
                        "capability": "ai.respond",
                        "tool": "office.ai_generate",
                        "reason": "No explicit tool or room command found. Using the model route.",
                    },
                },
                "content": [{"type": "text", "text": "placeholder"}],
            }

            normalized = app_module._normalize_model_governance_response(
                response,
                workspace_id=workspace_id,
                session_id=session_id,
                request_text="what can you tell me about blairally",
            )

            self.assertEqual(normalized["structuredContent"]["speaker"], "Navigator")
            self.assertEqual(normalized["structuredContent"]["routing"]["route_kind"], "clarify")
            self.assertEqual(
                normalized["structuredContent"]["response_text"],
                "Veridex doesn't have any verified information about blairally. Have the Marketing & Advertising do an internet search or search your other sessions if you want to know more.",
            )
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_workspace_new_reuses_existing_label(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_workspace_new"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            first = app_module.handle_workspace_new({"label": "testspace"})
            second = app_module.handle_workspace_new({"label": "testspace"})

            first_workspace_id = str(first["structuredContent"]["workspace_id"])
            second_workspace_id = str(second["structuredContent"]["workspace_id"])
            self.assertEqual(first_workspace_id, second_workspace_id)

            idx = temp_kernel.list_workspaces()
            matching = [row for row in idx.get("workspaces", []) if str(row.get("label") or "") == "testspace"]
            self.assertEqual(len(matching), 1)
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_workspace_new_does_not_inherit_current_session_workspace(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_workspace_new_scope"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = app_module.lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue
            self.assertIsNotNone(onboard_result)
            session_id = str(onboard_result["structuredContent"]["session_id"])
            workspace_id = str(onboard_result["structuredContent"]["workspace_id"])

            resolved_new = app_module.resolve_workspace_id("office.workspace_new", {"session_id": session_id})
            resolved_activate = app_module.resolve_workspace_id(
                "office.workspace_activate",
                {"session_id": session_id, "workspace_id": "ws_test1234"},
            )

            self.assertEqual(resolved_new, "")
            self.assertEqual(resolved_activate, "ws_test1234")
            self.assertEqual(workspace_id, str(onboard_result["structuredContent"]["workspace_id"]))
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_request_uses_session_workspace(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            app_module.register_tools(
                temp_router,
                {
                    "office.workspaces_list": app_module.handle_workspaces_list,
                    "office.workspace_new": app_module.handle_workspace_new,
                    "office.workspace_activate": app_module.handle_workspace_activate,
                    "office.bootstrap": app_module.handle_office_bootstrap,
                    "office.state_get": app_module.handle_office_state_get,
                    "office.transcript_get": app_module.handle_office_transcript_get,
                    "office.room_set": app_module.handle_office_room_set,
                    "office.nancy_route": app_module.handle_office_nancy_route,
                    "mailroom.dispatch": app_module.handle_mailroom_dispatch,
                    "office.artifact_create": app_module.handle_artifact_create,
                    "office.artifact_get": app_module.handle_artifact_get,
                    "office.artifact_list": app_module.handle_artifact_list,
                    "office.artifact_update": app_module.handle_artifact_update,
                    "office.artifact_append": app_module.handle_artifact_append,
                    "office.artifact_archive": app_module.handle_artifact_archive,
                    "office.memos_list": app_module.handle_memos_list,
                    "office.memo_get": app_module.handle_memo_get,
                    "office.archive_store_text": app_module.handle_archive_store_text,
                    "office.archive_list": app_module.handle_archive_list,
                    "office.archive_get": app_module.handle_archive_get,
                    "office.nancy_artifacts_list": app_module.handle_nancy_artifacts_list,
                    "office.nancy_artifact_open": app_module.handle_nancy_artifact_open,
                    "office.nancy_workspace_briefing": app_module.handle_nancy_workspace_briefing,
                    "office.room_memory_remember": app_module.handle_room_memory_remember,
                    "office.room_memory_list": app_module.handle_room_memory_list,
                    "office.room_memory_forget": app_module.handle_room_memory_forget,
                },
            )
            temp_pipeline.tool_names = temp_router.tool_names()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(
                        LobbyOnboardRequest(name="Mira", pin_code=pin_code)
                    )
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            structured = onboard_result["structuredContent"]
            session_id = structured["session_id"]
            workspace_id = structured["workspace_id"]

            response = handle_natural_language_request(
                NaturalLanguageRequest(text="show artifacts", session_id=session_id)
            )
            payload = response["structuredContent"]
            self.assertEqual(payload["workspace_id"], workspace_id)
            self.assertEqual(payload["retrieval_scope"], "workspace")
            transcript = temp_store.load_transcript(workspace_id, limit=10, session_id=session_id)
            user_rows = [row for row in transcript if row.get("role") == "user" and row.get("text") == "show artifacts"]
            assistant_rows = [row for row in transcript if row.get("role") == "assistant" and "artifact" in str(row.get("text") or "").lower()]
            self.assertTrue(user_rows)
            self.assertTrue(assistant_rows)

            handle_natural_language_request(
                NaturalLanguageRequest(text="what can you do?", session_id=session_id)
            )
            updated_transcript = temp_store.load_transcript(workspace_id, limit=10, session_id=session_id)
            self.assertTrue(
                [
                    row
                    for row in updated_transcript
                    if row.get("role") == "assistant" and "Across Veridex" in str(row.get("text") or "")
                ]
            )

            temp_user.remember_session_room(session_id, active_room="sales_department", active_persona="Sales Director")
            stale_state = temp_kernel.get_state(workspace_id)
            stale_state["active_room"] = "lobby"
            stale_state["active_persona"] = "Receptionist"
            temp_store.save_state(workspace_id, stale_state)

            memory_response = handle_natural_language_request(
                NaturalLanguageRequest(text="remember that Sales questions pertain to Oregon businesses.", session_id=session_id)
            )
            memory_payload = memory_response["structuredContent"]
            self.assertEqual(memory_payload["room_id"], "sales_department")
            self.assertEqual(memory_payload["artifact"]["metadata"]["target_room"], "sales_department")
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_start_new_session_request_prompts_for_name_and_then_creates_session(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_new_session_context"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(
                kernel=temp_kernel,
                runtime_dir=runtime_dir,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            app_module.register_tools(
                temp_router,
                {
                    "office.workspaces_list": app_module.handle_workspaces_list,
                    "office.workspace_new": app_module.handle_workspace_new,
                    "office.workspace_activate": app_module.handle_workspace_activate,
                    "office.bootstrap": app_module.handle_office_bootstrap,
                    "office.state_get": app_module.handle_office_state_get,
                    "office.transcript_get": app_module.handle_office_transcript_get,
                    "office.room_set": app_module.handle_office_room_set,
                    "office.nancy_route": app_module.handle_office_nancy_route,
                    "office.sessions_list": app_module.handle_sessions_list,
                    "office.session_create": app_module.handle_session_create,
                    "office.session_activate": app_module.handle_session_activate,
                    "mailroom.dispatch": app_module.handle_mailroom_dispatch,
                    "office.artifact_create": app_module.handle_artifact_create,
                    "office.artifact_get": app_module.handle_artifact_get,
                    "office.artifact_list": app_module.handle_artifact_list,
                    "office.artifact_update": app_module.handle_artifact_update,
                    "office.artifact_append": app_module.handle_artifact_append,
                    "office.artifact_archive": app_module.handle_artifact_archive,
                    "office.memos_list": app_module.handle_memos_list,
                    "office.memo_get": app_module.handle_memo_get,
                    "office.archive_store_text": app_module.handle_archive_store_text,
                    "office.archive_list": app_module.handle_archive_list,
                    "office.archive_get": app_module.handle_archive_get,
                    "office.nancy_artifacts_list": app_module.handle_nancy_artifacts_list,
                    "office.nancy_artifact_open": app_module.handle_nancy_artifact_open,
                    "office.nancy_workspace_briefing": app_module.handle_nancy_workspace_briefing,
                    "office.room_memory_remember": app_module.handle_room_memory_remember,
                    "office.room_memory_list": app_module.handle_room_memory_list,
                    "office.room_memory_forget": app_module.handle_room_memory_forget,
                    "office.ai_generate": app_module.handle_ai_generate,
                    "office.search_web": app_module.handle_search_web,
                    "office.search_reviews": app_module.handle_search_reviews,
                    "office.search_places": app_module.handle_search_places,
                    "office.ocr_extract": app_module.handle_ocr_extract,
                },
            )
            temp_pipeline.tool_names = temp_router.tool_names()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            old_session_id = str(onboard_result["structuredContent"]["session_id"])
            workspace_id = str(onboard_result["structuredContent"]["workspace_id"])
            temp_user.remember_session_room(old_session_id, active_room="sales_department", active_persona="Sales Director")

            prompt_response = handle_natural_language_request(
                NaturalLanguageRequest(text="start new session", session_id=old_session_id)
            )
            prompt_payload = prompt_response["structuredContent"]
            self.assertEqual(prompt_payload["session_id"], old_session_id)
            self.assertEqual(prompt_payload["routing"]["route_kind"], "clarify")
            self.assertEqual(prompt_payload["response_text"], "What should I name the new session?")
            self.assertEqual(prompt_payload["speaker"], "Navigator")

            old_transcript = temp_store.load_transcript(workspace_id, limit=20, session_id=old_session_id)
            self.assertTrue(
                [
                    row
                    for row in old_transcript
                    if row.get("role") == "user" and row.get("text") == "start new session"
                ]
            )
            self.assertTrue(
                [
                    row
                    for row in old_transcript
                    if row.get("role") == "assistant"
                    and row.get("text") == "What should I name the new session?"
                    and row.get("speaker") == "Navigator"
                ]
            )

            response = handle_natural_language_request(
                NaturalLanguageRequest(text="Restaurant strategy", session_id=old_session_id)
            )
            payload = response["structuredContent"]
            new_session_id = str(payload["session_id"])

            self.assertNotEqual(new_session_id, old_session_id)
            self.assertEqual(response["session_id"], new_session_id)
            self.assertEqual(payload["workspace_id"], workspace_id)
            self.assertEqual(payload["title"], "Restaurant strategy")

            resolved_workspace_id = str(app_module.user_service.resolve_workspace_for_session(new_session_id) or workspace_id)
            new_transcript = temp_store.load_transcript(resolved_workspace_id, limit=20, session_id=new_session_id)
            self.assertTrue(
                [
                    row
                    for row in new_transcript
                    if row.get("role") == "system" and "Session created:" in str(row.get("text") or "")
                ]
            )
            self.assertFalse(
                [
                    row
                    for row in new_transcript
                    if row.get("role") == "user" and row.get("text") == "start new session"
                ]
            )

            followup = handle_natural_language_request(
                NaturalLanguageRequest(
                    text="what are the main ways cellphone stores increase repeat customers?",
                    session_id=new_session_id,
                )
            )
            self.assertEqual(followup["structuredContent"]["session_id"], new_session_id)
            try:
                resolved_workspace_id = str(app_module.user_service.resolve_workspace_for_session(new_session_id) or workspace_id)
            except HTTPException:
                resolved_workspace_id = workspace_id
            updated_new_transcript = temp_store.load_transcript(resolved_workspace_id, limit=50, session_id=new_session_id)
            self.assertTrue(
                [
                    row
                    for row in updated_new_transcript
                    if row.get("role") == "user"
                    and row.get("text") == "what are the main ways cellphone stores increase repeat customers?"
                ]
            )

            session_list = handle_natural_language_request(
                NaturalLanguageRequest(text="list sessions", session_id=new_session_id)
            )
            session_list_text = session_list["content"][0]["text"]
            self.assertIn("Here are the sessions:", session_list_text)
            self.assertIn("Restaurant strategy", session_list_text)
            self.assertIn("[Active]", session_list_text)

            switched = handle_natural_language_request(
                NaturalLanguageRequest(text="go to session 2", session_id=new_session_id)
            )
            switched_payload = switched["structuredContent"]
            self.assertEqual(switched_payload["session_id"], old_session_id)
            self.assertIn("You are now in session", switched["content"][0]["text"])

            transcript_view = handle_natural_language_request(
                NaturalLanguageRequest(text="can you show this sessions thread?", session_id=old_session_id)
            )
            transcript_text = transcript_view["content"][0]["text"]
            self.assertIn("Current session thread:", transcript_text)
            self.assertIn("start new session", transcript_text)
            self.assertIn("What should I name the new session?", transcript_text)
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_session_list_confirmation_yes_lists_sessions_instead_of_navigating(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_session_list_confirmation"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(
                kernel=temp_kernel,
                runtime_dir=runtime_dir,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            app_module.register_tools(
                temp_router,
                {
                    "office.workspaces_list": app_module.handle_workspaces_list,
                    "office.workspace_new": app_module.handle_workspace_new,
                    "office.workspace_activate": app_module.handle_workspace_activate,
                    "office.bootstrap": app_module.handle_office_bootstrap,
                    "office.state_get": app_module.handle_office_state_get,
                    "office.transcript_get": app_module.handle_office_transcript_get,
                    "office.room_set": app_module.handle_office_room_set,
                    "office.nancy_route": app_module.handle_office_nancy_route,
                    "office.sessions_list": app_module.handle_sessions_list,
                    "office.session_create": app_module.handle_session_create,
                    "office.session_activate": app_module.handle_session_activate,
                    "mailroom.dispatch": app_module.handle_mailroom_dispatch,
                    "office.artifact_create": app_module.handle_artifact_create,
                    "office.artifact_get": app_module.handle_artifact_get,
                    "office.artifact_list": app_module.handle_artifact_list,
                    "office.artifact_update": app_module.handle_artifact_update,
                    "office.artifact_append": app_module.handle_artifact_append,
                    "office.artifact_archive": app_module.handle_artifact_archive,
                    "office.memos_list": app_module.handle_memos_list,
                    "office.memo_get": app_module.handle_memo_get,
                    "office.archive_store_text": app_module.handle_archive_store_text,
                    "office.archive_list": app_module.handle_archive_list,
                    "office.archive_get": app_module.handle_archive_get,
                    "office.nancy_artifacts_list": app_module.handle_nancy_artifacts_list,
                    "office.nancy_artifact_open": app_module.handle_nancy_artifact_open,
                    "office.nancy_workspace_briefing": app_module.handle_nancy_workspace_briefing,
                    "office.room_memory_remember": app_module.handle_room_memory_remember,
                    "office.room_memory_list": app_module.handle_room_memory_list,
                    "office.room_memory_forget": app_module.handle_room_memory_forget,
                    "office.ai_generate": app_module.handle_ai_generate,
                    "office.search_web": app_module.handle_search_web,
                    "office.search_reviews": app_module.handle_search_reviews,
                    "office.search_places": app_module.handle_search_places,
                    "office.ocr_extract": app_module.handle_ocr_extract,
                },
            )
            temp_pipeline.tool_names = temp_router.tool_names()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            session_id = str(onboard_result["structuredContent"]["session_id"])
            workspace_id = str(onboard_result["structuredContent"]["workspace_id"])
            temp_user.remember_session_room(session_id, active_room="sales_department", active_persona="Sales Director")

            clarify_response = handle_natural_language_request(
                NaturalLanguageRequest(text="what sessions are in this workspace", session_id=session_id)
            )
            clarify_payload = clarify_response["structuredContent"]
            self.assertEqual(clarify_payload["routing"]["route_kind"], "clarify")
            self.assertEqual(clarify_payload["routing"]["capability"], "session.list.confirmation")
            self.assertEqual(clarify_payload["response_text"], "Do you want me to list the sessions in this workspace?")
            self.assertEqual(clarify_payload["speaker"], "Navigator")

            state_after_clarify = temp_store.load_state(workspace_id)
            pending_map = state_after_clarify.get("pending_session_list_by_session")
            self.assertIsInstance(pending_map, dict)
            self.assertIn(session_id, pending_map)
            self.assertNotIn("pending_room_navigation", state_after_clarify)

            confirm_response = handle_natural_language_request(
                NaturalLanguageRequest(text="yes", session_id=session_id)
            )
            confirm_payload = confirm_response["structuredContent"]
            self.assertEqual(confirm_payload["routing"]["capability"], "session.list")
            self.assertEqual(confirm_payload["routing"]["route_kind"], "tool")
            confirm_text = confirm_response["content"][0]["text"]
            self.assertIn("Here are the sessions:", confirm_text)
            self.assertIn(session_id, confirm_text)
            self.assertNotIn("Active room set to", confirm_text)

            state_after_confirm = temp_store.load_state(workspace_id)
            self.assertNotIn("pending_session_list_by_session", state_after_confirm)
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_rename_session_command_renames_current_session(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_rename_session"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            app_module.register_tools(
                temp_router,
                {
                    "office.workspaces_list": app_module.handle_workspaces_list,
                    "office.workspace_new": app_module.handle_workspace_new,
                    "office.workspace_activate": app_module.handle_workspace_activate,
                    "office.bootstrap": app_module.handle_office_bootstrap,
                    "office.state_get": app_module.handle_office_state_get,
                    "office.transcript_get": app_module.handle_office_transcript_get,
                    "office.room_set": app_module.handle_office_room_set,
                    "office.nancy_route": app_module.handle_office_nancy_route,
                    "office.sessions_list": app_module.handle_sessions_list,
                    "office.session_create": app_module.handle_session_create,
                    "office.session_activate": app_module.handle_session_activate,
                    "office.session_rename": app_module.handle_session_rename,
                    "office.session_delete": app_module.handle_session_delete,
                    "mailroom.dispatch": app_module.handle_mailroom_dispatch,
                    "office.artifact_create": app_module.handle_artifact_create,
                    "office.artifact_get": app_module.handle_artifact_get,
                    "office.artifact_list": app_module.handle_artifact_list,
                    "office.artifact_update": app_module.handle_artifact_update,
                    "office.artifact_append": app_module.handle_artifact_append,
                    "office.artifact_archive": app_module.handle_artifact_archive,
                    "office.memos_list": app_module.handle_memos_list,
                    "office.memo_get": app_module.handle_memo_get,
                    "office.archive_store_text": app_module.handle_archive_store_text,
                    "office.archive_list": app_module.handle_archive_list,
                    "office.archive_get": app_module.handle_archive_get,
                    "office.nancy_artifacts_list": app_module.handle_nancy_artifacts_list,
                    "office.nancy_artifact_open": app_module.handle_nancy_artifact_open,
                    "office.nancy_workspace_briefing": app_module.handle_nancy_workspace_briefing,
                    "office.room_memory_remember": app_module.handle_room_memory_remember,
                    "office.room_memory_list": app_module.handle_room_memory_list,
                    "office.room_memory_forget": app_module.handle_room_memory_forget,
                    "office.ai_generate": app_module.handle_ai_generate,
                    "office.search_web": app_module.handle_search_web,
                    "office.search_reviews": app_module.handle_search_reviews,
                    "office.search_places": app_module.handle_search_places,
                    "office.ocr_extract": app_module.handle_ocr_extract,
                },
            )
            temp_pipeline.tool_names = temp_router.tool_names()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            session_id = str(onboard_result["structuredContent"]["session_id"])
            workspace_id = str(onboard_result["structuredContent"]["workspace_id"])
            temp_user.remember_session_room(session_id, active_room="sales_department", active_persona="Sales Director")

            response = handle_natural_language_request(
                NaturalLanguageRequest(text="rename this session newest test", session_id=session_id)
            )
            payload = response["structuredContent"]
            self.assertEqual(payload["routing"]["route_kind"], "tool")
            self.assertEqual(payload["routing"]["capability"], "session.rename")
            self.assertIn("Renamed session to Newest test.", response["content"][0]["text"])
            updated = temp_store.load_transcript(workspace_id, session_id=session_id, limit=20)
            self.assertTrue(any(row.get("text") == "rename this session newest test" for row in updated if row.get("role") == "user"))
            renamed_session = app_module.user_service.get_session(session_id)
            self.assertEqual(renamed_session["title"], "Newest test")

            info_response = handle_natural_language_request(
                NaturalLanguageRequest(text="what is the name of this session?", session_id=session_id)
            )
            info_payload = info_response["structuredContent"]
            self.assertEqual(info_payload["routing"]["capability"], "session.info")
            self.assertIn('This session is called "Newest test".', info_response["content"][0]["text"])
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_search_other_sessions_reads_matching_transcript_lines(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_search_other_sessions"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            workspace_id = onboard_result["structuredContent"]["workspace_id"]
            current_session_id = onboard_result["structuredContent"]["session_id"]
            temp_user.remember_session_room(current_session_id, active_room="sales_department", active_persona="Sales Director")

            created = app_module.handle_session_create(
                {
                    "workspace_id": workspace_id,
                    "session_id": current_session_id,
                    "title": "Wireless History",
                    "description": "Wireless History",
                }
            )
            other_session_id = created["structuredContent"]["session_id"]
            temp_store.append_transcript(
                workspace_id,
                "assistant",
                "sales_department",
                "I do not have verified information about Wireless Unlimited in this workspace. I can search for it if you want.",
                speaker="Navigator",
                session_id=other_session_id,
            )
            temp_store.append_transcript(
                workspace_id,
                "assistant",
                "sales_department",
                "Veridex doesn't have any verified information about Wireless Unlimited. Have the Sales Department do an internet search if you want to know more.",
                speaker="Navigator",
                session_id=other_session_id,
            )
            temp_store.append_transcript(
                workspace_id,
                "assistant",
                "sales_department",
                "Veridex does not have any verified information about Wireless Unlimited. I can initiate an internet search for you.",
                speaker="Sales Director",
                session_id=other_session_id,
            )
            temp_store.append_transcript(
                workspace_id,
                "assistant",
                "sales_department",
                (
                    "Wireless Unlimited sold AT&T service in Oregon. "
                    "It had retail locations in Eugene, Springfield, and Corvallis, "
                    "and it focused on local storefront sales, handset merchandising, "
                    "and in-person customer service for AT&T wireless plans."
                ),
                speaker="Sales Director",
                session_id=other_session_id,
            )

            response = handle_natural_language_request(
                NaturalLanguageRequest(
                    text="search other sessions for Wireless Unlimited",
                    session_id=current_session_id,
                )
            )

            response_text = response["structuredContent"]["response_text"]
            self.assertIn('I found 1 matching session(s) for "Wireless Unlimited":', response_text)
            self.assertIn("Wireless History", response_text)
            self.assertIn("Wireless Unlimited sold AT&T service in Oregon.", response_text)
            self.assertNotIn("I do not have verified information about Wireless Unlimited", response_text)

            detail_response = handle_natural_language_request(
                NaturalLanguageRequest(
                    text="can you list the information it gave in those sessions",
                    session_id=current_session_id,
                )
            )
            detail_text = detail_response["structuredContent"]["response_text"]
            self.assertIn('I found 1 matching session(s) for "Wireless Unlimited":', detail_text)
            self.assertIn("Sales Director: Wireless Unlimited sold AT&T service in Oregon.", detail_text)
            self.assertTrue(detail_response["structuredContent"]["detail"])
            full_response = app_module.handle_sessions_search(
                {
                    "workspace_id": workspace_id,
                    "session_id": current_session_id,
                    "query": "Wireless Unlimited",
                    "include_current": False,
                    "detail": True,
                    "expand_full": True,
                    "target_session_id": other_session_id,
                }
            )
            full_text = full_response["structuredContent"]["response_text"]
            self.assertIn('Here is the full response from Wireless History', full_text)
            self.assertIn("It had retail locations in Eugene, Springfield, and Corvallis", full_text)
            self.assertNotIn("...", full_text)
            self.assertTrue(full_response["structuredContent"]["expand_full"])
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_session_delete_rehomes_active_session_and_removes_transcript(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_delete_session"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            workspace_id = onboard_result["structuredContent"]["workspace_id"]
            first_session_id = onboard_result["structuredContent"]["session_id"]
            temp_user.remember_session_room(first_session_id, active_room="sales_department", active_persona="Sales Director")

            created = app_module.handle_session_create(
                {
                    "workspace_id": workspace_id,
                    "session_id": first_session_id,
                    "title": "Wireless History",
                    "description": "Wireless History",
                }
            )
            second_session_id = created["structuredContent"]["session_id"]
            temp_store.append_transcript(
                workspace_id,
                "assistant",
                "sales_department",
                "Session thread text for deletion.",
                speaker="Sales Director",
                session_id=second_session_id,
            )

            deleted = app_module.handle_session_delete(
                {
                    "session_id": second_session_id,
                    "target_session_id": second_session_id,
                }
            )

            self.assertEqual(deleted["structuredContent"]["deleted_session_id"], second_session_id)
            self.assertEqual(deleted["structuredContent"]["session_id"], first_session_id)
            self.assertFalse((workspaces_dir / workspace_id / "sessions" / second_session_id).exists())
            transcript = temp_store.load_transcript(workspace_id, limit=10, session_id=second_session_id)
            self.assertEqual(transcript, [])
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_session_delete_last_session_prompts_for_name(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_session_routing_test_delete_last_session"
        workspaces_dir = runtime_dir / "workspaces"
        legacy_memos_dir = runtime_dir / "memos"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)
        legacy_memos_dir.mkdir(parents=True, exist_ok=True)

        original = {
            "store": app_module.store,
            "kernel": app_module.kernel,
            "memo_service": app_module.memo_service,
            "archive_service": app_module.archive_service,
            "user_service": app_module.user_service,
            "receptionist_context_service": app_module.receptionist_context_service,
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_receptionist_context = app_module.ReceptionistContextService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_memo = MemoService(store=temp_store, legacy_memos_dir=legacy_memos_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_nancy = NancyService(
                kernel=temp_kernel,
                archive_service=temp_archive,
                store=temp_store,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
            )
            temp_router = CommandRouter()
            temp_pipeline = RequestPipeline(
                kernel=temp_kernel,
                navigator_control=NAVIGATOR_CONTROL,
                utc_now_fn=lambda: "2026-04-17T12:00:00Z",
                tool_names=[],
                app_version="1.3.0",
            )

            app_module.store = temp_store
            app_module.kernel = temp_kernel
            app_module.memo_service = temp_memo
            app_module.archive_service = temp_archive
            app_module.user_service = temp_user
            app_module.receptionist_context_service = temp_receptionist_context
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline
            app_module.refresh_handler_bindings()

            onboard_result = None
            for _ in range(20):
                pin_code = f"{uuid.uuid4().int % 10000:04d}"
                try:
                    onboard_result = lobby_onboard(LobbyOnboardRequest(name="Mira", pin_code=pin_code))
                    break
                except Exception:
                    continue

            self.assertIsNotNone(onboard_result)
            session_id = str(onboard_result["structuredContent"]["session_id"])
            workspace_id = str(onboard_result["structuredContent"]["workspace_id"])
            temp_user.remember_session_room(session_id, active_room="sales_department", active_persona="Sales Director")

            deleted = app_module.handle_session_delete(
                {
                    "session_id": session_id,
                    "target_session_id": session_id,
                }
            )

            deleted_text = deleted["content"][0]["text"]
            self.assertIn("What should I name the new session?", deleted_text)
            new_session_id = str(deleted["structuredContent"]["session_id"])
            self.assertNotEqual(new_session_id, session_id)
            self.assertEqual(deleted["structuredContent"]["created_replacement_session"], True)

            state = temp_store.load_state(workspace_id)
            pending_map = state.get("pending_session_create_by_session")
            self.assertIsInstance(pending_map, dict)
            self.assertIn(new_session_id, pending_map)
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.receptionist_context_service = original["receptionist_context_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            app_module.refresh_handler_bindings()
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
