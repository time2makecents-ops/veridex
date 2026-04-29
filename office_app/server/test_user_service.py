from __future__ import annotations

import json
import shutil
from pathlib import Path
import unittest

from fastapi import HTTPException

from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore
from office_app.server.user_service import UserService


class UserServiceTests(unittest.TestCase):
    def test_onboard_creates_user_and_workspace(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            result = service.onboard_user(name="Ada", display_name="Ada Lovelace", pin_code="2468")

            user = result["user"]
            session = result["session"]
            self.assertTrue(user["onboarding_complete"])
            self.assertEqual(user["name"], "Ada")
            self.assertEqual(user["display_name"], "Ada Lovelace")
            self.assertEqual(user["pin_code"], "2468")
            self.assertEqual(user["default_workspace_id"], result["workspace_id"])
            self.assertEqual(user["last_active_workspace_id"], result["workspace_id"])
            self.assertEqual(result["session_id"], session["session_id"])
            self.assertEqual(session["active_workspace_id"], result["workspace_id"])

            state = kernel.get_state(result["workspace_id"])
            self.assertEqual(state["workspace_id"], result["workspace_id"])
            self.assertEqual(state["active_room"], "lobby")

            fetched = service.get_user_by_pin("2468")
            self.assertEqual(fetched["user_id"], user["user_id"])
            self.assertEqual(service.resolve_workspace_for_session(result["session_id"]), result["workspace_id"])

            users_root = runtime_dir / "users"
            user_folders = [path for path in users_root.iterdir() if path.is_dir()]
            self.assertEqual(len(user_folders), 1)
            profile_path = user_folders[0] / "profile.json"
            self.assertTrue(profile_path.exists())
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(profile["user_id"], user["user_id"])
            self.assertEqual(profile["pin_code"], "2468")
            self.assertFalse(profile["has_face_photo"])
            self.assertEqual((user_folders[0] / "pin_code.txt").read_text(encoding="utf-8").strip(), "2468")
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_onboard_writes_face_photo_file(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test_photo"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            face_photo_data = (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZP8AAAAASUVORK5CYII="
            )
            result = service.onboard_user(
                name="Casey",
                display_name="Casey Jones",
                pin_code="1358",
                face_photo_data=face_photo_data,
            )

            users_root = runtime_dir / "users"
            user_folders = [path for path in users_root.iterdir() if path.is_dir()]
            self.assertEqual(len(user_folders), 1)
            user_folder = user_folders[0]
            profile = json.loads((user_folder / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["user_id"], result["user"]["user_id"])
            self.assertEqual(profile["pin_code"], "1358")
            self.assertTrue(profile["has_face_photo"])
            self.assertEqual(profile["face_photo_file"], "face_photo.png")
            self.assertEqual((user_folder / "pin_code.txt").read_text(encoding="utf-8").strip(), "1358")
            self.assertTrue((user_folder / "face_photo.png").exists())
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_enter_lobby_restores_last_active_workspace(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test_reentry"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            created = service.onboard_user(name="Grace", pin_code="1357")
            workspace_id = created["workspace_id"]
            second = service.create_session(
                user_id=created["user"]["user_id"],
                title="Return Session",
                description="Return to the project thread.",
                workspace_id=created["workspace_id"],
            )
            service.store.update_user(
                created["user"]["user_id"],
                {
                    "last_active_workspace_id": created["workspace_id"],
                    "last_active_session_id": second["session_id"],
                    "updated_at": "2026-04-17T12:00:00Z",
                },
            )

            restored = service.enter_lobby(pin_code="1357")
            self.assertEqual(restored["workspace_id"], created["workspace_id"])
            self.assertEqual(restored["user"]["last_active_workspace_id"], created["workspace_id"])
            self.assertEqual(restored["session_id"], second["session_id"])
            self.assertEqual(service.resolve_workspace_for_session(restored["session_id"]), created["workspace_id"])
            self.assertTrue((workspaces_dir / workspace_id / "state.json").exists())
            self.assertTrue((workspaces_dir / created["workspace_id"] / "state.json").exists())
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_invalid_pin_rejected(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test_invalid"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            with self.assertRaises(HTTPException):
                service.enter_lobby(pin_code="9999")
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_session_creation_and_activation_updates_last_active_session(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test_sessions"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            created = service.onboard_user(name="Mina", pin_code="1122")
            first_session_id = created["session_id"]
            second = service.create_session(
                user_id=created["user"]["user_id"],
                title="Event Flier",
                description="Design the flier for the fundraiser.",
                workspace_id=created["workspace_id"],
            )

            sessions = service.list_sessions(created["user"]["user_id"])
            self.assertEqual(len(sessions), 2)
            current = next((session for session in sessions if session["session_id"] == second["session_id"]), None)
            self.assertIsNotNone(current)
            self.assertEqual(current["title"], "Event Flier")
            self.assertEqual(current["description"], "Design the flier for the fundraiser.")
            self.assertEqual(service.store.fetch_user(created["user"]["user_id"])["last_active_session_id"], second["session_id"])

            restored = service.select_session_for_user(first_session_id)
            self.assertEqual(restored["session_id"], first_session_id)
            self.assertEqual(service.store.fetch_user(created["user"]["user_id"])["last_active_session_id"], first_session_id)
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_session_activation_restores_session_room(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test_session_room"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            created = service.onboard_user(name="Mina", pin_code="1133")
            first_session_id = created["session_id"]
            workspace_id = created["workspace_id"]
            service.remember_session_room(first_session_id, active_room="sales_department", active_persona="Sales Director")
            second = service.create_session(
                user_id=created["user"]["user_id"],
                title="Second",
                description="Second thread.",
                workspace_id=workspace_id,
            )
            service.remember_session_room(second["session_id"], active_room="it_department", active_persona="IT Administrator")

            service.select_session_for_user(second["session_id"])
            self.assertEqual(kernel.get_state(workspace_id)["active_room"], "it_department")
            service.select_session_for_user(first_session_id)
            self.assertEqual(kernel.get_state(workspace_id)["active_room"], "sales_department")
            self.assertEqual(kernel.get_state(workspace_id)["active_persona"], "Sales Director")
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_activate_workspace_creates_or_restores_session_in_workspace(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_user_service_test_workspace_activate"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-17T12:00:00Z")
            service = UserService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            created = service.onboard_user(name="Ivy", pin_code="7788")
            workspace_id = created["workspace_id"]

            activated = service.activate_workspace(user_id=created["user"]["user_id"], workspace_id=workspace_id)
            self.assertEqual(activated["workspace_id"], workspace_id)
            self.assertEqual(activated["session"]["active_workspace_id"], workspace_id)
            self.assertEqual(service.store.fetch_user(created["user"]["user_id"])["last_active_workspace_id"], workspace_id)
            self.assertEqual(service.store.fetch_user(created["user"]["user_id"])["last_active_session_id"], activated["session"]["session_id"])

            workspaces = service.list_user_workspaces(created["user"]["user_id"])
            self.assertTrue(any(item["workspace_id"] == workspace_id for item in workspaces))
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
