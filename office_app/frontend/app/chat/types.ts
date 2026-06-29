export type LobbyState = {
  workspace_id: string;
  active_room: string;
  active_persona: string;
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
};

export type ProviderBadge = {
  provider: string;
  fallbackUsed: boolean;
};

export type RoomCapabilityProfile = {
  room_id?: string;
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
  routing?: { route_kind?: string };
  provider?: string;
  fallback_used?: boolean;
  confirmation_id?: string;
  action_kind?: string;
};

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
