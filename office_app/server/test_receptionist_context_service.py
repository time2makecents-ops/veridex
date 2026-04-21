from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from office_app.server.receptionist_context_service import ReceptionistContextService
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore


class ReceptionistContextServiceTests(unittest.TestCase):
    def test_context_defaults_and_turns(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_receptionist_context_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            service = ReceptionistContextService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")

            context = service.get_context("ws_test")
            self.assertGreater(len(context["room_directory"]), 0)
            self.assertGreater(len(context["persona_directory"]), 0)
            self.assertIn("greeting", context["receptionist_script"])

            service.record_turn(
                workspace_id="ws_test",
                role="user",
                text="how many rooms are here?",
                room_id="lobby",
                persona_name="Receptionist",
                session_id="sess_test",
            )
            updated = service.get_context("ws_test")
            self.assertEqual(len(updated["recent_turns"]), 1)
            self.assertIn("Latest user request", updated["session_summary_text"])

            model_context = service.build_model_context(
                workspace_id="ws_test",
                user_profile={"display_name": "Mira", "user_id": "usr_123"},
                session_id="sess_test",
            )
            self.assertEqual(model_context["active_room"], "lobby")
            self.assertIn("Lobby", model_context["room_directory_text"])
            self.assertIn("display_name: Mira", model_context["known_user_profile_text"])
            self.assertEqual(model_context["session_id"], "sess_test")
            self.assertNotIn("persona_directory", model_context)
            self.assertNotIn("file_tools", model_context)
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
