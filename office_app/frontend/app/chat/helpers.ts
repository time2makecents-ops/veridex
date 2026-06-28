import type { FileRecord, SessionRecord, TranscriptEntry, WorkspaceRecord } from "@/lib/api";
import { ROOMS, type RoomInfo } from "@/lib/rooms";

import {
  DEFAULT_PERSONA,
  DEFAULT_ROOM_ID,
  type ChatScope,
  type ChatStructuredResponse,
  type Message,
  type ProviderBadge,
} from "./types";

export function roomById(roomId: string): RoomInfo | undefined {
  return ROOMS.find((room) => room.id === roomId);
}

export function roomTransitionText(roomId: string, persona: string): string {
  const title = roomById(roomId)?.title || roomId;
  return `Now in ${title}. Persona: ${persona}.`;
}

export function lobbyOrientationText(persona: string): string {
  return [
    `${persona} ready. You are in the Lobby.`,
    "",
    "I can show you every room, help you start onboarding, or send you to a department.",
    "Try: what rooms are there, go to Conference Room, or go to My Office.",
  ].join("\n");
}

export function backendDisconnectedMessage(message: string): string {
  const text = message.toLowerCase();
  if (
    text.includes("500") ||
    text.includes("failed to fetch") ||
    text.includes("unable to connect") ||
    text.includes("networkerror") ||
    text.includes("request timed out")
  ) {
    return "Veridex backend disconnected. Check the server on port 8078.";
  }
  return "";
}

export function visibleMessagesForScope(
  messages: Message[],
  sessionId: string,
  chatScope: ChatScope,
  activeRoom: string,
): Message[] {
  return messages.filter((message) => {
    const sessionMatches = message.sessionId === sessionId;
    if (!sessionMatches) {
      return false;
    }
    if (chatScope === "global") {
      return true;
    }
    return !message.room || message.room === activeRoom;
  });
}

export function roomPersonaValues(
  state: { active_room?: string; active_persona?: string } | undefined,
  fallbackRoom = DEFAULT_ROOM_ID,
  fallbackPersona = DEFAULT_PERSONA,
): { room: string; persona: string } {
  return {
    room: String(state?.active_room || fallbackRoom),
    persona: String(state?.active_persona || fallbackPersona),
  };
}

export function workspaceById(workspaces: WorkspaceRecord[], workspaceId: string): WorkspaceRecord | undefined {
  return workspaces.find((workspace) => String(workspace.workspace_id) === workspaceId);
}

export function workspaceLabelById(workspaces: WorkspaceRecord[], workspaceId: string): string {
  return workspaceById(workspaces, workspaceId)?.label || workspaceId;
}

export function workspaceDraftValues(
  workspace: WorkspaceRecord | undefined,
  fallbackTitle = "",
  fallbackDescription = "",
): { title: string; description: string } {
  return {
    title: String(workspace?.label || fallbackTitle),
    description: String(workspace?.description || fallbackDescription),
  };
}

export function workspaceMetadataValues(
  workspace: WorkspaceRecord | undefined,
  titleDraft: string,
  descriptionDraft: string,
  fallbackLabel: string,
  fallbackId: string,
): { label: string; description: string } {
  return {
    label: titleDraft.trim() || String(workspace?.label || fallbackLabel || fallbackId),
    description: descriptionDraft.trim(),
  };
}

export function sessionById(sessions: SessionRecord[], sessionId: string): SessionRecord | undefined {
  return sessions.find((session) => String(session.session_id) === sessionId);
}

export function sessionDraftValues(
  session: Pick<SessionRecord, "title" | "description"> | undefined,
  fallbackTitle = "",
  fallbackDescription = "",
): { title: string; description: string } {
  return {
    title: String(session?.title || fallbackTitle),
    description: String(session?.description || fallbackDescription),
  };
}

export function visibleSessions(sessions: SessionRecord[], hiddenSessionIds: Set<string>): SessionRecord[] {
  return sessions.filter((session) => !hiddenSessionIds.has(String(session.session_id)));
}

export function hiddenSessionsWith(hiddenSessionIds: Set<string>, sessionId: string): Set<string> {
  return new Set([...hiddenSessionIds, sessionId]);
}

export function deleteSessionNotice(targetTitle: string, deletedWasCurrent: boolean, replacementTitle: string): string {
  return deletedWasCurrent
    ? `Deleted session ${targetTitle}. Switched to ${replacementTitle}.`
    : `Deleted session ${targetTitle}.`;
}

export function speakerForStructuredResponse(response: ChatStructuredResponse | undefined, fallbackPersona: string): string {
  const speaker =
    response?.routing?.route_kind === "clarify" || response?.navigator_activation?.activated
      ? "Navigator"
      : response?.speaker;
  return String(speaker || fallbackPersona);
}

export function providerBadgeForResponse(response: ChatStructuredResponse | undefined): ProviderBadge | null {
  if (!response?.provider) {
    return null;
  }
  return {
    provider: response.provider,
    fallbackUsed: Boolean(response.fallback_used),
  };
}

export function confirmationLabelForAction(actionKind: string | undefined): string | undefined {
  return actionKind === "gmail.send" ? "Confirm Gmail Send" : undefined;
}

export function createMessage(message: Omit<Message, "id">): Message {
  return {
    id: crypto.randomUUID(),
    ...message,
  };
}

export function assistantMessageForResponse(
  response: ChatStructuredResponse | undefined,
  text: string,
  speaker: string,
  room: string,
  sessionId: string,
): Message {
  return createMessage({
    role: "assistant",
    speaker,
    text,
    room,
    sessionId,
    confirmationId: typeof response?.confirmation_id === "string" ? response.confirmation_id : undefined,
    confirmationLabel: confirmationLabelForAction(response?.action_kind),
  });
}

export function integrationConfirmationMessage(text: string, room: string, sessionId: string): Message {
  return createMessage({
    role: "assistant",
    speaker: "Nancy",
    text,
    room,
    sessionId,
  });
}

export function fileSortLabel(file: FileRecord): string {
  const date = file.created_at ? new Date(file.created_at).toLocaleDateString() : "no date";
  const session = String(file.scope_ref || file.workspace_id || "workspace");
  const kind = file.kind || "file";
  return `${date} - ${session} - ${kind}`;
}

export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Unable to read file."));
    reader.readAsDataURL(file);
  });
}

export function mapTranscriptEntries(entries: TranscriptEntry[]): Message[] {
  const mapped = entries
    .filter((entry) => typeof entry.text === "string" && entry.text.trim())
    .map((entry, index) => {
      const entryRole = String(entry.role || "").trim().toLowerCase();
      const role: Message["role"] = entryRole === "user" ? "user" : entryRole === "system" ? "system" : "assistant";
      const speaker =
        typeof entry.speaker === "string" && entry.speaker.trim()
          ? entry.speaker
          : role === "user"
            ? "You"
            : role === "system"
              ? "System"
              : undefined;
      const idSource = typeof entry.ts === "string" && entry.ts.trim() ? entry.ts : `${index}`;
      return {
        id: `${idSource}-${index}`,
        role,
        speaker,
        text: String(entry.text),
        room: typeof entry.room === "string" && entry.room.trim() ? entry.room : undefined,
        sessionId: typeof entry.session_id === "string" && entry.session_id.trim() ? entry.session_id : undefined,
      };
    });
  const conversational = mapped.filter((entry) => entry.role !== "system");
  return conversational.length ? mapped : mapped.slice(-12);
}
