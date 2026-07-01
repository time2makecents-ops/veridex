from __future__ import annotations

import unittest
from pathlib import Path
import shutil

from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore


class WorkspaceKernelTranscriptTests(unittest.TestCase):
    def test_loads_recent_transcript_entries(self) -> None:
        tmp = Path("C:/Office-App/office_app/runtime/test_workspace_kernel")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            store = WorkspaceStore(tmp, utc_now_fn=lambda: "2026-04-24T00:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-24T00:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            store.append_transcript("ws_test", "user", "lobby", "hello", speaker="You")
            store.append_transcript("ws_test", "assistant", "lobby", "hi there", speaker="Receptionist")

            rows = store.load_transcript("ws_test", limit=2)

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["text"], "hello")
            self.assertEqual(rows[0]["speaker"], "You")
            self.assertEqual(rows[1]["text"], "hi there")
            self.assertEqual(rows[1]["speaker"], "Receptionist")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_session_transcripts_are_isolated_from_workspace_transcript(self) -> None:
        tmp = Path("C:/Office-App/office_app/runtime/test_workspace_kernel_sessions")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            store = WorkspaceStore(tmp, utc_now_fn=lambda: "2026-04-24T00:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-24T00:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            store.append_transcript("ws_test", "user", "lobby", "workspace hello", speaker="You")
            store.append_transcript("ws_test", "user", "lobby", "session hello", speaker="You", session_id="sess_alpha")

            workspace_rows = store.load_transcript("ws_test", limit=10)
            session_rows = store.load_transcript("ws_test", limit=10, session_id="sess_alpha")

            self.assertEqual(len(workspace_rows), 2)
            self.assertEqual(workspace_rows[-1]["text"], "workspace hello")
            self.assertEqual(len(session_rows), 1)
            self.assertEqual(session_rows[0]["text"], "session hello")
            self.assertEqual(session_rows[0]["session_id"], "sess_alpha")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_load_transcript_preserves_multiline_assistant_text(self) -> None:
        tmp = Path("C:/Office-App/office_app/runtime/test_workspace_kernel_multiline")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            store = WorkspaceStore(tmp, utc_now_fn=lambda: "2026-04-24T00:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-24T00:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            text = "First paragraph.\n\nSecond paragraph."
            store.append_transcript("ws_test", "assistant", "lobby", text, speaker="Receptionist", session_id="sess_alpha")

            rows = store.load_transcript("ws_test", limit=10, session_id="sess_alpha")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
