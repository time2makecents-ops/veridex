from __future__ import annotations

from pathlib import Path

from office_app.server.artifact_service import ArtifactService


class ArchiveService(ArtifactService):
    def __init__(self, workspaces_dir: Path, utc_now_fn):
        runtime_dir = Path(workspaces_dir).parent
        super().__init__(runtime_dir=runtime_dir, utc_now_fn=utc_now_fn)
        self.workspaces_dir = Path(workspaces_dir)

    def artifacts_dir(self, workspace_id: str) -> Path:
        path = self.workspaces_dir / workspace_id / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path
