from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from office_app.server.errors import error_unknown_capability, error_unknown_tool
from office_app.server.tool_context import ToolContext
from office_app.server.tool_definitions import ToolDefinition, tool_definition
from office_app.server.tool_policies import ToolPolicyEngine

ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]
ToolContextProvider = Callable[[str, Dict[str, Any], ToolDefinition], ToolContext]


class ToolRouter:
    def __init__(
        self,
        *,
        context_provider: Optional[ToolContextProvider] = None,
        policy_engine: Optional[ToolPolicyEngine] = None,
    ) -> None:
        self._handlers: Dict[str, ToolHandler] = {}
        self._definitions: Dict[str, ToolDefinition] = {}
        self._context_provider = context_provider
        self._policy_engine = policy_engine or ToolPolicyEngine()

    def register(self, tool_name: str, handler: ToolHandler, definition: Optional[ToolDefinition] = None) -> None:
        self._handlers[tool_name] = handler
        self._definitions[tool_name] = definition or tool_definition(tool_name, tool_name)

    def tool_names(self) -> list[str]:
        return sorted(self._handlers.keys())

    def definitions(self) -> list[ToolDefinition]:
        return [self._definitions[name] for name in self.tool_names()]

    def definition_for_tool(self, tool_name: str) -> ToolDefinition:
        definition = self._definitions.get(tool_name)
        if definition is None:
            raise error_unknown_tool(tool_name)
        return definition

    def _build_context(self, tool_name: str, args: Dict[str, Any], definition: ToolDefinition) -> ToolContext:
        if self._context_provider is None:
            return ToolContext(
                tool_name=tool_name,
                capability=definition.capability,
                workspace_id=str(args.get("workspace_id") or "").strip(),
                session_id=str(args.get("session_id") or "").strip() or None,
                arguments=dict(args),
            )
        return self._context_provider(tool_name, args, definition)

    def dispatch(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise error_unknown_tool(tool_name)
        definition = self.definition_for_tool(tool_name)
        context = self._build_context(tool_name, args, definition)
        self._policy_engine.authorize(definition, context)
        return handler(args)

    def dispatch_capability(
        self,
        capability: str,
        args: Dict[str, Any],
        *,
        preferred_tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        if preferred_tool:
            definition = self._definitions.get(preferred_tool)
            if definition is not None and definition.capability == capability:
                return self.dispatch(preferred_tool, args)

        for tool_name in self.tool_names():
            definition = self._definitions[tool_name]
            if definition.capability != capability:
                continue
            context = self._build_context(tool_name, args, definition)
            try:
                self._policy_engine.authorize(definition, context)
            except Exception:
                continue
            return self.dispatch(tool_name, args)

        raise error_unknown_capability(capability)
