export type LobbyResponse = {
  structuredContent?: {
    session_id?: string;
    workspace_id?: string;
    user?: {
      display_name?: string;
      name?: string;
      user_id?: string;
      role?: string;
      is_admin?: boolean;
    };
    [key: string]: unknown;
  };
  content?: Array<{ type?: string; text?: string }>;
  session_id?: string;
  workspace_id?: string;
  [key: string]: unknown;
};

export type RequestResponse = LobbyResponse & {
  session_id?: string;
  workspace_id?: string;
  content?: Array<{ type?: string; text?: string }>;
};

export type ToolResponse = {
  structuredContent?: {
    active_room?: string;
    active_persona?: string;
    room_title?: string;
    workspace_id?: string;
    [key: string]: unknown;
  };
  content?: Array<{ type?: string; text?: string }>;
  [key: string]: unknown;
};

export type FileRecord = {
  file_id: string;
  workspace_id: string;
  scope?: string;
  scope_ref?: string;
  original_name: string;
  mime_type?: string;
  kind?: string;
  description?: string;
  download_url?: string;
  created_at?: string;
  updated_at?: string;
  byte_size?: number;
  sha256?: string;
  storage_path?: string;
  [key: string]: unknown;
};

export type TranscriptEntry = {
  ts?: string;
  role?: string;
  room?: string;
  text?: string;
  speaker?: string;
  [key: string]: unknown;
};

export type SessionRecord = {
  session_id: string;
  user_id?: string;
  title?: string;
  description?: string;
  active_workspace_id?: string;
  created_at?: string;
  updated_at?: string;
  last_active_at?: string;
  active_room?: string;
  active_persona?: string;
  is_current?: boolean;
  [key: string]: unknown;
};

export type WorkspaceRecord = {
  workspace_id: string;
  label?: string;
  description?: string;
  status?: string;
  created_utc?: string;
  last_seen_utc?: string;
  last_room?: string;
  archived_at?: string;
  archived_by_user_id?: string;
  deleted_by_user_id?: string;
  session_count?: number;
  last_active_at?: string;
  last_session_id?: string;
  [key: string]: unknown;
};

export type ArtifactRecord = {
  artifact_id: string;
  workspace_id?: string;
  display_name?: string;
  title?: string;
  artifact_type?: string;
  content_preview?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type UserRecord = {
  user_id: string;
  name?: string;
  display_name?: string;
  pin_code?: string;
  role?: string;
  is_admin?: boolean;
  onboarding_complete?: boolean;
  default_workspace_id?: string;
  last_active_workspace_id?: string;
  last_active_session_id?: string;
  created_at?: string;
  updated_at?: string;
  session_count?: number;
  workspace_count?: number;
  [key: string]: unknown;
};

export type IntegrationConnection = {
  provider: string;
  configured: boolean;
  connected: boolean;
  account_email: string;
  scopes: string[];
  access_token_expires_at: string;
  updated_at: string;
};

export type AdminUserDetail = {
  user: UserRecord;
  sessions: SessionRecord[];
  workspaces: WorkspaceRecord[];
  artifacts?: Array<{
    artifact_id: string;
    workspace_id?: string;
    display_name?: string;
    artifact_type?: string;
    content_preview?: string;
    updated_at?: string;
    created_at?: string;
    [key: string]: unknown;
  }>;
  user_folder?: string;
  profile_path?: string;
};

export type AdminWorkspaceDetail = {
  workspace: WorkspaceRecord;
  sessions: SessionRecord[];
  artifacts?: ArtifactRecord[];
  files?: FileRecord[];
};

type FileListEnvelope = {
  structuredContent?: {
    workspace_id?: string;
    count?: number;
    files?: FileRecord[];
  };
  workspace_id?: string;
  count?: number;
  files?: FileRecord[];
  [key: string]: unknown;
};

type FileRecordEnvelope = {
  structuredContent?: FileRecord;
  [key: string]: unknown;
} & Partial<FileRecord>;

function backendBaseUrl(): string {
  return process.env.NEXT_PUBLIC_VERIDEX_API_BASE_URL ?? "";
}

async function readResponseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
    if (payload.detail && typeof payload.detail === "object") {
      const detail = payload.detail as Record<string, unknown>;
      const detailMessage = detail.message;
      if (typeof detailMessage === "string" && detailMessage.trim()) {
        return detailMessage;
      }
      return JSON.stringify(detail);
    }
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }
    if (payload.message && typeof payload.message === "object") {
      return JSON.stringify(payload.message);
    }
    return `Request failed with ${response.status}`;
  } catch {
    return `Request failed with ${response.status}`;
  }
}

