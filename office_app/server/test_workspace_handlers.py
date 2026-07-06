from __future__ import annotations

import unittest
from typing import Any, Dict, List

from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.workspace_handlers import build_workspace_handlers


class FakePipeline:
    def snapshot_response(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "active_room": "sales_department",
                "active_persona": "Sales Director",
            },
            "content": [{"type": "text", "text": "Active room: sales_department | Persona: Sales Director"}],
        }

    def enter_room_response(self, workspace_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "structuredContent": {
                "workspace_id": workspace_id,
                "active_room": result["active_room"],
                "active_persona": result["active_persona"],
            },
            "content": [{"type": "text", "text": f"Active room set to {result['active_room']}."}],
        }


class FakeKernel:
    def enter_room(self, workspace_id: str, room_id: str, session_id: str | None = None) -> Dict[str, Any]:
        return {
            "previous_room": "lobby",
            "active_room": room_id,
            "active_persona": "Marketing Director",
            "active_persona_profile": {},
            "room_title": "Marketing & Advertising",
        }

    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "workspace_id": workspace_id,
            "active_room": "marketing_room",
            "active_persona": "Marketing Director",
            "pending_nancy_email_by_session": {
                "sess_1": {
                    "mode": "compose",
                    "stage": "body",
                    "to": "time2makecents@gmail.com",
                    "subject": "Project update",
                    "body": "",
                    "source": "direct",
                }
            },
            "pending_session_create_by_session": {
                "sess_1": {
                    "request_text": "new session",
                    "ts": "2026-07-03T12:00:00Z",
                }
            },
            "pending_session_rename_by_session": {
                "sess_1": {
                    "request_text": "rename this session",
                    "ts": "2026-07-03T12:00:30Z",
                }
            },
            "pending_session_list_by_session": {
                "sess_1": {
                    "request_text": "what sessions are in this workspace",
                    "ts": "2026-07-03T12:00:45Z",
                }
            },
            "pending_workspace_switch_by_session": {
                "sess_1": {
                    "workspace_id": "ws_switch",
                    "label": "Switch Target",
                    "ts": "2026-07-03T12:02:00Z",
                }
            },
            "pending_room_navigation": {
                "room_id": "marketing_room",
                "room_title": "Marketing & Advertising",
                "persona": "Marketing Director",
                "request_text": "go there",
                "ts": "2026-07-03T12:03:00Z",
            },
            "pending_break_room_jokes": {
                "sess_1": {
                    "setup": "Why did the launch plan cross the room?",
                    "punchline": "Because Sales said Marketing left it on the other side.",
                }
            },
        }


class FakeStore:
    def state_path(self, workspace_id: str) -> str:
        return f"/tmp/{workspace_id}/state.json"

    def save_state(self, workspace_id: str, state: Dict[str, Any]) -> None:
        self.saved_state = dict(state)


class FakeUserService:
    def get_user_for_session(self, session_id: str) -> Dict[str, Any]:
        return {"user_id": "user_1", "session_id": session_id}

    def activate_workspace(self, *, user_id: str, workspace_id: str) -> Dict[str, Any]:
        return {
            "workspace_id": workspace_id,
            "workspace_state": {
                "workspace_id": workspace_id,
                "active_room": "lobby",
                "active_persona": "Receptionist",
                "pending_nancy_email_by_session": {
                    "sess_workspace": {
                        "mode": "compose",
                        "stage": "body",
                        "to": "time2makecents@gmail.com",
                        "subject": "Workspace launch",
                        "body": "",
                        "source": "direct",
                    }
                },
                "pending_session_create_by_session": {
                    "sess_workspace": {
                        "request_text": "new session",
                        "ts": "2026-07-03T12:01:00Z",
                    }
                },
                "pending_session_rename_by_session": {
                    "sess_workspace": {
                        "request_text": "rename this session",
                        "ts": "2026-07-03T12:00:30Z",
                    }
                },
                "pending_session_list_by_session": {
                    "sess_workspace": {
                        "request_text": "what sessions are in this workspace",
                        "ts": "2026-07-03T12:00:45Z",
                    }
                },
                "pending_workspace_switch_by_session": {
                    "sess_workspace": {
                        "workspace_id": "ws_switch",
                        "label": "Switch Target",
                        "ts": "2026-07-03T12:02:00Z",
                    }
                },
                "pending_room_navigation": {
                    "room_id": "marketing_room",
                    "room_title": "Marketing & Advertising",
                    "persona": "Marketing Director",
                    "request_text": "go there",
                    "ts": "2026-07-03T12:03:00Z",
                },
                "pending_break_room_jokes": {
                    "sess_workspace": {
                        "setup": "Why did the launch plan cross the room?",
                        "punchline": "Because Sales said Marketing left it on the other side.",
                    }
                },
            },
            "session": {
                "session_id": "sess_workspace",
                "title": "Workspace Session",
                "description": "Workspace Session",
            },
        }

    def remember_session_room(self, session_id: str | None, *, active_room: str, active_persona: str) -> None:
        self.remembered_room = {
            "session_id": session_id,
            "active_room": active_room,
            "active_persona": active_persona,
        }


class FakeWorkContextService:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def list_contexts(self, workspace_id: str, *, status: str = "active", limit: int = 10) -> List[Dict[str, Any]]:
        self.calls.append({"workspace_id": workspace_id, "status": status, "limit": limit})
        return [
            {
                "context_id": "ctx_manual_1",
                "title": "Finalize launch plan",
                "summary": "Coordinate Sales and Marketing.",
                "status": "active",
                "active_room": "sales_department",
                "active_persona": "Sales Director",
            }
        ]


