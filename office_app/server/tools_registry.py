from __future__ import annotations

from typing import Callable, Dict

from office_app.server.command_router import CommandRouter

ToolHandler = Callable[[dict], dict]


def register_tools(router: CommandRouter, handlers: Dict[str, ToolHandler]) -> None:
    for tool_name, handler in handlers.items():
        router.register(tool_name, handler)
