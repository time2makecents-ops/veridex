from __future__ import annotations

from typing import Any, Callable, Dict

from office_app.server.errors import error_unknown_tool

ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: Dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        self._handlers[tool_name] = handler

    def tool_names(self) -> list[str]:
        return sorted(self._handlers.keys())

    def dispatch(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise error_unknown_tool(tool_name)
        return handler(args)
