export type LobbyState = {
  workspace_id: string;
  active_room: string;
  active_persona: string;
  active_work_context?: WorkContextRecord[];
  pending_nancy_email_compose?: NancyEmailComposeState;
  pending_session_create?: PendingSessionCreateState;
  pending_session_rename?: PendingSessionRenameState;
  pending_session_list?: PendingSessionListState;
  pending_workspace_switch?: PendingWorkspaceSwitchState;
  pending_room_navigation?: PendingRoomNavigationState;
  pending_break_room_joke?: PendingBreakRoomJokeState;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  speaker?: string;
  room?: string;
  sessionId?: string;
  confirmationId?: string;
  confirmationLabel?: string;
  gmailMessages?: GmailMessageSummary[];
  gmailMessage?: GmailMessageDetail;
  gmailThread?: GmailMessageDetail[];
  contacts?: ContactRecord[];
  emailReview?: EmailReview;
  workContexts?: WorkContextRecord[];
};

export type GmailMessageSummary = {
  id: string;
  threadId?: string;
  index?: number;
  from?: string;
  subject?: string;
  date?: string;
  snippet?: string;
};

export type GmailMessageDetail = GmailMessageSummary & {
  to?: string;
  body_text?: string;
};

export type EmailReview = {
  to: string[];
  subject: string;
  body: string;
};

export type ContactRecord = {
  email: string;
  display_name?: string;
  aliases?: string[];
  source?: string;
};

export type WorkContextRecord = {
  context_id: string;
  session_id?: string;
  title?: string;
  summary?: string;
  status?: string;
  active_room?: string;
  active_persona?: string;
  updated_at?: string;
  refs?: {
    kind?: string;
    confirmation_id?: string;
    [key: string]: unknown;
  };
};

export type NancyEmailComposeState = {
  mode?: string;
  stage?: string;
  to?: string;
  subject?: string;
  body?: string;
  source?: string;
};

export type PendingSessionCreateState = {
  request_text?: string;
  ts?: string;
};

export type PendingSessionRenameState = {
  request_text?: string;
  ts?: string;
};

export type PendingSessionListState = {
  request_text?: string;
  ts?: string;
};

export type PendingWorkspaceSwitchState = {
  workspace_id?: string;
  label?: string;
  ts?: string;
};

export type PendingRoomNavigationState = {
  room_id?: string;
  room_title?: string;
  persona?: string;
  request_text?: string;
  ts?: string;
};

export type PendingBreakRoomJokeState = {
  setup?: string;
  punchline?: string;
};

export type ProviderBadge = {
  provider: string;
  fallbackUsed: boolean;
};

export type RoomCapabilityProfile = {
  room_id?: string;
  primary_capabilities?: string[];
  operating_notes?: string[];
  example_requests?: string[];
  plugin_affinities?: string[];
  approval_required_for?: string[];
};

export type ChatStructuredResponse = {
  workspace_id?: string;
  session_id?: string;
  active_room?: string;
  active_persona?: string;
  speaker?: string;
  navigator_activation?: { activated?: boolean };
  routing?: { route_kind?: string; capability?: string; tool?: string; reason?: string };
  provider?: string;
  fallback_used?: boolean;
  confirmation_id?: string;
  action_kind?: string;
  gmail_messages?: GmailMessageSummary[];
  gmail_message?: GmailMessageDetail;
  gmail_thread?: GmailMessageDetail[];
  contacts?: ContactRecord[];
  email_review?: EmailReview;
  contexts?: WorkContextRecord[];
  nancy_email_compose?: NancyEmailComposeState;
  pending_session_rename?: PendingSessionRenameState;
  pending_session_list?: PendingSessionListState;
  clear_pending_session_prompt?: boolean;
  clear_pending_session_list?: boolean;
  clear_pending_nancy_email?: boolean;
  clear_pending_room_navigation?: boolean;
  pending_workspace_switch?: PendingWorkspaceSwitchState;
  clear_pending_workspace_switch?: boolean;
  pending_room_navigation?: PendingRoomNavigationState;
  pending_break_room_joke?: PendingBreakRoomJokeState;
  clear_pending_break_room_joke?: boolean;
};

export type SessionPromptMode = "create" | "rename";

export type DeleteWorkspaceStructuredResponse = {
  workspace_id?: string;
  session_id?: string;
  workspace_state?: LobbyState;
  archived_workspace?: { label?: string };
  switched_workspace?: boolean;
};

export type DeleteSessionStructuredResponse = {
  session_id?: string;
  workspace_id?: string;
  deleted_session_id?: string;
  created_replacement_session?: boolean;
  active_session?: {
    active_room?: string;
    active_persona?: string;
    title?: string;
    description?: string;
  };
  workspace_state?: LobbyState;
};

export type SavedFileNotice = {
  name: string;
  scope: string;
  scopeRef: string;
  fileId: string;
};

export type FileScope = "room" | "session" | "public" | "private";
export type ChatScope = "room" | "global";
export type AttachmentMode = "upload" | "download";

export const DEFAULT_ROOM_ID = "lobby";
export const DEFAULT_PERSONA = "Receptionist";

export const FILE_KIND_OPTIONS = [
  { value: "audio", label: "Audio" },
  { value: "video", label: "Video" },
  { value: "document", label: "Document" },
  { value: "code", label: "Code" },
  { value: "other", label: "Other" },
];

export const FILE_SCOPE_OPTIONS: Array<{ value: FileScope; label: string; description: string }> = [
  { value: "room", label: "Room", description: "Saved to the current room for everyone in that room." },
  { value: "session", label: "Session", description: "Only accessible in this session." },
  { value: "public", label: "Public", description: "Accessible anywhere in Veridex." },
  { value: "private", label: "Private", description: "Stored separately. Access via Nancy memo." },
];

export const PRIVATE_BUCKET_OPTIONS = [
  { value: "by_type", label: "By type" },
  { value: "by_date", label: "By date" },
  { value: "by_project", label: "By project" },
  { value: "by_memo", label: "By memo" },
];
