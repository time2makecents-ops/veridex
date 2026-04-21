from __future__ import annotations

from fastapi import HTTPException

from office_app.server.tool_context import ToolContext
from office_app.server.tool_definitions import ToolDefinition


class ToolPolicyEngine:
    def authorize(self, definition: ToolDefinition, context: ToolContext) -> None:
        if definition.requires_workspace and not context.workspace_id:
            raise HTTPException(status_code=400, detail=f"Tool requires workspace: {definition.tool_name}")

        if definition.allowed_rooms and context.active_room and context.active_room not in definition.allowed_rooms:
            raise HTTPException(
                status_code=403,
                detail=f"Tool {definition.tool_name} is not allowed from room {context.active_room}.",
            )

        if definition.allowed_personas and context.active_persona and context.active_persona not in definition.allowed_personas:
            raise HTTPException(
                status_code=403,
                detail=f"Tool {definition.tool_name} is not allowed for persona {context.active_persona}.",
            )
