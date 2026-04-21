from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from office_app.server.workspace_file_service import WorkspaceFileService
from office_app.server.workspace_kernel import WorkspaceKernel, WorkspaceStore


class WorkspaceFileServiceTests(unittest.TestCase):
    def test_upload_list_and_get(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_workspace_file_test"
        workspaces_dir = runtime_dir / "workspaces"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        workspaces_dir.mkdir(parents=True, exist_ok=True)

        try:
            store = WorkspaceStore(workspaces_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel = WorkspaceKernel(store=store, utc_now_fn=lambda: "2026-04-21T12:00:00Z")
            kernel.create_workspace("ws_test", "Test")
            service = WorkspaceFileService(kernel=kernel, runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-21T12:00:00Z")

            record = service.upload_file(
                workspace_id="ws_test",
                original_name="hello.txt",
                content_text="hello world",
                mime_type="text/plain",
                kind="note",
            )
            self.assertTrue(record["file_id"].startswith("file_"))
            self.assertEqual(record["byte_size"], 11)

            listed = service.list_files("ws_test")
            self.assertEqual(len(listed), 1)

            fetched = service.get_file("ws_test", record["file_id"])
            self.assertEqual(fetched["original_name"], "hello.txt")

            record_meta, raw = service.file_bytes("ws_test", record["file_id"])
            self.assertEqual(record_meta["file_id"], record["file_id"])
            self.assertEqual(raw, b"hello world")
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
