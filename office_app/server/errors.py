from __future__ import annotations

from fastapi import HTTPException


def error_missing_required_field(field: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"Missing required field: {field}")


def error_unknown_tool(tool: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"Unknown tool: {tool}")


def error_unknown_capability(capability: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"Unknown capability: {capability}")


def error_workspace_not_initialized(workspace_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Workspace not initialized: {workspace_id}")


def error_memo_not_found(memo_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Memo not found: {memo_id}")
