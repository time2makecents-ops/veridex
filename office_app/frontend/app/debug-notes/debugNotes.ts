export type DebugNoteRecord = {
  page_path: string;
  text: string;
  updated_at?: string;
  session_id?: string;
  workspace_id?: string;
  active_room?: string;
  active_persona?: string;
  note_key?: string;
  note_scope?: string;
};

export type DebugNotePayloadInput = {
  pagePath: string;
  text: string;
  sessionId?: string;
  workspaceId?: string;
  activeRoom?: string;
  activePersona?: string;
};

type DebugNoteResponse = {
  structuredContent?: DebugNoteRecord;
};

export function normalizeDebugPagePath(pagePath: string): string {
  let text = String(pagePath || "").trim();
  text = text.split(/[?#]/, 1)[0] || "";
  text = text.replace(/\/+/g, "/").replace(/[^A-Za-z0-9/_-]+/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
  if (!text) {
    return "/";
  }
  if (!text.startsWith("/")) {
    text = `/${text}`;
  }
  return text.length > 180 ? text.slice(0, 180).replace(/[\/_-]+$/g, "") || "/" : text;
}

export function debugNoteContextKey(pagePath: string, activeRoom?: string, activePersona?: string): string {
  const normalized = normalizeDebugPagePath(pagePath);
  const room = String(activeRoom || "").trim();
  const persona = String(activePersona || "").trim();
  if (normalized === "/chat" && room) {
    return `${normalized}|${room}|${persona}`;
  }
  return normalized;
}

export function buildDebugNotePayload(input: DebugNotePayloadInput): DebugNoteRecord {
  return {
    page_path: normalizeDebugPagePath(input.pagePath),
    text: input.text,
    session_id: String(input.sessionId || ""),
    workspace_id: String(input.workspaceId || ""),
    active_room: String(input.activeRoom || ""),
    active_persona: String(input.activePersona || ""),
  };
}

export function prepareDebugNoteForEditing(text: string): { text: string; selectionStart: number } {
  const current = String(text || "");
  const prepared = current.endsWith("\n\n") || !current ? current : `${current.replace(/\s+$/g, "")}\n\n`;
  return {
    text: prepared,
    selectionStart: prepared.length,
  };
}

async function readResponseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (typeof payload.message === "string") {
      return payload.message;
    }
  } catch {
    // Fall through to generic status message.
  }
  return `Request failed with ${response.status}`;
}

export async function fetchDebugNote(input: { pagePath: string; activeRoom?: string; activePersona?: string }): Promise<DebugNoteRecord> {
  const url = new URL("/debug-notes", window.location.origin);
  url.searchParams.set("page_path", normalizeDebugPagePath(input.pagePath));
  if (input.activeRoom) {
    url.searchParams.set("active_room", input.activeRoom);
  }
  if (input.activePersona) {
    url.searchParams.set("active_persona", input.activePersona);
  }
  const response = await fetch(url.pathname + url.search, { method: "GET" });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  const payload = (await response.json()) as DebugNoteResponse;
  return (
    payload.structuredContent || {
      page_path: normalizeDebugPagePath(input.pagePath),
      text: "",
    }
  );
}

export async function saveDebugNote(input: DebugNotePayloadInput): Promise<DebugNoteRecord> {
  const response = await fetch("/debug-notes", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildDebugNotePayload(input)),
  });
  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }
  const payload = (await response.json()) as DebugNoteResponse;
  return payload.structuredContent || buildDebugNotePayload(input);
}