async function fetchJsonWithTimeout(path: string, init: RequestInit, timeoutMs = 30000): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(path, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function postJson<T>(path: string, body: unknown, headers?: HeadersInit): Promise<T> {
  const response = await fetchJsonWithTimeout(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(headers || {}),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }

  return (await response.json()) as T;
}

async function authorizedGetJson<T>(path: string): Promise<T> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const url = new URL(path, window.location.origin);
  url.searchParams.set("session_id", sessionId);
  const response = await fetchJsonWithTimeout(url.pathname + url.search, {
    method: "GET",
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  return (await response.json()) as T;
}

export async function onboard(
  name: string,
  display_name: string,
  pin_code: string,
  face_photo_data?: string,
): Promise<LobbyResponse> {
  return postJson<LobbyResponse>("/lobby/onboard", { name, display_name, pin_code, face_photo_data });
}

export async function enter(pin_code: string): Promise<LobbyResponse> {
  return postJson<LobbyResponse>("/lobby/enter", { pin_code });
}

export async function request(text: string, sessionIdOverride?: string): Promise<RequestResponse> {
  const storedSessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  const sessionId = String(sessionIdOverride || storedSessionId || "");
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout("/request", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
    body: JSON.stringify({ text, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }

  return (await response.json()) as RequestResponse;
}

export async function callTool(tool: string, arguments_: Record<string, unknown> = {}): Promise<ToolResponse> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const explicitSessionId = typeof arguments_.session_id === "string" ? String(arguments_.session_id) : "";

  const response = await fetchJsonWithTimeout("/call", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
    body: JSON.stringify({
      tool,
      arguments: {
        ...arguments_,
        session_id: explicitSessionId || sessionId,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }

  return (await response.json()) as ToolResponse;
}

export async function loadTranscript(limit = 100, sessionId?: string): Promise<TranscriptEntry[]> {
  const response = await callTool("office.transcript_get", { limit, session_id: sessionId });
  const structured = response.structuredContent as { entries?: unknown } | undefined;
  return Array.isArray(structured?.entries) ? (structured.entries as TranscriptEntry[]) : [];
}

export async function listSessions(workspace_id?: string): Promise<SessionRecord[]> {
  const args: Record<string, unknown> = {};
  if (workspace_id) {
    args.workspace_id = workspace_id;
  }
  const response = await callTool("office.sessions_list", args);
  const structured = response.structuredContent as { sessions?: unknown } | undefined;
  return Array.isArray(structured?.sessions) ? (structured.sessions as SessionRecord[]) : [];
}

export async function listWorkspaces(): Promise<WorkspaceRecord[]> {
  const response = await callTool("office.workspaces_list", {});
  const structured = response.structuredContent as { workspaces?: unknown } | undefined;
  return Array.isArray(structured?.workspaces) ? (structured.workspaces as WorkspaceRecord[]) : [];
}

export async function createSession(title: string, description: string): Promise<SessionRecord> {
  const response = await callTool("office.session_create", { title, description });
  const structured = response.structuredContent as SessionRecord | undefined;
  if (structured && typeof structured.session_id === "string") {
    return structured;
  }
  return {
    session_id: String(response.session_id || ""),
    title,
    description,
    active_workspace_id: String(response.workspace_id || ""),
  };
}

export async function renameSession(session_id: string, title: string, description: string): Promise<SessionRecord> {
  const response = await callTool("office.session_rename", { session_id, title, description });
  const structured = response.structuredContent as SessionRecord | undefined;
  if (structured && typeof structured.session_id === "string") {
    return structured;
  }
  return {
    session_id,
    title,
    description,
    active_workspace_id: String(response.workspace_id || ""),
  };
}

export async function createWorkspace(label: string): Promise<WorkspaceRecord> {
  const response = await callTool("office.workspace_new", { label });
  const structured = response.structuredContent as WorkspaceRecord | undefined;
  if (structured && typeof structured.workspace_id === "string") {
    return structured;
  }
  return {
    workspace_id: String(response.workspace_id || ""),
    label,
  };
}

export async function updateWorkspaceMetadata(
  workspace_id: string,
  payload: { label?: string; description?: string },
): Promise<WorkspaceRecord> {
  const response = await callTool("office.workspace_update", { workspace_id, ...payload });
  const structured = response.structuredContent as WorkspaceRecord | undefined;
  if (structured && typeof structured.workspace_id === "string") {
    return structured;
  }
  return {
    workspace_id,
    label: String(payload.label || ""),
    description: String(payload.description || ""),
  };
}

export async function listWorkspaceArtifacts(workspace_id: string): Promise<ArtifactRecord[]> {
  const response = await callTool("office.artifact_list", {
    workspace_id,
    retrieval_scope: "workspace",
    include_archived: false,
  });
  const structured = response.structuredContent as { artifacts?: unknown } | undefined;
  return Array.isArray(structured?.artifacts) ? (structured.artifacts as ArtifactRecord[]) : [];
}

export async function listWorkspaceFiles(workspace_id: string): Promise<FileRecord[]> {
  const response = await callTool("office.file_list", {
    workspace_id,
  });
  const structured = response.structuredContent as { files?: unknown } | undefined;
  return Array.isArray(structured?.files) ? (structured.files as FileRecord[]) : [];
}

export async function activateWorkspace(workspace_id: string): Promise<{ workspace_id: string; session_id?: string; title?: string; description?: string }> {
  const response = await callTool("office.workspace_activate", { workspace_id });
  const structured = response.structuredContent as {
    workspace_id?: string;
    session_id?: string;
    title?: string;
    description?: string;
  } | undefined;
  return {
    workspace_id: String(structured?.workspace_id || response.workspace_id || workspace_id),
    session_id: structured?.session_id || String(response.session_id || ""),
    title: structured?.title || String(response.title || ""),
    description: structured?.description || String(response.description || ""),
  };
}

export async function deleteWorkspace(workspace_id: string): Promise<LobbyResponse> {
  return callTool("office.workspace_delete", { workspace_id });
}

export async function activateSession(session_id: string): Promise<SessionRecord> {
  const response = await callTool("office.session_activate", { session_id });
  const structured = response.structuredContent as SessionRecord | undefined;
  if (structured && typeof structured.session_id === "string") {
    return structured;
  }
  return {
    session_id,
    active_workspace_id: String(response.workspace_id || ""),
  };
}

export async function deleteSession(session_id: string, currentSessionId?: string): Promise<LobbyResponse> {
  const storedSessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  const authSessionId = String(currentSessionId || storedSessionId || "");
  if (!authSessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout(`/sessions/${encodeURIComponent(session_id)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": authSessionId,
    },
  });

  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }

  return (await response.json()) as LobbyResponse;
}

export async function uploadFile(payload: {
  name: string;
  content_text?: string;
  content_base64?: string;
  data_url?: string;
  mime_type?: string;
  kind?: string;
  scope?: string;
  scope_ref?: string;
  description?: string;
}): Promise<FileRecord> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await postJson<FileRecordEnvelope>("/files", {
    ...payload,
    session_id: sessionId,
  });
  return (response.structuredContent as FileRecord | undefined) ?? (response as FileRecord);
}

export async function listFiles(scope?: string, scope_ref?: string): Promise<{ workspace_id: string; count: number; files: FileRecord[] }> {
  const query = new URLSearchParams();
  if (scope) {
    query.set("scope", scope);
  }
  if (scope_ref) {
    query.set("scope_ref", scope_ref);
  }
  const response = await authorizedGetJson<FileListEnvelope>(`/files${query.toString() ? `?${query.toString()}` : ""}`);
  const structured = response.structuredContent;
  return {
    workspace_id: String(structured?.workspace_id ?? response.workspace_id ?? ""),
    count: Number(structured?.count ?? response.count ?? 0),
    files: Array.isArray(structured?.files) ? structured.files : Array.isArray(response.files) ? response.files : [],
  };
}

export function fileDownloadUrl(file: FileRecord): string {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  const url = new URL(String(file.download_url || `/files/${file.file_id}/download`), window.location.origin);
  if (sessionId) {
    url.searchParams.set("session_id", sessionId);
  }
  return url.pathname + url.search;
}

export async function readFileText(file: FileRecord): Promise<string> {
  const url = fileDownloadUrl(file);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  return await response.text();
}

export async function extractFileText(file: FileRecord): Promise<string> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await callTool("office.ocr_extract", {
    file_id: file.file_id,
    scope: file.scope || "workspace",
  });
  const structured = response.structuredContent as { text?: unknown } | undefined;
  const contentText = response.content?.find((item) => item.type === "text")?.text;
  if (typeof structured?.text === "string" && structured.text.trim()) {
    return structured.text;
  }
  if (typeof contentText === "string" && contentText.trim()) {
    return contentText;
  }
  return "No extracted text returned.";
}

export function requestText(response: RequestResponse): string {
  const structured = response.structuredContent as { response_text?: unknown } | undefined;
  const contentText = response.content?.find((item) => item.type === "text")?.text;
  const structuredText = structured?.response_text;

  if (typeof contentText === "string" && contentText.trim()) {
    return contentText;
  }
  if (typeof structuredText === "string" && structuredText.trim()) {
    return structuredText;
  }
  if (contentText != null) {
    return typeof contentText === "string" ? contentText : JSON.stringify(contentText);
  }
  if (structuredText != null) {
    return typeof structuredText === "string" ? structuredText : JSON.stringify(structuredText);
  }
  return "Request completed.";
}

export async function resetTestData(): Promise<void> {
  const response = await fetch(`${backendBaseUrl()}/dev/reset-test-data`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
}

export async function getCurrentUser(): Promise<UserRecord> {
  const response = await authorizedGetJson<LobbyResponse>("/me");
  const structured = response.structuredContent as { user?: UserRecord } | undefined;
  if (!structured?.user || typeof structured.user.user_id !== "string") {
    throw new Error("Unable to load current user.");
  }
  return structured.user;
}

export async function listIntegrations(): Promise<IntegrationConnection[]> {
  const response = await authorizedGetJson<LobbyResponse>("/integrations");
  const structured = response.structuredContent as { connections?: IntegrationConnection[] } | undefined;
  return Array.isArray(structured?.connections) ? structured.connections : [];
}

export async function startGoogleConnection(): Promise<string> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await postJson<LobbyResponse>("/integrations/google/connect", {}, { "X-Session-Id": sessionId });
  const structured = response.structuredContent as { authorization_url?: unknown } | undefined;
  const url = typeof structured?.authorization_url === "string" ? structured.authorization_url : "";
  if (!url) {
    throw new Error("Google authorization URL was not returned.");
  }
  return url;
}

export async function disconnectIntegration(provider: string): Promise<void> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout(`/integrations/${encodeURIComponent(provider)}`, {
    method: "DELETE",
    headers: { "X-Session-Id": sessionId },
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
}

export async function adminListUsers(): Promise<UserRecord[]> {
  const response = await authorizedGetJson<LobbyResponse>("/admin/users");
  const structured = response.structuredContent as { users?: UserRecord[] } | undefined;
  return Array.isArray(structured?.users) ? structured.users : [];
}

export async function adminListWorkspaces(): Promise<WorkspaceRecord[]> {
  const response = await authorizedGetJson<LobbyResponse>("/admin/workspaces");
  const structured = response.structuredContent as { workspaces?: WorkspaceRecord[] } | undefined;
  return Array.isArray(structured?.workspaces) ? structured.workspaces : [];
}

export async function adminGetWorkspace(workspaceId: string): Promise<AdminWorkspaceDetail> {
  const response = await authorizedGetJson<LobbyResponse>(`/admin/workspaces/${encodeURIComponent(workspaceId)}/detail`);
  const structured = response.structuredContent as AdminWorkspaceDetail | undefined;
  if (!structured?.workspace || typeof structured.workspace.workspace_id !== "string") {
    throw new Error("Unable to load workspace detail.");
  }
  return structured;
}

export async function adminCreateUser(payload: {
  name: string;
  display_name: string;
  pin_code: string;
  face_photo_data?: string;
}): Promise<LobbyResponse> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  return postJson<LobbyResponse>("/admin/users", payload, { "X-Session-Id": sessionId });
}

export async function adminGetUser(userId: string): Promise<AdminUserDetail> {
  const response = await authorizedGetJson<LobbyResponse>(`/admin/users/${encodeURIComponent(userId)}`);
  const structured = response.structuredContent as AdminUserDetail | undefined;
  if (!structured?.user || typeof structured.user.user_id !== "string") {
    throw new Error("Unable to load user detail.");
  }
  return structured;
}

export async function adminDeleteUser(userId: string): Promise<LobbyResponse> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  return (await response.json()) as LobbyResponse;
}

export async function adminDeleteWorkspace(workspaceId: string): Promise<LobbyResponse> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout(`/admin/workspaces/${encodeURIComponent(workspaceId)}/delete`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  return (await response.json()) as LobbyResponse;
}

export async function adminRestoreWorkspace(workspaceId: string): Promise<LobbyResponse> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout(`/admin/workspaces/${encodeURIComponent(workspaceId)}/restore`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  return (await response.json()) as LobbyResponse;
}

export async function adminLoadTranscript(userId: string, targetSessionId: string, limit = 400): Promise<TranscriptEntry[]> {
  const response = await authorizedGetJson<LobbyResponse>(
    `/admin/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(targetSessionId)}/transcript?limit=${limit}`,
  );
  const structured = response.structuredContent as { entries?: TranscriptEntry[] } | undefined;
  return Array.isArray(structured?.entries) ? structured.entries : [];
}
