import type { FileRecord, SessionRecord, TranscriptEntry, WorkspaceRecord } from "@/lib/api";
import { ROOMS, type RoomInfo } from "@/lib/rooms";

import {
  DEFAULT_PERSONA,
  DEFAULT_ROOM_ID,
  type ChatScope,
  type ChatStructuredResponse,
  type ContactRecord,
  type DeleteSessionStructuredResponse,
  type GmailMessageDetail,
  type Message,
  type NancyEmailComposeState,
  type PendingBreakRoomJokeState,
  type PendingRoomNavigationState,
  type PendingSessionListState,
  type PendingWorkspaceSwitchState,
  type ProviderBadge,
  type RoomCapabilityProfile,
  type WorkContextRecord,
} from "./types";

export function roomById(roomId: string): RoomInfo | undefined {
  return ROOMS.find((room) => room.id === roomId);
}

export function roomTransitionText(roomId: string, persona: string): string {
  const title = roomById(roomId)?.title || roomId;
  return `Now in ${title}. Persona: ${persona}.`;
}

export function roomStatusText(roomId: string, persona: string, profile?: RoomCapabilityProfile): string {
  const base = roomTransitionText(roomId, persona);
  const capabilities = Array.isArray(profile?.primary_capabilities)
    ? profile.primary_capabilities
        .map((item) => String(item).trim())
        .filter(Boolean)
        .slice(0, 3)
    : [];
  const example = Array.isArray(profile?.example_requests) ? String(profile?.example_requests?.[0] || "").trim() : "";
  if (!capabilities.length && !example) {
    return base;
  }
  const lines = [base];
  if (capabilities.length) {
    lines.push(`Capabilities: ${capabilities.join(", ")}.`);
  }
  if (example) {
    lines.push(`Try: ${example}`);
  }
  return lines.join("\n");
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

export function deleteSessionRoomPersona(
  response: DeleteSessionStructuredResponse | undefined,
  fallbackRoom: string,
  fallbackPersona: string,
): { room: string; persona: string } {
  return roomPersonaValues(
    {
      active_room: response?.workspace_state?.active_room || response?.active_session?.active_room,
      active_persona: response?.workspace_state?.active_persona || response?.active_session?.active_persona,
    },
    fallbackRoom,
    fallbackPersona,
  );
}

export function speakerForStructuredResponse(response: ChatStructuredResponse | undefined, fallbackPersona: string): string {
  const explicitSpeaker = String(response?.speaker || "").trim();
  if (explicitSpeaker) {
    return explicitSpeaker;
  }
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

function decodeBasicHtmlEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

export function cleanGmailBodyText(value: string | undefined): string {
  let text = String(value || "").replace(/\r\n?/g, "\n").trim();
  if (!text) {
    return "";
  }
  const htmlMatch = text.match(/<(?:html|body|div|span|blockquote|br|p|table|a)\b/i);
  if (htmlMatch?.index !== undefined) {
    const plainBeforeHtml = text.slice(0, htmlMatch.index).trim();
    if (plainBeforeHtml) {
      text = plainBeforeHtml;
    } else {
      text = text
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<\/(?:div|p|blockquote|li|tr|h[1-6])>/gi, "\n")
        .replace(/<[^>]+>/g, "");
      text = decodeBasicHtmlEntities(text);
    }
  }
  text = text.split(/^\s*On .+? wrote:\s*$/im, 1)[0].trim();
  text = text
    .split("\n")
    .filter((line) => !line.trimStart().startsWith(">"))
    .join("\n");
  return text.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function cleanGmailDetail(message: GmailMessageDetail | undefined): GmailMessageDetail | undefined {
  if (!message) {
    return undefined;
  }
  return {
    ...message,
    body_text: cleanGmailBodyText(message.body_text),
  };
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
    gmailMessages: Array.isArray(response?.gmail_messages) ? response.gmail_messages : undefined,
    gmailMessage: cleanGmailDetail(response?.gmail_message),
    gmailThread: Array.isArray(response?.gmail_thread) ? response.gmail_thread.map((message) => cleanGmailDetail(message) || message) : undefined,
    contacts: Array.isArray(response?.contacts) ? response.contacts : undefined,
    emailReview: response?.email_review,
    workContexts: Array.isArray(response?.contexts) ? response.contexts : undefined,
  });
}

