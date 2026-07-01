const SESSION_KEY = "veridex.session_id";

export function getStoredSessionId(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(SESSION_KEY) ?? "";
}

export function setStoredSessionId(sessionId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(SESSION_KEY, sessionId);
}

export function clearStoredSessionId(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(SESSION_KEY);
}

export function getSessionShortLabel(sessionId: string): string {
  if (!sessionId) {
    return "No session";
  }
  if (sessionId.length <= 12) {
    return sessionId;
  }
  return `${sessionId.slice(0, 6)}…${sessionId.slice(-4)}`;
}
