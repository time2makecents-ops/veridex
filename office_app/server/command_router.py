from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from office_app.server.tool_definitions import ToolDefinition
from office_app.server.tool_policies import ToolPolicyEngine
from office_app.server.tool_router import ToolRouter

ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


class CommandRouter:
    def __init__(self, *, context_provider=None, policy_engine: Optional[ToolPolicyEngine] = None) -> None:
        self._router = ToolRouter(context_provider=context_provider, policy_engine=policy_engine)

    def register(self, tool_name: str, handler: ToolHandler, definition: Optional[ToolDefinition] = None) -> None:
        self._router.register(tool_name, handler, definition=definition)

    def tool_names(self) -> list[str]:
        return self._router.tool_names()

    def definitions(self) -> list[ToolDefinition]:
        return self._router.definitions()

    def dispatch(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._router.dispatch(tool_name, args)

    def dispatch_capability(self, capability: str, args: Dict[str, Any], *, preferred_tool: Optional[str] = None) -> Dict[str, Any]:
        return self._router.dispatch_capability(capability, args, preferred_tool=preferred_tool)