export function shouldShowMessageText(message: Message): boolean {
  if (message.gmailMessages?.length || message.gmailMessage || message.gmailThread?.length || message.contacts?.length || message.emailReview || message.workContexts?.length) {
    return false;
  }
  return Boolean(message.text);
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

export function contactEmailRequest(contact: ContactRecord): string {
  const email = String(contact.email || "").trim();
  return `Nancy, email ${email}`;
}

export function workContextCompleteArgs(contextId: string, activeIndex: number, sessionId: string): Record<string, unknown> {
  const trimmedContextId = String(contextId || "").trim();
  return {
    ...(trimmedContextId ? { context_id: trimmedContextId } : { active_index: activeIndex }),
    session_id: sessionId,
  };
}

export function activeWorkContextNoticeText(contexts: WorkContextRecord[]): string {
  const active = contexts.find((context) => String(context.status || "").toLowerCase() === "active") || contexts[0];
  if (!active) {
    return "";
  }
  const title = String(active.title || "Untitled work").trim();
  const summary = String(active.summary || "").trim();
  const location = [active.active_room, active.active_persona].map((item) => String(item || "").trim()).filter(Boolean).join(" / ");
  const detail = summary ? ` - ${summary}` : "";
  const suffix = location ? ` (${location})` : "";
  return `Active work: ${title}${detail}${suffix}`;
}

export function pendingNancyComposeNotice(compose: NancyEmailComposeState | undefined): string {
  const stage = String(compose?.stage || "").trim().toLowerCase();
  const to = String(compose?.to || "").trim();
  const subject = String(compose?.subject || "").trim();
  if (stage === "recipient") {
    return "Nancy is waiting for the email recipient.";
  }
  if (stage === "subject") {
    return to ? `Nancy is waiting for the subject for ${to}.` : "Nancy is waiting for the email subject.";
  }
  if (stage === "body" || stage === "reply_body") {
    if (to && subject) {
      return `Nancy is waiting for the body for ${to}. Subject: ${subject}`;
    }
    if (to) {
      return `Nancy is waiting for the body for ${to}.`;
    }
    return "Nancy is waiting for the email body.";
  }
  if (stage === "review") {
    return "Nancy has a draft ready. Say send when you want Gmail confirmation prepared.";
  }
  return "Nancy has an email task in progress.";
}

export function pendingWorkspaceSwitchNotice(pending: PendingWorkspaceSwitchState | undefined): string {
  const label = String(pending?.label || pending?.workspace_id || "").trim();
  const workspaceId = String(pending?.workspace_id || "").trim();
  if (!label && !workspaceId) {
    return "";
  }
  return `Workspace "${label || workspaceId}" is ready. Switch now and start a new session there, or stay here.`;
}

export function pendingSessionListNotice(pending: PendingSessionListState | undefined): string {
  const requestText = String(pending?.request_text || "").trim();
  if (!requestText) {
    return "";
  }
  return "List the sessions in this workspace now, or keep working here.";
}

export function pendingRoomNavigationNotice(pending: PendingRoomNavigationState | undefined): string {
  const roomTitle = String(pending?.room_title || pending?.room_id || "").trim();
  const persona = String(pending?.persona || "").trim();
  if (!roomTitle && !persona) {
    return "";
  }
  if (roomTitle && persona) {
    return `Move to ${roomTitle} (${persona}) now, or stay here.`;
  }
  return `Move to ${roomTitle || persona} now, or stay here.`;
}

export function pendingBreakRoomJokeNotice(pending: PendingBreakRoomJokeState | undefined): string {
  const setup = String(pending?.setup || "").trim();
  if (!setup) {
    return "";
  }
  return `Break Room setup waiting: ${setup}`;
}

export function workContextConfirmationId(context: WorkContextRecord | undefined): string {
  if (!context || typeof context !== "object") {
    return "";
  }
  const refs = context.refs;
  if (!refs || typeof refs !== "object") {
    return "";
  }
  const kind = String(refs.kind || "").trim();
  if (!["nancy_email_confirmation", "integration_confirmation"].includes(kind)) {
    return "";
  }
  return String(refs.confirmation_id || "").trim();
}

export function workContextConfirmationLabel(context: WorkContextRecord | undefined): string {
  const refs = context?.refs;
  if (!refs || typeof refs !== "object") {
    return "Confirm Action";
  }
  const kind = String(refs.kind || "").trim();
  if (kind === "nancy_email_confirmation") {
    return "Confirm Gmail Send";
  }
  const actionKind = String(refs.action_kind || "").trim();
  if (actionKind === "calendar.create") {
    return "Confirm Calendar Create";
  }
  if (actionKind === "calendar.update") {
    return "Confirm Calendar Update";
  }
  if (actionKind === "calendar.cancel") {
    return "Confirm Calendar Cancel";
  }
  return "Confirm Action";
}

export function workContextConfirmationAssistantPersona(context: WorkContextRecord | undefined): string {
  const refs = context?.refs;
  if (!refs || typeof refs !== "object") {
    return "";
  }
  const kind = String(refs.kind || "").trim();
  if (kind === "nancy_email_confirmation" || kind === "integration_confirmation") {
    return "Nancy";
  }
  return "";
}

export function workContextCancellationLabel(context: WorkContextRecord | undefined): string {
  const refs = context?.refs;
  if (!refs || typeof refs !== "object") {
    return "Dismiss";
  }
  const kind = String(refs.kind || "").trim();
  if (kind === "nancy_email_confirmation") {
    return "Dismiss Gmail Send";
  }
  const actionKind = String(refs.action_kind || "").trim();
  if (actionKind === "calendar.create") {
    return "Dismiss Calendar Create";
  }
  if (actionKind === "calendar.update") {
    return "Dismiss Calendar Update";
  }
  if (actionKind === "calendar.cancel") {
    return "Dismiss Calendar Cancel";
  }
  return "Dismiss";
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
