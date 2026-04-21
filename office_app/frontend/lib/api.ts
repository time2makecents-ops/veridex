export type LobbyResponse = {
  structuredContent?: {
    session_id?: string;
    workspace_id?: string;
    user?: {
      display_name?: string;
      name?: string;
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

function backendBaseUrl(): string {
  return process.env.NEXT_PUBLIC_VERIDEX_API_BASE_URL ?? "";
}

async function readResponseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail || payload.message || `Request failed with ${response.status}`;
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

export async function request(text: string): Promise<RequestResponse> {
  const sessionId = typeof window === "undefined" ? "" : window.localStorage.getItem("veridex.session_id") ?? "";
  if (!sessionId) {
    throw new Error("Session ID required");
  }
  const response = await fetchJsonWithTimeout("/request", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
    body: JSON.stringify({ text }),
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
        session_id: sessionId,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }

  return (await response.json()) as ToolResponse;
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
