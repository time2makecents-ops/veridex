from __future__ import annotations

import unittest

from fastapi import HTTPException

from office_app.server.tool_context import ToolContext
from office_app.server.tool_definitions import tool_definition
from office_app.server.tool_router import ToolRouter


class ToolRouterTests(unittest.TestCase):
    def test_dispatches_by_capability(self) -> None:
        router = ToolRouter(
            context_provider=lambda tool_name, args, definition: ToolContext(
                tool_name=tool_name,
                capability=definition.capability,
                workspace_id=str(args.get("workspace_id") or ""),
                active_room="lobby",
                active_persona="Receptionist",
                arguments=dict(args),
            )
        )
        router.register(
            "office.file_upload",
            lambda args: {"ok": True, "received": args["name"]},
            definition=tool_definition("office.file_upload", "file.upload", requires_workspace=True),
        )

        result = router.dispatch_capability("file.upload", {"workspace_id": "ws_test", "name": "memo.txt"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["received"], "memo.txt")

    def test_policy_blocks_room_when_definition_disallows_it(self) -> None:
        router = ToolRouter(
            context_provider=lambda tool_name, args, definition: ToolContext(
                tool_name=tool_name,
                capability=definition.capability,
                workspace_id="ws_test",
                active_room="lobby",
                active_persona="Receptionist",
                arguments=dict(args),
            )
        )
        router.register(
            "office.internal_security_check",
            lambda args: {"ok": True},
            definition=tool_definition(
                "office.internal_security_check",
                "security.audit",
                requires_workspace=True,
                allowed_rooms=("security_room",),
            ),
        )

        with self.assertRaises(HTTPException):
            router.dispatch("office.internal_security_check", {"workspace_id": "ws_test"})


if __name__ == "__main__":
    unittest.main()
