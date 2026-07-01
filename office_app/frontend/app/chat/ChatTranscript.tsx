import type { RefObject } from "react";

import type { ChatScope, Message } from "./types";

type ChatTranscriptProps = {
  activePersona: string;
  activeRoom: string;
  backendBanner: string;
  chatScope: ChatScope;
  confirmedIntegrationIds: string[];
  confirmingIntegrationId: string;
  error: string;
  loading: boolean;
  logRef: RefObject<HTMLDivElement>;
  messages: Message[];
  roomStatus: string;
  sessionId: string;
  onChatScopeChange: (scope: ChatScope) => void;
  onConfirmIntegration: (confirmationId: string, room: string, targetSessionId: string) => void;
};

export function ChatTranscript({
  activePersona,
  activeRoom,
  backendBanner,
  chatScope,
  confirmedIntegrationIds,
  confirmingIntegrationId,
  error,
  loading,
  logRef,
  messages,
  roomStatus,
  sessionId,
  onChatScopeChange,
  onConfirmIntegration,
}: ChatTranscriptProps) {
  return (
    <>
      <div className="terminal-panel-title">Chat Window</div>
      <div className="room-status-bar">{roomStatus}</div>
      {backendBanner ? <div className="backend-banner">{backendBanner}</div> : null}
      <div className="toolbar-row" style={{ marginBottom: 10 }}>
        <button
          type="button"
          className={`ghost toolbar-button ${chatScope === "room" ? "toolbar-button-active" : ""}`}
          onClick={() => onChatScopeChange("room")}
        >
          Room Chat
        </button>
        <button
          type="button"
          className={`ghost toolbar-button ${chatScope === "global" ? "toolbar-button-active" : ""}`}
          onClick={() => onChatScopeChange("global")}
        >
          Global Chat
        </button>
      </div>
      <section ref={logRef} className="chat lobby-chat-window">
        {messages.map((message) => {
          const speakerLabel = message.role === "user" ? "You" : message.role === "system" ? "System" : message.speaker || activePersona;
          const isNavigator = message.role === "assistant" && speakerLabel === "Navigator";
          return (
            <div key={message.id} className={`bubble ${message.role === "system" ? "assistant" : message.role}`}>
              <div className={`chat-role ${isNavigator ? "navigator-role" : ""}`}>
                {isNavigator ? <strong>Navigator</strong> : speakerLabel}
              </div>
              <div className="chat-text">{message.text}</div>
              {message.confirmationId ? (
                <button
                  type="button"
                  className="primary"
                  disabled={confirmingIntegrationId === message.confirmationId || confirmedIntegrationIds.includes(message.confirmationId)}
                  onClick={() => onConfirmIntegration(message.confirmationId || "", message.room || activeRoom, message.sessionId || sessionId)}
                >
                  {confirmedIntegrationIds.includes(message.confirmationId)
                    ? "Sent"
                    : confirmingIntegrationId === message.confirmationId
                      ? "Sending..."
                      : message.confirmationLabel || "Confirm"}
                </button>
              ) : null}
            </div>
          );
        })}
        {loading ? <div className="muted">Processing...</div> : null}
      </section>
      {error ? <div className="error">{error}</div> : null}
    </>
  );
}
