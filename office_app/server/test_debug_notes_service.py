from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from office_app.server.debug_notes_service import DebugNotesStore
import office_app.server.app as app_module


class DebugNotesStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_dir = Path.cwd() / "office_app" / "runtime" / "_debug_notes_test"
        shutil.rmtree(self.runtime_dir, ignore_errors=True)
        self.store = DebugNotesStore(runtime_dir=self.runtime_dir, utc_now_fn=lambda: "2026-07-01T12:00:00Z")

    def tearDown(self) -> None:
        shutil.rmtree(self.runtime_dir, ignore_errors=True)

    def test_missing_note_returns_empty_record_for_normalized_page(self) -> None:
        record = self.store.get_note("chat")

        self.assertEqual(record["page_path"], "/chat")
        self.assertEqual(record["text"], "")
        self.assertEqual(record["updated_at"], "")

    def test_saves_and_reads_page_note_without_cross_page_leakage(self) -> None:
        saved = self.store.save_note(
            page_path="/chat",
            text="Login button disappears after restart.",
            session_id="sess_123",
            workspace_id="ws_123",
            active_room="control_room",
            active_persona="Navigator",
        )

        self.assertEqual(saved["page_path"], "/chat")
        self.assertEqual(saved["text"], "Login button disappears after restart.")
        self.assertEqual(saved["session_id"], "sess_123")
        self.assertEqual(saved["workspace_id"], "ws_123")
        self.assertEqual(saved["active_room"], "control_room")
        self.assertEqual(saved["active_persona"], "Navigator")
        self.assertEqual(saved["updated_at"], "2026-07-01T12:00:00Z")
        self.assertEqual(
            self.store.get_note("/chat", active_room="control_room", active_persona="Navigator")["text"],
            "Login button disappears after restart.",
        )
        self.assertEqual(self.store.get_note("/admin")["text"], "")

    def test_chat_notes_are_separate_by_room_and_persona(self) -> None:
        self.store.save_note(
            page_path="/chat",
            text="lobby note",
            active_room="lobby",
            active_persona="Receptionist",
        )
        self.store.save_note(
            page_path="/chat",
            text="conference note",
            active_room="conference_room",
            active_persona="Facilitator",
        )

        lobby = self.store.get_note("/chat", active_room="lobby", active_persona="Receptionist")
        conference = self.store.get_note("/chat", active_room="conference_room", active_persona="Facilitator")

        self.assertEqual(lobby["text"], "lobby note")
        self.assertEqual(lobby["note_scope"], "room_persona")
        self.assertEqual(conference["text"], "conference note")
        self.assertEqual(conference["note_key"], "/chat|conference_room|Facilitator")

    def test_non_chat_pages_ignore_room_for_page_scoped_notes(self) -> None:
        self.store.save_note(page_path="/profile", text="profile note", active_room="lobby", active_persona="Receptionist")

        record = self.store.get_note("/profile", active_room="conference_room", active_persona="Facilitator")

        self.assertEqual(record["text"], "profile note")
        self.assertEqual(record["note_scope"], "page")
        self.assertEqual(record["note_key"], "/profile")

    def test_legacy_chat_note_is_recovered_for_matching_room(self) -> None:
        self.store.notes_path.parent.mkdir(parents=True, exist_ok=True)
        self.store.notes_path.write_text(
            '{"notes": {"/chat": {"page_path": "/chat", "text": "old conference note", "active_room": "conference_room", "updated_at": "old"}}}',
            encoding="utf-8",
        )

        record = self.store.get_note("/chat", active_room="conference_room", active_persona="Facilitator")

        self.assertEqual(record["text"], "old conference note")
        self.assertEqual(record["note_key"], "/chat|conference_room|Facilitator")
        self.assertIn("/chat|conference_room|Facilitator", self.store.notes_path.read_text(encoding="utf-8"))

    def test_normalizes_malformed_page_path_to_safe_key(self) -> None:
        saved = self.store.save_note(page_path="///admin/users?tab=all#top", text="check users")

        self.assertEqual(saved["page_path"], "/admin/users")
        self.assertIn("/admin/users", self.store.notes_path.read_text(encoding="utf-8"))

    def test_app_endpoints_use_debug_notes_store(self) -> None:
        original_store = app_module.debug_notes_store
        app_module.debug_notes_store = self.store
        try:
            saved = app_module.put_debug_note(
                app_module.DebugNoteUpdateRequest(
                    page_path="/profile",
                    text="profile redirect loops after login",
                    session_id="sess_profile",
                    workspace_id="ws_profile",
                    active_room="lobby",
                    active_persona="Receptionist",
                )
            )
            loaded = app_module.get_debug_note("/profile", active_room="conference_room", active_persona="Facilitator")
        finally:
            app_module.debug_notes_store = original_store

        self.assertEqual(saved["structuredContent"]["text"], "profile redirect loops after login")
        self.assertEqual(loaded["structuredContent"]["session_id"], "sess_profile")


if __name__ == "__main__":
    unittest.main()
