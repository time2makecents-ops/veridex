from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    capability: str
    description: str = ""
    allowed_rooms: Tuple[str, ...] = ()
    allowed_personas: Tuple[str, ...] = ()
    requires_workspace: bool = False
    visibility: str = "public"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)


def tool_definition(tool_name: str, capability: str, description: str = "", **kwargs: Any) -> ToolDefinition:
    return ToolDefinition(
        tool_name=tool_name,
        capability=capability,
        description=description,
        **kwargs,
    )


VERIDEX_TOOL_DEFINITIONS = {
    "office.workspaces_list": tool_definition("office.workspaces_list", "workspace.list", "List workspaces."),
    "office.workspace_new": tool_definition("office.workspace_new", "workspace.create", "Create a workspace."),
    "office.bootstrap": tool_definition("office.bootstrap", "workspace.bootstrap", "Bootstrap a workspace.", requires_workspace=True),
    "office.state_get": tool_definition("office.state_get", "workspace.state.get", "Read workspace state.", requires_workspace=True),
    "office.transcript_get": tool_definition("office.transcript_get", "workspace.transcript.get", "Read recent workspace transcript.", requires_workspace=True),
    "office.commands_list": tool_definition("office.commands_list", "system.commands.list", "List available Veridex commands."),
    "office.room_set": tool_definition("office.room_set", "room.navigate", "Switch the active room.", requires_workspace=True),
    "office.nancy_route": tool_definition("office.nancy_route", "room.recommend", "Recommend a room for a request.", requires_workspace=True),
    "office.ai_generate": tool_definition("office.ai_generate", "ai.respond", "Generate a model response.", requires_workspace=True),
    "office.search_web": tool_definition("office.search_web", "search.web", "Search the web.", requires_workspace=True),
    "office.search_reviews": tool_definition("office.search_reviews", "search.reviews", "Search reviews.", requires_workspace=True),
    "office.search_places": tool_definition("office.search_places", "search.places", "Search places.", requires_workspace=True),
    "office.ocr_extract": tool_definition("office.ocr_extract", "document.ocr", "Extract text from a document or image.", requires_workspace=True),
    "mailroom.dispatch": tool_definition("mailroom.dispatch", "memo.dispatch", "Send a memo to another room.", requires_workspace=True),
    "office.memos_list": tool_definition("office.memos_list", "memo.list", "List memos.", requires_workspace=True),
    "office.memo_get": tool_definition("office.memo_get", "memo.get", "Get a memo.", requires_workspace=True),
    "office.artifact_create": tool_definition("office.artifact_create", "artifact.create", "Create an artifact.", requires_workspace=True),
    "office.artifact_get": tool_definition("office.artifact_get", "artifact.get", "Get an artifact.", requires_workspace=True),
    "office.artifact_list": tool_definition("office.artifact_list", "artifact.list", "List artifacts.", requires_workspace=True),
    "office.artifact_update": tool_definition("office.artifact_update", "artifact.update", "Update an artifact.", requires_workspace=True),
    "office.artifact_append": tool_definition("office.artifact_append", "artifact.append", "Append to an artifact.", requires_workspace=True),
    "office.artifact_archive": tool_definition("office.artifact_archive", "artifact.archive", "Archive an artifact.", requires_workspace=True),
    "office.archive_store_text": tool_definition("office.archive_store_text", "archive.store_text", "Store text in the archive.", requires_workspace=True),
    "office.archive_list": tool_definition("office.archive_list", "archive.list", "List archived artifacts.", requires_workspace=True),
    "office.archive_get": tool_definition("office.archive_get", "archive.get", "Get an archived artifact.", requires_workspace=True),
    "office.nancy_artifacts_list": tool_definition("office.nancy_artifacts_list", "artifact.list.assist", "List artifacts through Nancy.", requires_workspace=True),
    "office.nancy_artifact_open": tool_definition("office.nancy_artifact_open", "artifact.get.assist", "Open an artifact through Nancy.", requires_workspace=True),
    "office.nancy_workspace_briefing": tool_definition("office.nancy_workspace_briefing", "workspace.briefing", "Get a workspace briefing.", requires_workspace=True),
    "office.receptionist_context_get": tool_definition(
        "office.receptionist_context_get",
        "receptionist.context.get",
        "Read receptionist context.",
        requires_workspace=True,
        visibility="internal",
    ),
    "office.receptionist_context_update": tool_definition(
        "office.receptionist_context_update",
        "receptionist.context.update",
        "Update receptionist context.",
        requires_workspace=True,
        visibility="internal",
    ),
    "office.file_upload": tool_definition("office.file_upload", "file.upload", "Upload a workspace file.", requires_workspace=True),
    "office.file_list": tool_definition("office.file_list", "file.list", "List workspace files.", requires_workspace=True),
    "office.file_get": tool_definition("office.file_get", "file.get", "Read workspace file metadata.", requires_workspace=True),
    "office.file_download": tool_definition("office.file_download", "file.download", "Download a workspace file.", requires_workspace=True),
    "office.private_file_upload": tool_definition("office.private_file_upload", "private_file.upload", "Upload a private file.", requires_workspace=True),
    "office.private_file_list": tool_definition("office.private_file_list", "private_file.list", "List private files.", requires_workspace=True),
    "office.private_file_get": tool_definition("office.private_file_get", "private_file.get", "Read private file metadata.", requires_workspace=True),
}
