"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { callTool, request, requestText } from "@/lib/api";
import { clearStoredSessionId, getSessionShortLabel, getStoredSessionId } from "@/lib/session";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

type LobbyState = {
  workspace_id: string;
  active_room: string;
  active_persona: string;
};

export default function ChatPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [activeRoom, setActiveRoom] = useState("lobby");
  const [activePersona, setActivePersona] = useState("Receptionist");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [switchingRoom, setSwitchingRoom] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([
    { id: "welcome", role: "assistant", text: "Receptionist ready. How may I help you today?" },
  ]);
  const logRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const stored = getStoredSessionId();
    if (!stored) {
      router.replace("/");
      return;
    }
    setSessionId(stored);
  }, [router]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, switchingRoom]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    let cancelled = false;
    const loadState = async () => {
      try {
        const response = await callTool("office.state_get", {});
        const structured = response.structuredContent as LobbyState | undefined;
        if (cancelled || !structured) {
          return;
        }
        setWorkspaceId(String(structured.workspace_id || ""));
        setActiveRoom(String(structured.active_room || "lobby"));
        setActivePersona(String(structured.active_persona || "Receptionist"));
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to load lobby state.";
        setError(message);
        if (message.toLowerCase().includes("session")) {
          clearStoredSessionId();
          router.replace("/");
        }
      }
    };

    void loadState();
    return () => {
      cancelled = true;
    };
  }, [router, sessionId]);

  const sessionLabel = useMemo(() => getSessionShortLabel(sessionId), [sessionId]);

  async function sendText(text: string) {
    const value = text.trim();
    if (!value || loading) {
      return;
    }
    setDraft("");
    setError("");
    setLoading(true);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: value }]);
    try {
      const response = await request(value);
      const assistantText = requestText(response);
      setWorkspaceId(String(response.workspace_id || response.structuredContent?.workspace_id || workspaceId));
      setSessionId(String(response.session_id || response.structuredContent?.session_id || sessionId));
      setActiveRoom(String((response.structuredContent as { active_room?: string } | undefined)?.active_room || activeRoom));
      setActivePersona(String((response.structuredContent as { active_persona?: string } | undefined)?.active_persona || activePersona));
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: assistantText }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed.";
      setError(message);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: message }]);
      if (message.toLowerCase().includes("session")) {
        clearStoredSessionId();
        router.replace("/");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendText(draft);
  }

  return (
    <main className="screen lobby-page">
      <section className="terminal-shell stack">
        <div className="terminal-header">
          <div className="terminal-lens" />
          <div className="status" style={{ justifyContent: "flex-end" }}>
            <span className="pill">Session {sessionLabel}</span>
            <span className="pill">Workspace {workspaceId || "syncing"}</span>
            <span className="pill">Room {activeRoom}</span>
            <span className="pill">Persona {activePersona}</span>
          </div>
        </div>

        <div className="terminal-screen stack">
          <div className="terminal-label">VERIDEX LOBBY TERMINAL</div>
          <div className="terminal-title" style={{ color: "inherit", fontSize: "1.35rem", margin: 0 }}>
            Reception Desk
          </div>
          <div className="muted" style={{ marginBottom: 8 }}>
            You are speaking with the receptionist. Type below to continue.
          </div>

          <section ref={logRef} className="chat" style={{ maxHeight: "42dvh", minHeight: "42dvh" }}>
          {messages.map((message) => (
            <div key={message.id} className="stack" style={{ gap: 4 }}>
              <div className="muted" style={{ fontSize: "0.8rem", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                {message.role === "user" ? "You" : "Receptionist"}
              </div>
              <div
                className="card"
                style={{
                  padding: 14,
                  background: message.role === "user" ? "rgba(141, 253, 167, 0.12)" : "rgba(255, 255, 255, 0.03)",
                  color: "inherit",
                  borderColor: "rgba(141, 253, 167, 0.12)",
                }}
              >
                {message.text}
              </div>
            </div>
          ))}
          {loading ? <div className="muted">Processing...</div> : null}
          </section>

          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              ref={draftRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Speak to the receptionist..."
              rows={2}
            />
            <button className="primary" type="submit" disabled={loading || !draft.trim()}>
              Send
            </button>
          </form>

          {error ? <div className="error">{error}</div> : null}
        </div>
      </section>
    </main>
  );
}
