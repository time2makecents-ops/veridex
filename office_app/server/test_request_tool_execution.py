from __future__ import annotations

import unittest

from office_app.server.request_tool_execution import execute_tool_route


class FakeKernel:
    def __init__(self, state=None) -> None:
        self.state = state or {
            "active_room": "lobby",
            "active_persona": "Receptionist",
        }

    def get_state(self, workspace_id: str):
        return self.state


class CapturingStore:
    def __init__(self) -> None:
        self.saved = []
        self.transcript = []

    def save_state(self, workspace_id: str, state: dict) -> None:
        self.saved.append({"workspace_id": workspace_id, "state": state})

    def append_transcript(self, workspace_id: str, role: str, room_id: str, text: str, **kwargs) -> None:
        self.transcript.append(
            {
                "workspace_id": workspace_id,
                "role": role,
                "room_id": room_id,
                "text": text,
                **kwargs,
            }
        )


class CapturingRouter:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls = []

    def dispatch_capability(self, capability: str, args: dict, preferred_tool: str | None = None):
        self.calls.append(
            {
                "capability": capability,
                "args": args,
                "preferred_tool": preferred_tool,
            }
        )
        return self.result


class CapturingReceptionistContextService:
    def __init__(self) -> None:
        self.turns = []

    def record_turn(self, **kwargs) -> None:
        self.turns.append(kwargs)


def apply_navigator_activation(response: dict, **kwargs) -> dict:
    enriched = dict(response)
    structured = dict(enriched.get("structuredContent") or {})
    structured["navigator_activation"] = {
        "activated": True,
        "capability": kwargs.get("capability"),
        "reason": kwargs.get("reason"),
    }
    enriched["structuredContent"] = structured
    return enriched


def response_speaker(response: dict) -> str | None:
    structured = response.get("structuredContent")
    if not isinstance(structured, dict):
        return None
    routing = structured.get("routing")
    if isinstance(routing, dict) and str(routing.get("route_kind") or "").strip().lower() == "clarify":
        return "Navigator"
    return str(structured.get("speaker") or "").strip() or None


def set_pending_workspace_switch(state: dict, session_id: str, workspace_id: str, label: str) -> dict:
    pending = dict(state.get("pending_workspace_switch_by_session") or {})
    pending[session_id] = {
        "workspace_id": workspace_id,
        "label": label,
        "ts": "2026-06-30T00:00:00Z",
    }
    state["pending_workspace_switch_by_session"] = pending
    return state


class RequestToolExecutionTests(unittest.TestCase):
    def test_execute_tool_route_records_clarify_response_with_navigator_speaker(self) -> None:
        kernel = FakeKernel()
        store = CapturingStore()
        receptionist_context_service = CapturingReceptionistContextService()
        router = CapturingRouter(
            {
                "structuredContent": {
                    "response_text": "Need a title first.",
                    "routing": {
                        "route_kind": "clarify",
                        "capability": "conference_room.agenda.title_required",
                        "tool": "office.capability_info",
                    },
                },
                "content": [{"type": "text", "text": "Need a title first."}],
            }
        )

        result = execute_tool_route(
            routed={
                "capability": "artifact.create",
                "tool": "office.artifact_create",
                "reason": "Create agenda artifact.",
                "arguments": {"title": ""},
            },
            workspace_id="ws_test",
            session_id="sess_test",
            user_profile=None,
            kernel=kernel,
            store=store,
            router=router,
            receptionist_context_service=receptionist_context_service,
            utc_now=lambda: "2026-06-30T00:00:00Z",
            apply_navigator_activation=apply_navigator_activation,
            set_pending_workspace_switch=set_pending_workspace_switch,
            response_speaker=response_speaker,
        )

        self.assertEqual(result["structuredContent"]["routing"]["route_kind"], "clarify")
        self.assertEqual(store.transcript[0]["speaker"], "Navigator")

    def test_execute_tool_route_wraps_workspace_create_in_switch_confirmation(self) -> None:
        kernel = FakeKernel()
        store = CapturingStore()
        receptionist_context_service = CapturingReceptionistContextService()
        router = CapturingRouter(
            {
                "structuredContent": {
                    "workspace_id": "ws_new",
                    "label": "Launch",
                    "response_text": "Created workspace Launch.",
                },
                "content": [{"type": "text", "text": "Created workspace Launch."}],
            }
        )

        result = execute_tool_route(
            routed={
                "capability": "workspace.create",
                "tool": "office.workspace_new",
                "reason": "Create workspace.",
                "arguments": {"title": "Launch"},
            },
            workspace_id="ws_current",
            session_id="sess_test",
            user_profile=None,
            kernel=kernel,
            store=store,
            router=router,
            receptionist_context_service=receptionist_context_service,
            utc_now=lambda: "2026-06-30T00:00:00Z",
            apply_navigator_activation=apply_navigator_activation,
            set_pending_workspace_switch=set_pending_workspace_switch,
            response_speaker=response_speaker,
        )

        structured = result["structuredContent"]
        self.assertEqual(structured["workspace_id"], "ws_current")
        self.assertEqual(structured["created_workspace_id"], "ws_new")
        self.assertEqual(structured["pending_workspace_switch"]["workspace_id"], "ws_new")
        self.assertEqual(structured["routing"]["capability"], "workspace.switch.confirmation")
        self.assertEqual(
            store.saved[0]["state"]["pending_workspace_switch_by_session"]["sess_test"]["workspace_id"],
            "ws_new",
        )


if __name__ == "__main__":
    unittest.main()
