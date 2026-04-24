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


if __name__ == "__main__":
    unittest.main()
