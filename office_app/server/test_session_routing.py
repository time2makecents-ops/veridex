from __future__ import annotations

import shutil
import uuid
from pathlib import Path
import unittest

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


class SessionRoutingTests(unittest.TestCase):
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
            "nancy_service": app_module.nancy_service,
            "router": app_module.router,
            "pipeline": app_module.pipeline,
        }

        try:
            temp_store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_kernel = WorkspaceKernel(store=temp_store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_archive = ArchiveService(workspaces_dir=workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            temp_user = app_module.UserService(kernel=temp_kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
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
            app_module.nancy_service = temp_nancy
            app_module.router = temp_router
            app_module.pipeline = temp_pipeline

            app_module.register_tools(
                temp_router,
                {
                    "office.workspaces_list": app_module.handle_workspaces_list,
                    "office.workspace_new": app_module.handle_workspace_new,
                    "office.bootstrap": app_module.handle_office_bootstrap,
                    "office.state_get": app_module.handle_office_state_get,
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
        finally:
            app_module.store = original["store"]
            app_module.kernel = original["kernel"]
            app_module.memo_service = original["memo_service"]
            app_module.archive_service = original["archive_service"]
            app_module.user_service = original["user_service"]
            app_module.nancy_service = original["nancy_service"]
            app_module.router = original["router"]
            app_module.pipeline = original["pipeline"]
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
