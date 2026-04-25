from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from office_app.server.receptionist_context_service import ReceptionistContextService
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore


class ReceptionistContextServiceTests(unittest.TestCase):
    def test_context_is_derived_from_session_transcript_only(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_receptionist_context_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            service = ReceptionistContextService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")

            store.append_transcript("ws_test", "user", "lobby", "session alpha first user turn", speaker="You", session_id="sess_alpha")
            store.append_transcript("ws_test", "assistant", "lobby", "session alpha first assistant turn", speaker="Receptionist", session_id="sess_alpha")
            store.append_transcript("ws_test", "user", "lobby", "session beta only turn", speaker="You", session_id="sess_beta")

            model_context = service.build_model_context(
                workspace_id="ws_test",
                session_id="sess_alpha",
            )
            self.assertEqual(model_context["active_room"], "lobby")
            self.assertEqual(model_context["session_id"], "sess_alpha")
            self.assertLessEqual(len(model_context["recent_turns_text"]), 4)
            for item in model_context["recent_turns_text"]:
                self.assertLessEqual(len(item), 340)
            self.assertTrue(any("session alpha first user turn" in item for item in model_context["recent_turns_text"]))
            self.assertFalse(any("session beta only turn" in item for item in model_context["recent_turns_text"]))
            self.assertLessEqual(len(model_context["session_summary_text"]), 600)
            self.assertNotIn("room_directory_text", model_context)
            self.assertNotIn("known_user_profile_text", model_context)
            self.assertNotIn("prompt_state_text", model_context)
            self.assertNotIn("behavior_rules", model_context)

            before = dict(model_context)
            service.record_turn(
                workspace_id="ws_test",
                role="assistant",
                text="this should not become durable receptionist memory",
                room_id="lobby",
                persona_name="Receptionist",
                session_id="sess_alpha",
            )
            after = service.build_model_context(
                workspace_id="ws_test",
                session_id="sess_alpha",
            )
            self.assertEqual(before["session_summary_text"], after["session_summary_text"])
            self.assertEqual(before["recent_turns_text"], after["recent_turns_text"])
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
