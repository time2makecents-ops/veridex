from __future__ import annotations

from typing import Any, Dict, List


class NancyService:
    def __init__(self, *, kernel, archive_service, store, utc_now_fn):
        self.kernel = kernel
        self.archive_service = archive_service
        self.store = store
        self.utc_now = utc_now_fn

    def _workspace_ids(self, workspace_id: str) -> List[str]:
        idx = self.kernel.list_workspaces()
        workspace_ids: List[str] = []
        for row in idx.get("workspaces", []):
            candidate = str(row.get("workspace_id") or "").strip()
            if candidate and candidate not in workspace_ids:
                workspace_ids.append(candidate)
        if workspace_id and workspace_id not in workspace_ids:
            workspace_ids.insert(0, workspace_id)
        return workspace_ids

    def _artifact_rows(self, workspace_id: str, retrieval_scope: str = "workspace") -> List[Dict[str, Any]]:
        if retrieval_scope == "archive_global":
            rows = self.archive_service.list_artifacts_across_workspaces(self._workspace_ids(workspace_id), include_archived=True)
        else:
            rows = self.archive_service.list_artifacts(workspace_id)
        return sorted(rows, key=lambda r: r.get("updated_at") or r.get("created_at", ""), reverse=True)

    def artifacts_list_response(self, workspace_id: str, retrieval_scope: str = "workspace") -> Dict[str, Any]:
        state = self.kernel.get_state(workspace_id)
        rows = self._artifact_rows(workspace_id, retrieval_scope=retrieval_scope)

        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "retrieval_scope": retrieval_scope,
                "nancy_mode": "overlay" if state.get("active_room") != "my_office" else "active_room_persona",
                "count": len(rows),
                "artifacts": rows,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Nancy found {len(rows)} artifact(s) "
                        f"({'all workspaces' if retrieval_scope == 'archive_global' else 'this workspace'})."
                    ),
                }
            ],
        }

    def artifact_open_response(self, workspace_id: str, artifact_id: str, retrieval_scope: str = "workspace") -> Dict[str, Any]:
        state = self.kernel.get_state(workspace_id)
        if retrieval_scope == "archive_global":
            obj = self.archive_service.get_artifact_across_workspaces(self._workspace_ids(workspace_id), artifact_id)
        else:
            obj = self.archive_service.get_artifact(workspace_id, artifact_id)

        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "retrieval_scope": retrieval_scope,
                "nancy_mode": "overlay" if state.get("active_room") != "my_office" else "active_room_persona",
                "artifact": obj,
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Nancy opened {obj.get('display_name') or obj.get('title')} ({obj['artifact_id']}).\n\n"
                        f"{obj.get('content_preview', '')}"
                    ),
                }
            ],
        }

    def workspace_briefing_response(self, workspace_id: str) -> Dict[str, Any]:
        state = self.kernel.get_state(workspace_id)
        rows = self._artifact_rows(workspace_id)
        idx = self.kernel.list_workspaces()

        label = workspace_id
        for row in idx.get("workspaces", []):
            if row.get("workspace_id") == workspace_id:
                label = row.get("label") or workspace_id
                break

        briefing = {
            "workspace_id": workspace_id,
            "workspace_label": label,
            "active_room": state.get("active_room", "lobby"),
            "active_persona": state.get("active_persona", "Receptionist"),
            "nancy_mode": "overlay" if state.get("active_room") != "my_office" else "active_room_persona",
            "artifact_count": len(rows),
            "latest_artifact": rows[0] if rows else None,
            "timestamp_utc": self.utc_now(),
        }

        latest_text = "No artifacts stored yet."
        if briefing["latest_artifact"]:
            latest = briefing["latest_artifact"]
            latest_text = f"Latest artifact: {latest.get('display_name') or latest.get('title')} ({latest['artifact_id']})"

        text = (
            f"Nancy briefing for {label}\n"
            f"Active room: {briefing['active_room']}\n"
            f"Active persona: {briefing['active_persona']}\n"
            f"Artifacts: {briefing['artifact_count']}\n"
            f"{latest_text}"
        )

        return {
            "structuredContent": briefing,
            "content": [{"type": "text", "text": text}],
        }
