from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from office_app.server.artifact_service import ArtifactService


class ArtifactServiceTests(unittest.TestCase):
    def test_crud_flow(self) -> None:
        runtime_dir = Path.cwd() / "office_app" / "runtime" / "_artifact_service_test"
        shutil.rmtree(runtime_dir, ignore_errors=True)
        runtime_dir.mkdir(parents=True, exist_ok=True)

        try:
            service = ArtifactService(runtime_dir=runtime_dir, utc_now_fn=lambda: "2026-04-17T12:00:00Z")

            created = service.create_artifact(
                workspace_id="ws_test",
                type="document",
                title="Alpha",
                content="hello",
                created_by="user",
                metadata={"priority": "high"},
                source_refs=[{"kind": "request", "id": "req_1"}],
            )
            self.assertEqual(created["artifact_id"][:4], "art_")
            self.assertEqual(created["version"], 1)
            self.assertFalse(created["archived"])
            self.assertEqual(created["metadata"]["priority"], "high")
            self.assertTrue((runtime_dir / "veridex.db").exists())

            fetched = service.get_artifact("ws_test", created["artifact_id"])
            self.assertEqual(fetched["title"], "Alpha")
            self.assertEqual(fetched["content"], "hello")

            listed = service.list_artifacts("ws_test")
            self.assertEqual(len(listed), 1)

            updated = service.update_artifact(
                workspace_id="ws_test",
                artifact_id=created["artifact_id"],
                title="Alpha v2",
                metadata={"owner": "team-a"},
            )
            self.assertEqual(updated["version"], 2)
            self.assertEqual(updated["title"], "Alpha v2")
            self.assertEqual(updated["metadata"]["priority"], "high")
            self.assertEqual(updated["metadata"]["owner"], "team-a")

            appended = service.append_to_artifact(
                workspace_id="ws_test",
                artifact_id=created["artifact_id"],
                content="world",
            )
            self.assertEqual(appended["version"], 3)
            self.assertIn("world", appended["content"])

            archived = service.archive_artifact(
                workspace_id="ws_test",
                artifact_id=created["artifact_id"],
            )
            self.assertTrue(archived["archived"])
            self.assertEqual(archived["status"], "archived")
            self.assertEqual(archived["version"], 4)

            active_only = service.list_artifacts("ws_test")
            self.assertEqual(active_only, [])

            with_archived = service.list_artifacts("ws_test", include_archived=True)
            self.assertEqual(len(with_archived), 1)
            self.assertTrue(with_archived[0]["archived"])

            other = service.create_artifact(
                workspace_id="ws_other",
                type="document",
                title="Beta",
                content="other workspace",
                created_by="system",
            )

            global_rows = service.list_artifacts_across_workspaces(["ws_test", "ws_other"], include_archived=True)
            self.assertEqual(len(global_rows), 2)
            self.assertEqual({row["workspace_id"] for row in global_rows}, {"ws_test", "ws_other"})

            global_fetched = service.get_artifact_across_workspaces(["ws_test", "ws_other"], other["artifact_id"])
            self.assertEqual(global_fetched["workspace_id"], "ws_other")
            self.assertEqual(global_fetched["title"], "Beta")
        finally:
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
