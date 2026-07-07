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
    "office.workspace_update": tool_definition("office.workspace_update", "workspace.update", "Update workspace metadata.", requires_workspace=True),
    "office.workspace_activate": tool_definition("office.workspace_activate", "workspace.activate", "Activate a workspace.", requires_workspace=True),
    "office.workspace_delete": tool_definition("office.workspace_delete", "workspace.delete", "Archive a workspace for the current user.", requires_workspace=True),
    "office.bootstrap": tool_definition("office.bootstrap", "workspace.bootstrap", "Bootstrap a workspace.", requires_workspace=True),
    "office.state_get": tool_definition("office.state_get", "workspace.state.get", "Read workspace state.", requires_workspace=True),
    "office.transcript_get": tool_definition("office.transcript_get", "workspace.transcript.get", "Read recent workspace transcript.", requires_workspace=True),
    "office.commands_list": tool_definition("office.commands_list", "system.commands.list", "List available Veridex commands."),
    "office.sessions_list": tool_definition("office.sessions_list", "session.list", "List workspace sessions.", requires_workspace=True),
    "office.session_objects_list": tool_definition("office.session_objects_list", "session.objects.list", "List saved session objects.", requires_workspace=True),
    "office.sessions_search": tool_definition("office.sessions_search", "session.search", "Search workspace session transcripts.", requires_workspace=True),
    "office.session_create": tool_definition("office.session_create", "session.create", "Create a new workspace session.", requires_workspace=True),
    "office.session_info": tool_definition("office.session_info", "session.info", "Read the current workspace session.", requires_workspace=True),
    "office.session_activate": tool_definition("office.session_activate", "session.activate", "Activate a workspace session.", requires_workspace=True),
    "office.session_rename": tool_definition("office.session_rename", "session.rename", "Rename a workspace session.", requires_workspace=True),
    "office.session_delete": tool_definition("office.session_delete", "session.delete", "Delete a workspace session.", requires_workspace=True),
    "office.room_set": tool_definition("office.room_set", "room.navigate", "Switch the active room.", requires_workspace=True),
    "office.nancy_route": tool_definition("office.nancy_route", "room.recommend", "Recommend a room for a request.", requires_workspace=True),
    "office.room_capabilities": tool_definition(
        "office.room_capabilities",
        "room.capabilities",
        "Describe the active room's governed capabilities, allowed tools, collaborators, and approval boundaries.",
        requires_workspace=True,
    ),
    "office.navigator_status_report": tool_definition(
        "office.navigator_status_report",
        "navigator.status_report",
        "Generate a read-only Navigator diagnostic report for Veridex.",
        requires_workspace=True,
    ),
    "office.navigator_recent_errors": tool_definition(
        "office.navigator_recent_errors",
        "navigator.recent_errors",
        "Read recent Veridex incidents and log tails for Navigator diagnostics.",
        requires_workspace=True,
    ),
    "office.navigator_explain_error": tool_definition(
        "office.navigator_explain_error",
        "navigator.explain_error",
        "Explain a Veridex error and suggest a safe next step.",
        requires_workspace=True,
    ),
    "office.ai_generate": tool_definition("office.ai_generate", "ai.respond", "Generate a model response.", requires_workspace=True),
    "office.search_web": tool_definition("office.search_web", "search.web", "Search the web.", requires_workspace=True),
    "office.search_reviews": tool_definition("office.search_reviews", "search.reviews", "Search reviews.", requires_workspace=True),
    "office.search_places": tool_definition("office.search_places", "search.places", "Search places.", requires_workspace=True),
    "office.ocr_extract": tool_definition("office.ocr_extract", "document.ocr", "Extract text from a document or image.", requires_workspace=True),
    "office.image_generate": tool_definition(
        "office.image_generate",
        "image.generate",
        "Generate an image from an Art Department prompt and save it as a workspace file.",
        requires_workspace=True,
        allowed_rooms=("art_department",),
    ),
    "office.gmail_search": tool_definition("office.gmail_search", "integration.gmail.search", "Search the connected Gmail account."),
    "office.gmail_read": tool_definition("office.gmail_read", "integration.gmail.read", "Read a Gmail message."),
    "office.gmail_thread_read": tool_definition("office.gmail_thread_read", "integration.gmail.thread_read", "Read a Gmail thread."),
    "office.gmail_draft": tool_definition("office.gmail_draft", "integration.gmail.draft", "Prepare a Gmail draft without sending it."),
    "office.gmail_send": tool_definition("office.gmail_send", "integration.gmail.send", "Prepare a Gmail send confirmation."),
    "office.contact_resolve_email": tool_definition("office.contact_resolve_email", "contact.email.resolve", "Resolve a saved contact for Nancy email composition."),
    "office.contact_save": tool_definition("office.contact_save", "contact.save", "Save a Veridex email contact."),
    "office.contact_list": tool_definition("office.contact_list", "contact.list", "List Veridex email contacts."),
    "office.calendar_list": tool_definition("office.calendar_list", "integration.calendar.list", "List connected Google Calendar events."),
    "office.calendar_create": tool_definition("office.calendar_create", "integration.calendar.create", "Prepare a Calendar create confirmation."),
    "office.calendar_update": tool_definition("office.calendar_update", "integration.calendar.update", "Prepare a Calendar update confirmation."),
    "office.calendar_cancel": tool_definition("office.calendar_cancel", "integration.calendar.cancel", "Prepare a Calendar cancel confirmation."),
    "office.integration_confirm": tool_definition("office.integration_confirm", "integration.confirm", "Confirm a pending external action."),
    "office.integration_cancel": tool_definition("office.integration_cancel", "integration.cancel", "Dismiss a pending external action."),
    "office.meeting_state_start": tool_definition("office.meeting_state_start", "meeting_state.start", "Start internal Conference Room meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_add_agenda": tool_definition("office.meeting_state_add_agenda", "meeting_state.agenda.add", "Add an agenda item to the active internal meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_record_decision": tool_definition("office.meeting_state_record_decision", "meeting_state.decision.record", "Record a decision in the active internal meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_add_action_item": tool_definition("office.meeting_state_add_action_item", "meeting_state.action_item.add", "Add an action item to the active internal meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_add_parking_lot": tool_definition("office.meeting_state_add_parking_lot", "meeting_state.parking_lot.add", "Add a parking-lot item to the active internal meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_update_title": tool_definition("office.meeting_state_update_title", "meeting_state.title.update", "Update the active internal meeting title.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_update_item": tool_definition("office.meeting_state_update_item", "meeting_state.item.update", "Update an item in the active internal meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_delete_item": tool_definition("office.meeting_state_delete_item", "meeting_state.item.delete", "Delete an item from the active internal meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_state_show": tool_definition("office.meeting_state_show", "meeting_state.show", "Show the active internal Conference Room meeting state.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "office.meeting_brief_save": tool_definition("office.meeting_brief_save", "meeting_brief.save", "Save the active Conference Room meeting state as a deterministic or polished artifact.", requires_workspace=True, allowed_rooms=("conference_room",)),
    "mailroom.dispatch": tool_definition(
        "mailroom.dispatch",
        "memo.dispatch",
        "Send a memo to another room and return the destination room's response.",
        requires_workspace=True,
    ),
    "office.memos_list": tool_definition("office.memos_list", "memo.list", "List memos.", requires_workspace=True),
    "office.memo_get": tool_definition("office.memo_get", "memo.get", "Get a memo.", requires_workspace=True),
    "office.work_context_save": tool_definition("office.work_context_save", "work_context.save", "Save active cross-room work context.", requires_workspace=True),
    "office.work_context_list": tool_definition("office.work_context_list", "work_context.list", "List active or recent cross-room work context.", requires_workspace=True),
    "office.work_context_complete": tool_definition("office.work_context_complete", "work_context.complete", "Complete active cross-room work context.", requires_workspace=True),
    "office.artifact_create": tool_definition("office.artifact_create", "artifact.create", "Create an artifact.", requires_workspace=True),
    "office.artifact_get": tool_definition("office.artifact_get", "artifact.get", "Get an artifact.", requires_workspace=True),
    "office.artifact_list": tool_definition("office.artifact_list", "artifact.list", "List artifacts.", requires_workspace=True),
    "office.artifact_update": tool_definition("office.artifact_update", "artifact.update", "Update an artifact.", requires_workspace=True),
    "office.artifact_append": tool_definition("office.artifact_append", "artifact.append", "Append to an artifact.", requires_workspace=True),
    "office.artifact_archive": tool_definition("office.artifact_archive", "artifact.archive", "Archive an artifact.", requires_workspace=True),
    "office.artifact_delete": tool_definition("office.artifact_delete", "artifact.delete", "Delete an artifact.", requires_workspace=True),
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
    "office.room_memory_remember": tool_definition(
        "office.room_memory_remember",
        "room.memory.remember",
        "Store a durable room-specific behavior memory in Records Archive and link it to the workspace room.",
        requires_workspace=True,
    ),
    "office.room_memory_list": tool_definition(
        "office.room_memory_list",
        "room.memory.list",
        "List the room's saved behavior memories from Records Archive.",
        requires_workspace=True,
    ),
    "office.room_memory_forget": tool_definition(
        "office.room_memory_forget",
        "room.memory.forget",
        "Remove a room-specific behavior memory reference from the workspace room.",
        requires_workspace=True,
    ),
    "office.file_upload": tool_definition("office.file_upload", "file.upload", "Upload a workspace file.", requires_workspace=True),
    "office.file_list": tool_definition("office.file_list", "file.list", "List workspace files.", requires_workspace=True),
    "office.file_get": tool_definition("office.file_get", "file.get", "Read workspace file metadata.", requires_workspace=True),
    "office.file_download": tool_definition("office.file_download", "file.download", "Download a workspace file.", requires_workspace=True),
    "office.private_file_upload": tool_definition("office.private_file_upload", "private_file.upload", "Upload a private file.", requires_workspace=True),
    "office.private_file_list": tool_definition("office.private_file_list", "private_file.list", "List private files.", requires_workspace=True),
    "office.private_file_get": tool_definition("office.private_file_get", "private_file.get", "Read private file metadata.", requires_workspace=True),
}
