from __future__ import annotations

import unittest
from typing import Any, Dict, List

from office_app.server.handlers.dependencies import HandlerDeps
from office_app.server.handlers.session_handlers import build_session_handlers


class FakeKernel:
    def get_state(self, workspace_id: str) -> Dict[str, Any]:
        return {
            "workspace_id": workspace_id,
            "active_room": "marketing_room",
            "active_persona": "Marketing Director",
            "pending_nancy_email_by_session": {
                "sess_1": {
                    "mode": "compose",
                    "stage": "subject",
                    "to": "time2makecents@gmail.com",
                    "subject": "",
                    "body": "",
                    "source": "direct",
                },
                "sess_workspace": {
                    "mode": "compose",
                    "stage": "body",
                    "to": "time2makecents@gmail.com",
                    "subject": "Workspace launch",
                    "body": "",
                    "source": "direct",
                },
            },
            "pending_session_create_by_session": {
                "sess_1": {
                    "request_text": "new session",
                    "ts": "2026-07-03T12:00:00Z",
                },
                "sess_workspace": {
                    "request_text": "new session",
                    "ts": "2026-07-03T12:01:00Z",
                },
            },
            "pending_session_rename_by_session": {
                "sess_1": {
                    "request_text": "rename this session",
                    "ts": "2026-07-03T12:00:30Z",
                },
                "sess_workspace": {
                    "request_text": "rename this session",
                    "ts": "2026-07-03T12:00:30Z",
                },
            },
            "pending_session_list_by_session": {
                "sess_1": {
                    "request_text": "what sessions are in this workspace",
                    "ts": "2026-07-03T12:00:45Z",
                },
                "sess_workspace": {
                    "request_text": "what sessions are in this workspace",
                    "ts": "2026-07-03T12:00:45Z",
                },
            },
            "pending_workspace_switch_by_session": {
                "sess_1": {
                    "workspace_id": "ws_switch",
                    "label": "Switch Target",
                    "ts": "2026-07-03T12:02:00Z",
                },
                "sess_workspace": {
                    "workspace_id": "ws_switch",
                    "label": "Switch Target",
                    "ts": "2026-07-03T12:02:00Z",
                },
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
                },
                "sess_workspace": {
                    "setup": "Why did the launch plan cross the room?",
                    "punchline": "Because Sales said Marketing left it on the other side.",
                },
            },
        }


class FakeUserService:
    def get_user_for_session(self, session_id: str) -> Dict[str, Any]:
        return {"user_id": "user_1", "session_id": session_id}

    def select_session_for_user(self, session_id: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "active_workspace_id": "ws_1",
            "title": "Launch Thread",
            "description": "Launch Thread",
        }

    def activate_workspace(self, *, user_id: str, workspace_id: str) -> Dict[str, Any]:
        return {
            "workspace_id": workspace_id,
            "workspace_state": {
                "workspace_id": workspace_id,
                "active_room": "sales_department",
                "active_persona": "Sales Director",
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


class FakeWorkContextService:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def list_contexts(self, workspace_id: str, *, status: str = "active", limit: int = 10) -> List[Dict[str, Any]]:
        self.calls.append({"workspace_id": workspace_id, "status": status, "limit": limit})
        return [
            {
                "context_id": "ctx_manual_launch",
                "title": "Launch coordination",
                "summary": "Keep Sales and Marketing aligned.",
                "status": "active",
            }
        ]


class SessionHandlerTests(unittest.TestCase):
    def _handlers(self, work_context: FakeWorkContextService) -> Dict[str, Any]:
        return build_session_handlers(
            HandlerDeps(
                kernel=FakeKernel(),
                store=None,
                pipeline=None,
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
                resolve_workspace_id=lambda tool, args: str(args.get("workspace_id") or "ws_1"),
                work_context_service=work_context,
            )
        )

    def test_session_activate_includes_active_work_context_in_workspace_state(self) -> None:
        work_context = FakeWorkContextService()
        handlers = self._handlers(work_context)

        response = handlers["office.session_activate"]({"session_id": "sess_1"})

        workspace_state = response["structuredContent"]["workspace_state"]
        self.assertEqual(work_context.calls, [{"workspace_id": "ws_1", "status": "active", "limit": 8}])
        self.assertEqual(workspace_state["active_work_context"][0]["title"], "Launch coordination")
        self.assertEqual(workspace_state["pending_nancy_email_compose"]["stage"], "subject")
        self.assertEqual(workspace_state["pending_session_create"]["request_text"], "new session")
        self.assertEqual(workspace_state["pending_session_rename"]["request_text"], "rename this session")
        self.assertEqual(workspace_state["pending_session_list"]["request_text"], "what sessions are in this workspace")
        self.assertEqual(workspace_state["pending_workspace_switch"]["workspace_id"], "ws_switch")
        self.assertEqual(workspace_state["pending_room_navigation"]["room_id"], "marketing_room")
        self.assertEqual(workspace_state["pending_break_room_joke"]["setup"], "Why did the launch plan cross the room?")

    def test_workspace_activate_includes_active_work_context_in_workspace_state(self) -> None:
        work_context = FakeWorkContextService()
        handlers = self._handlers(work_context)

        response = handlers["office.workspace_activate"]({"session_id": "sess_1", "workspace_id": "ws_2"})

        workspace_state = response["structuredContent"]["workspace_state"]
        self.assertEqual(work_context.calls, [{"workspace_id": "ws_2", "status": "active", "limit": 8}])
        self.assertEqual(workspace_state["active_work_context"][0]["title"], "Launch coordination")
        self.assertEqual(workspace_state["pending_nancy_email_compose"]["stage"], "body")
        self.assertEqual(workspace_state["pending_session_create"]["request_text"], "new session")
        self.assertEqual(workspace_state["pending_session_rename"]["request_text"], "rename this session")
        self.assertEqual(workspace_state["pending_session_list"]["request_text"], "what sessions are in this workspace")
        self.assertEqual(workspace_state["pending_workspace_switch"]["workspace_id"], "ws_switch")
        self.assertEqual(workspace_state["pending_room_navigation"]["room_id"], "marketing_room")
        self.assertEqual(workspace_state["pending_break_room_joke"]["setup"], "Why did the launch plan cross the room?")


if __name__ == "__main__":
    unittest.main()
