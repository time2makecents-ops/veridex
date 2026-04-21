"use client";

import Image from "next/image";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { callTool, request, requestText } from "@/lib/api";
import {
  lobbyTerminalConfig,
  regionStyle,
  regionVisible,
  textStyleToCss,
  type LobbyTerminalMode,
} from "@/lib/lobby-terminal-config";
import LobbyTerminalCalibrationEditor from "@/components/LobbyTerminalCalibrationEditor";
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
  const [inputMode, setInputMode] = useState<LobbyTerminalMode>(lobbyTerminalConfig.defaultMode);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [switchingRoom, setSwitchingRoom] = useState<string>("");
  const [showConfig, setShowConfig] = useState(true);
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
        setInputMode(
          String((structured as { input_mode?: LobbyTerminalMode; inputMode?: LobbyTerminalMode }).input_mode ||
            (structured as { input_mode?: LobbyTerminalMode; inputMode?: LobbyTerminalMode }).inputMode ||
            lobbyTerminalConfig.defaultMode) as LobbyTerminalMode,
        );
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
      setInputMode(
        String(
          (response.structuredContent as { input_mode?: LobbyTerminalMode; inputMode?: LobbyTerminalMode } | undefined)
            ?.input_mode ||
            (response.structuredContent as { input_mode?: LobbyTerminalMode; inputMode?: LobbyTerminalMode } | undefined)
              ?.inputMode ||
            lobbyTerminalConfig.defaultMode,
        ) as LobbyTerminalMode,
      );
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
    <main
      className="screen lobby-page"
      data-session={sessionLabel}
      data-workspace={workspaceId}
      data-room={activeRoom}
      data-persona={activePersona}
    >
      <section className={`lobby-terminal ${showConfig ? "lobby-terminal-scrollable" : "lobby-terminal-fixed"}`}>
        <div className="lobby-terminal-image-wrap lobby-terminal-frame-wrap">
          <Image
            src={lobbyTerminalConfig.frameAsset}
            alt={lobbyTerminalConfig.name}
            fill
            priority
            sizes="100vw"
            className="lobby-terminal-image lobby-terminal-frame-image"
          />
          {regionVisible(lobbyTerminalConfig.regions.mainDisplay, inputMode) ? (
            <div
              className="lobby-terminal-region lobby-terminal-region-mainDisplay"
              style={{
                ...regionStyle(lobbyTerminalConfig.regions.mainDisplay, inputMode),
                ...textStyleToCss(lobbyTerminalConfig.textStyle),
              }}
            >
              <section ref={logRef} className="chat lobby-terminal-chat lobby-terminal-main-chat">
                {messages.map((message) => (
                  <div key={message.id} className="stack" style={{ gap: 4 }}>
                    <div className="muted lobby-terminal-speaker">{message.role === "user" ? "You" : "Receptionist"}</div>
                    <div className="lobby-terminal-bubble lobby-terminal-main-bubble">{message.text}</div>
                  </div>
                ))}
                {loading ? <div className="muted lobby-terminal-speaker">Processing...</div> : null}
              </section>
            </div>
          ) : null}

          {inputMode === "text" && regionVisible(lobbyTerminalConfig.regions.textInput, inputMode) ? (
            <form
              className="lobby-terminal-region lobby-terminal-region-textInput"
              style={{
                ...regionStyle(lobbyTerminalConfig.regions.textInput, inputMode),
                ...textStyleToCss(lobbyTerminalConfig.textStyle),
              }}
              onSubmit={handleSubmit}
            >
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
          ) : null}

          {inputMode === "pin" && regionVisible(lobbyTerminalConfig.regions.pinDots, inputMode) ? (
            <div
              className="lobby-terminal-region lobby-terminal-region-pinDots"
              style={regionStyle(lobbyTerminalConfig.regions.pinDots, inputMode)}
            >
              <div className="lobby-terminal-pin-dots">
                {Array.from({ length: lobbyTerminalConfig.pinStyle.pinLength }).map((_, index) => (
                  <span key={index} className="lobby-terminal-pin-dot" />
                ))}
              </div>
            </div>
          ) : null}

          {inputMode === "pin" && regionVisible(lobbyTerminalConfig.regions.keypadOverlay, inputMode) ? (
            <div
              className="lobby-terminal-region lobby-terminal-region-keypadOverlay"
              style={regionStyle(lobbyTerminalConfig.regions.keypadOverlay, inputMode)}
            >
              <div className="lobby-terminal-keypad-hint">PIN keypad will render here.</div>
            </div>
          ) : null}
        </div>

        {error ? <div className="error lobby-terminal-error">{error}</div> : null}
      </section>

      <section className="card lobby-config-toggle">
        <div className="stack">
          <div className="terminal-label">Layout controls</div>
          <p className="muted">Use the embedded config panel below to move and resize overlay regions.</p>
          <button type="button" className="primary" onClick={() => setShowConfig((current) => !current)}>
            {showConfig ? "Hide config" : "Show config"}
          </button>
        </div>
      </section>

      {showConfig ? (
        <section className="lobby-inline-config">
          <LobbyTerminalCalibrationEditor />
        </section>
      ) : null}
    </main>
  );
}