class WorkspaceHandlerTests(unittest.TestCase):
    def _handlers(self, work_context: FakeWorkContextService) -> Dict[str, Any]:
        return build_workspace_handlers(
            HandlerDeps(
                kernel=FakeKernel(),
                store=FakeStore(),
                pipeline=FakePipeline(),
                archive_service=None,
                memo_service=None,
                nancy_service=None,
                receptionist_context_service=None,
                workspace_file_service=None,
                private_file_service=None,
                search_service=None,
                ocr_service=None,
                model_router=None,
                user_service=FakeUserService(),
                utc_now=lambda: "2026-07-03T12:00:00Z",
                stable_state_sha=lambda state: "sha",
                append_incident=lambda **kwargs: "inc",
                error_missing_required_field=lambda field: ValueError(field),
                resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
                work_context_service=work_context,
            )
        )

    def test_state_get_includes_active_work_context(self) -> None:
        work_context = FakeWorkContextService()
        handlers = self._handlers(work_context)

        response = handlers["office.state_get"]({"workspace_id": "ws_1", "session_id": "sess_1"})

        structured = response["structuredContent"]
        self.assertEqual(work_context.calls, [{"workspace_id": "ws_1", "status": "active", "limit": 8}])
        self.assertEqual(structured["active_work_context"][0]["title"], "Finalize launch plan")
        self.assertEqual(structured["pending_nancy_email_compose"]["stage"], "body")
        self.assertEqual(structured["pending_session_create"]["request_text"], "new session")
        self.assertEqual(structured["pending_session_rename"]["request_text"], "rename this session")
        self.assertEqual(structured["pending_session_list"]["request_text"], "what sessions are in this workspace")
        self.assertEqual(structured["pending_workspace_switch"]["workspace_id"], "ws_switch")
        self.assertEqual(structured["pending_room_navigation"]["room_id"], "marketing_room")
        self.assertEqual(structured["pending_break_room_joke"]["setup"], "Why did the launch plan cross the room?")

    def test_workspace_activate_includes_active_work_context(self) -> None:
        work_context = FakeWorkContextService()
        handlers = self._handlers(work_context)

        response = handlers["office.workspace_activate"]({"workspace_id": "ws_2", "session_id": "sess_1"})

        structured = response["structuredContent"]
        self.assertEqual(work_context.calls, [{"workspace_id": "ws_2", "status": "active", "limit": 8}])
        self.assertEqual(structured["workspace_state"]["active_work_context"][0]["title"], "Finalize launch plan")
        self.assertEqual(structured["workspace_state"]["pending_nancy_email_compose"]["stage"], "body")
        self.assertEqual(structured["workspace_state"]["pending_session_create"]["request_text"], "new session")
        self.assertEqual(structured["workspace_state"]["pending_session_rename"]["request_text"], "rename this session")
        self.assertEqual(structured["workspace_state"]["pending_session_list"]["request_text"], "what sessions are in this workspace")
        self.assertEqual(structured["workspace_state"]["pending_workspace_switch"]["workspace_id"], "ws_switch")
        self.assertEqual(structured["workspace_state"]["pending_room_navigation"]["room_id"], "marketing_room")
        self.assertEqual(structured["workspace_state"]["pending_break_room_joke"]["setup"], "Why did the launch plan cross the room?")

    def test_room_set_includes_active_work_context(self) -> None:
        work_context = FakeWorkContextService()
        handlers = build_workspace_handlers(
            HandlerDeps(
                kernel=FakeKernel(),
                store=FakeStore(),
                pipeline=FakePipeline(),
                archive_service=None,
                memo_service=None,
                nancy_service=None,
                receptionist_context_service=None,
                workspace_file_service=None,
                private_file_service=None,
                search_service=None,
                ocr_service=None,
                model_router=None,
                user_service=FakeUserService(),
                utc_now=lambda: "2026-07-03T12:00:00Z",
                stable_state_sha=lambda state: "sha",
                append_incident=lambda **kwargs: "inc",
                error_missing_required_field=lambda field: ValueError(field),
                resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or ""),
                work_context_service=work_context,
            )
        )

        response = handlers["office.room_set"]({"workspace_id": "ws_1", "session_id": "sess_1", "room_id": "marketing_room"})

        structured = response["structuredContent"]
        self.assertEqual(work_context.calls, [{"workspace_id": "ws_1", "status": "active", "limit": 8}])
        self.assertEqual(structured["active_work_context"][0]["title"], "Finalize launch plan")
        self.assertEqual(structured["pending_nancy_email_compose"]["stage"], "body")
        self.assertEqual(structured["pending_session_create"]["request_text"], "new session")
        self.assertEqual(structured["pending_session_rename"]["request_text"], "rename this session")
        self.assertEqual(structured["pending_session_list"]["request_text"], "what sessions are in this workspace")
        self.assertEqual(structured["pending_workspace_switch"]["workspace_id"], "ws_switch")
        self.assertEqual(structured["pending_room_navigation"]["room_id"], "marketing_room")
        self.assertEqual(structured["pending_break_room_joke"]["setup"], "Why did the launch plan cross the room?")


if __name__ == "__main__":
    unittest.main()
