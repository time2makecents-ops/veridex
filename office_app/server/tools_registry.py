from __future__ import annotations

from typing import Callable, Dict, Optional

from office_app.server.command_router import CommandRouter
from office_app.server.tool_definitions import ToolDefinition, VERIDEX_TOOL_DEFINITIONS

ToolHandler = Callable[[dict], dict]


def register_tools(
    router: CommandRouter,
    handlers: Dict[str, ToolHandler],
    definitions: Optional[Dict[str, ToolDefinition]] = None,
) -> None:
    catalog = definitions or VERIDEX_TOOL_DEFINITIONS
    for tool_name, handler in handlers.items():
        router.register(tool_name, handler, definition=catalog.get(tool_name))
