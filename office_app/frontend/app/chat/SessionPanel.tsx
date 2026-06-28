import type { SessionRecord } from "@/lib/api";

import { roomById } from "./helpers";

type SessionPanelProps = {
  deletingSessionId: string;
  sessionActionNotice: string;
  sessionDescriptionDraft: string;
  sessionId: string;
  sessions: SessionRecord[];
  sessionsLoading: boolean;
  sessionTitleDraft: string;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onSessionDescriptionDraftChange: (value: string) => void;
  onSessionSelect: (sessionId: string) => void;
  onSessionTitleDraftChange: (value: string) => void;
};

type SessionNamePromptProps = {
  sessionDescriptionDraft: string;
  sessionPromptTargetId: string;
  sessionTitleDraft: string;
  onCancelSessionNamePrompt: () => void;
  onSaveSessionNamePrompt: () => void;
  onSessionDescriptionDraftChange: (value: string) => void;
  onSessionTitleDraftChange: (value: string) => void;
};

export function SessionPanel({
  deletingSessionId,
  sessionActionNotice,
  sessionDescriptionDraft,
  sessionId,
  sessions,
  sessionsLoading,
  sessionTitleDraft,
  onCreateSession,
  onDeleteSession,
  onSessionDescriptionDraftChange,
  onSessionSelect,
  onSessionTitleDraftChange,
}: SessionPanelProps) {
  return (
    <div className="dropdown-panel">
      <div className="dropdown-group">
        <div className="dropdown-group-title">Current Sessions</div>
        {sessionActionNotice ? <div className="muted session-action-notice">{sessionActionNotice}</div> : null}
        <div className="dropdown-grid">
          {sessionsLoading ? <div className="muted">Loading sessions...</div> : null}
          {sessions.map((session) => (
            <div key={session.session_id} className="session-list-row">
              <button
                type="button"
                className={`ghost room-option ${String(session.session_id) === sessionId ? "toolbar-button-active" : ""}`}
                onClick={() => onSessionSelect(session.session_id)}
                disabled={deletingSessionId === session.session_id}
              >
                <span>{session.title || session.session_id}</span>
                <span className="room-option-persona">
                  {session.description || "No description"}
                  {session.active_room ? ` - ${roomById(String(session.active_room))?.title || session.active_room}` : ""}
                </span>
              </button>
              <button
                type="button"
                className="ghost session-delete-button"
                aria-label={`Delete session ${session.title || session.session_id}`}
                title="Delete session"
                disabled={deletingSessionId === session.session_id}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  onDeleteSession(session.session_id);
                }}
              >
                x
              </button>
            </div>
          ))}
          {!sessionsLoading && !sessions.length ? <div className="muted">No sessions yet.</div> : null}
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">New Session</div>
        <div className="toolbar-stack">
          <input
            className="session-input"
            type="text"
            value={sessionTitleDraft}
            placeholder="Event Flier"
            onChange={(event) => onSessionTitleDraftChange(event.target.value)}
          />
          <textarea
            className="session-input session-description"
            value={sessionDescriptionDraft}
            placeholder="Describe this work thread"
            onChange={(event) => onSessionDescriptionDraftChange(event.target.value)}
            rows={3}
          />
          <div className="toolbar-row">
            <button type="button" className="primary" onClick={onCreateSession}>
              Create Session
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function SessionNamePrompt({
  sessionDescriptionDraft,
  sessionPromptTargetId,
  sessionTitleDraft,
  onCancelSessionNamePrompt,
  onSaveSessionNamePrompt,
  onSessionDescriptionDraftChange,
  onSessionTitleDraftChange,
}: SessionNamePromptProps) {
  if (!sessionPromptTargetId) {
    return null;
  }

  return (
    <div className="session-name-overlay" role="dialog" aria-modal="true" aria-label="Name new session">
      <div className="session-name-modal">
        <div className="dropdown-group-title">Name new session</div>
        <div className="muted">The current workspace created a fresh session. Give it a title before continuing.</div>
        <div className="toolbar-stack">
          <input
            className="session-input"
            type="text"
            value={sessionTitleDraft}
            placeholder="Session title"
            onChange={(event) => onSessionTitleDraftChange(event.target.value)}
            autoFocus
          />
          <textarea
            className="session-input session-description"
            value={sessionDescriptionDraft}
            placeholder="Optional description"
            onChange={(event) => onSessionDescriptionDraftChange(event.target.value)}
            rows={3}
          />
          <div className="toolbar-row">
            <button type="button" className="secondary" onClick={onCancelSessionNamePrompt}>
              Keep New Session
            </button>
            <button type="button" className="primary" onClick={onSaveSessionNamePrompt}>
              Save Name
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
