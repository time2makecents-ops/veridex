from __future__ import annotations

import unittest

import office_app.server.app as app_module


class CallToolSessionContextTests(unittest.TestCase):
    def test_call_tool_forwards_session_header_to_tool_arguments(self) -> None:
        original_router = app_module.router

        class CapturingRouter:
            def __init__(self) -> None:
                self.tool = ""
                self.args = {}

            def dispatch(self, tool, args):
                self.tool = tool
                self.args = args
                return {"structuredContent": args, "content": []}

        fake_router = CapturingRouter()
        app_module.router = fake_router
        try:
            app_module.call_tool(
                app_module.ToolCall(
                    tool="office.room_set",
                    arguments={"workspace_id": "ws_test", "room_id": "sales_department"},
                ),
                x_session_id="sess_test",
            )
        finally:
            app_module.router = original_router

        self.assertEqual(fake_router.tool, "office.room_set")
        self.assertEqual(fake_router.args["workspace_id"], "ws_test")
        self.assertEqual(fake_router.args["room_id"], "sales_department")
        self.assertEqual(fake_router.args["session_id"], "sess_test")


if __name__ == "__main__":
    unittest.main()
