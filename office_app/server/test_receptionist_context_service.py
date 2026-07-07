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
            store.append_transcript("ws_test", "user", "sales_department", "save that i am located in Oregon.", speaker="You", session_id="sess_alpha")
            store.append_transcript("ws_test", "assistant", "sales_department", "I've saved that you're located in Oregon.", speaker="Sales Director", session_id="sess_alpha")
            for index in range(2, 6):
                store.append_transcript("ws_test", "user", "sales_department", f"session alpha user turn {index}", speaker="You", session_id="sess_alpha")
                store.append_transcript("ws_test", "assistant", "sales_department", f"session alpha assistant turn {index}", speaker="Sales Director", session_id="sess_alpha")

            model_context = service.build_model_context(
                workspace_id="ws_test",
                session_id="sess_alpha",
            )
            self.assertEqual(model_context["active_room"], "lobby")
            self.assertEqual(model_context["session_id"], "sess_alpha")
            self.assertLessEqual(len(model_context["recent_turns_text"]), 12)
            for item in model_context["recent_turns_text"]:
                self.assertLessEqual(len(item), 760)
            self.assertTrue(any("session alpha first user turn" in item for item in model_context["recent_turns_text"]))
            self.assertFalse(any("session beta only turn" in item for item in model_context["recent_turns_text"]))
            self.assertIn("conversation_history_text", model_context)
            self.assertIn("session alpha first user turn", model_context["conversation_history_text"])
            self.assertIn("session alpha assistant turn 5", model_context["conversation_history_text"])
            self.assertNotIn("session beta only turn", model_context["conversation_history_text"])
            self.assertIn("session_facts_text", model_context)
            self.assertIn("User lives in Oregon.", model_context["session_facts_text"])
            self.assertLessEqual(len(model_context["session_summary_text"]), 1400)
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

    def test_room_behavior_memory_refs_are_scoped_to_active_room(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_receptionist_context_memory_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            service = ReceptionistContextService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")

            service.remember_room_behavior_ref(
                workspace_id="ws_test",
                room_id="sales_department",
                artifact_id="art_oregon",
                artifact_workspace_id="ws_test",
                preview="Sales questions pertain to Oregon businesses.",
            )

            kernel.enter_room("ws_test", "sales_department")
            sales_context = service.build_model_context(workspace_id="ws_test", session_id="sess_alpha")
            self.assertEqual(sales_context["active_room"], "sales_department")
            self.assertEqual(sales_context["room_behavior_memory_refs"][0]["artifact_id"], "art_oregon")
            self.assertIn("Oregon businesses", sales_context["room_behavior_memory_refs"][0]["preview"])

            kernel.enter_room("ws_test", "marketing_room")
            marketing_context = service.build_model_context(workspace_id="ws_test", session_id="sess_alpha")
            self.assertEqual(marketing_context["active_room"], "marketing_room")
            self.assertEqual(marketing_context["room_behavior_memory_refs"], [])

            removed = service.forget_room_behavior_refs(
                workspace_id="ws_test",
                room_id="sales_department",
                match_text="Oregon",
            )
            self.assertEqual(removed["removed_count"], 1)
            self.assertEqual(service.room_behavior_memory_refs(workspace_id="ws_test", room_id="sales_department"), [])

            service.remember_room_behavior_ref(
                workspace_id="ws_test",
                room_id="sales_department",
                artifact_id="art_carnegie",
                artifact_workspace_id="ws_test",
                preview="Answer my sales questions from now on with the book How to Win Friends and Influence People in mind.",
            )
            service.remember_persona_behavior_ref(
                workspace_id="ws_test",
                room_id="sales_department",
                persona_name="Sales Director",
                artifact_id="art_persona",
                artifact_workspace_id="ws_test",
                preview="Use a friendly, empathetic sales style.",
            )
            removed_current = service.forget_room_behavior_refs(
                workspace_id="ws_test",
                room_id="sales_department",
                match_text="using how to win friends and influence people",
            )
            self.assertEqual(removed_current["removed_count"], 1)
            self.assertEqual(service.room_behavior_memory_refs(workspace_id="ws_test", room_id="sales_department"), [])
            persona_refs = service.persona_behavior_memory_refs(
                workspace_id="ws_test",
                room_id="sales_department",
                persona_name="Sales Director",
            )
            self.assertEqual(len(persona_refs), 1)
            self.assertEqual(persona_refs[0]["artifact_id"], "art_persona")

            service.remember_room_behavior_ref(
                workspace_id="ws_test",
                room_id="sales_department",
                artifact_id="art_first",
                artifact_workspace_id="ws_test",
                preview="First memory.",
            )
            service.remember_room_behavior_ref(
                workspace_id="ws_test",
                room_id="sales_department",
                artifact_id="art_second",
                artifact_workspace_id="ws_test",
                preview="Second memory.",
            )
            removed_by_index = service.forget_room_behavior_refs(
                workspace_id="ws_test",
                room_id="sales_department",
                memory_index=1,
            )
            remaining = service.room_behavior_memory_refs(workspace_id="ws_test", room_id="sales_department")
            self.assertEqual(removed_by_index["removed_count"], 1)
            self.assertEqual(removed_by_index["removed_refs"][0]["artifact_id"], "art_first")
            self.assertEqual(remaining[0]["artifact_id"], "art_second")
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_session_fact_extraction_does_not_bleed_across_numbered_lists(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_receptionist_context_fact_bleed_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            service = ReceptionistContextService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")

            store.append_transcript(
                "ws_test",
                "assistant",
                "sales_department",
                (
                    "Found 4 artifact(s) (this workspace).\n"
                    "1. room_behavior_memory: Sales Department behavior memory (art_1) - i am in oregon\n"
                    "2. room_behavior_memory: Sales Department behavior memory (art_2) - i am in oregon\n"
                    "3. room_behavior_memory: Sales Department behavior memory (art_3) - use the book 48 laws of power when giving me advice"
                ),
                speaker="Sales Director",
                session_id="sess_alpha",
            )
            context = service.build_model_context(workspace_id="ws_test", session_id="sess_alpha")
            facts_text = context["session_facts_text"]
            self.assertIn("User lives in Oregon.", facts_text)
            self.assertNotIn("Oregon 2", facts_text)
            self.assertNotIn("Oregon 3", facts_text)
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)

    def test_diagnostic_turns_are_hidden_from_non_control_room_model_context(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_receptionist_context_diagnostics_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            service = ReceptionistContextService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")

            store.append_transcript(
                "ws_test",
                "assistant",
                "control_room",
                "Navigator found 2 known diagnostic category incidents. Run recent errors for details.",
                speaker="Navigator",
                session_id="sess_alpha",
            )
            store.append_transcript(
                "ws_test",
                "user",
                "art_department",
                "what is an important part of visual marketing?",
                speaker="You",
                session_id="sess_alpha",
            )
            store.append_transcript(
                "ws_test",
                "assistant",
                "art_department",
                "A clear visual hierarchy helps people understand the offer quickly.",
                speaker="Creative Director",
                session_id="sess_alpha",
            )

            kernel.enter_room("ws_test", "art_department")
            art_context = service.build_model_context(workspace_id="ws_test", session_id="sess_alpha")
            self.assertNotIn("known diagnostic category", art_context["conversation_history_text"])
            self.assertNotIn("Run recent errors", art_context["session_summary_text"])
            self.assertFalse(any("Navigator found" in item for item in art_context["recent_turns_text"]))
            self.assertTrue(any("visual marketing" in item for item in art_context["recent_turns_text"]))

            kernel.enter_room("ws_test", "control_room")
            control_context = service.build_model_context(workspace_id="ws_test", session_id="sess_alpha")
            self.assertIn("known diagnostic category", control_context["conversation_history_text"])
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
