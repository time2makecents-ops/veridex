import type { FormEvent } from "react";

import type { Message } from "./types";

type NavigatorPanelProps = {
  draft: string;
  error: string;
  loading: boolean;
  messages: Message[];
  onClose: () => void;
  onDraftChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function NavigatorPanel({
  draft,
  error,
  loading,
  messages,
  onClose,
  onDraftChange,
  onSubmit,
}: NavigatorPanelProps) {
  return (
    <section className="navigator-panel" aria-label="Navigator chat">
      <div className="navigator-panel-header">
        <div>
          <div className="chat-role navigator-role">
            <strong>Navigator</strong>
          </div>
          <div className="navigator-panel-title">Governance chat</div>
        </div>
        <button type="button" className="ghost navigator-panel-close" onClick={onClose} aria-label="Close Navigator chat">
          Close
        </button>
      </div>

      <div className="navigator-panel-log">
        {messages.length ? (
          messages.map((message) => (
            <article key={message.id} className={`navigator-panel-message navigator-panel-message-${message.role}`}>
              <div className="chat-role">{message.role === "user" ? "You" : message.speaker || "Navigator"}</div>
              <div className="chat-text">{message.text}</div>
            </article>
          ))
        ) : (
          <div className="muted">Ask Navigator for diagnostics, safe checks, or routing guidance.</div>
        )}
        {loading ? <div className="muted">Navigator is checking...</div> : null}
      </div>

      {error ? <div className="error">{error}</div> : null}

      <form className="navigator-panel-composer" onSubmit={onSubmit}>
        <textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="Ask Navigator..."
          rows={3}
        />
        <button type="submit" className="primary" disabled={loading || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
