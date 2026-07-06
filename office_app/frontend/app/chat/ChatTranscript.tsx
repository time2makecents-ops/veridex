import type { RefObject } from "react";

import { activeWorkContextNoticeText, pendingBreakRoomJokeNotice, pendingNancyComposeNotice, pendingRoomNavigationNotice, pendingSessionListNotice, pendingWorkspaceSwitchNotice, shouldShowMessageText, workContextCancellationLabel, workContextConfirmationAssistantPersona, workContextConfirmationId, workContextConfirmationLabel } from "./helpers";
import type { ChatScope, ContactRecord, EmailReview, GmailMessageDetail, GmailMessageSummary, Message, NancyEmailComposeState, PendingBreakRoomJokeState, PendingRoomNavigationState, PendingSessionListState, PendingWorkspaceSwitchState, WorkContextRecord } from "./types";

type ChatTranscriptProps = {
  activePersona: string;
  activeRoom: string;
  activeWorkContexts: WorkContextRecord[];
  backendBanner: string;
  chatScope: ChatScope;
  completedWorkContextIds: string[];
  completingWorkContextId: string;
  confirmedIntegrationIds: string[];
  confirmingIntegrationId: string;
  error: string;
  loading: boolean;
  logRef: RefObject<HTMLDivElement>;
  messages: Message[];
  nancyMode: boolean;
  pendingNancyCompose?: NancyEmailComposeState;
  pendingBreakRoomJoke?: PendingBreakRoomJokeState;
  pendingRoomNavigation?: PendingRoomNavigationState;
  pendingSessionList?: PendingSessionListState;
  pendingWorkspaceSwitch?: PendingWorkspaceSwitchState;
  roomStatus: string;
  sessionId: string;
  onChatScopeChange: (scope: ChatScope) => void;
  onConfirmIntegration: (confirmationId: string, room: string, targetSessionId: string, assistantPersona?: string) => void;
  onCancelIntegration: (confirmationId: string, room: string, targetSessionId: string, assistantPersona?: string) => void;
  onEmailContact: (contact: ContactRecord, room: string, targetSessionId: string) => void;
  onEnableNancyMode: () => void;
  onRevealBreakRoomPunchline: () => void;
  onDismissBreakRoomJoke: () => void;
  onKeepCurrentRoom: () => void;
  onKeepSessionListPending: () => void;
  onKeepCurrentWorkspace: () => void;
  onOpenGmailThread: (message: GmailMessageSummary, room: string, targetSessionId: string) => void;
  onCompleteWorkContext: (contextId: string, activeIndex: number, room: string, targetSessionId: string) => void;
  onSwitchRoomNow: () => void;
  onShowSessionListNow: () => void;
  onSwitchWorkspaceNow: () => void;
};

function GmailSummaryCard({ message, onOpen }: { message: GmailMessageSummary; onOpen: (message: GmailMessageSummary) => void }) {
  return (
    <button type="button" className="gmail-card gmail-card-button" onClick={() => onOpen(message)}>
      <div className="gmail-card-topline">
        <span className="gmail-card-index">{message.index || ""}</span>
        <span className="gmail-card-from">{message.from || "Unknown sender"}</span>
      </div>
      <div className="gmail-card-subject">{message.subject || "(no subject)"}</div>
      {message.date ? <div className="gmail-card-date">{message.date}</div> : null}
      {message.snippet ? <div className="gmail-card-snippet">{message.snippet}</div> : null}
    </button>
  );
}

function GmailDetailCard({ message }: { message: GmailMessageDetail }) {
  return (
    <article className="gmail-card gmail-card-detail">
      <div className="gmail-card-topline">
        <span className="gmail-card-from">{message.from || "Unknown sender"}</span>
      </div>
      {message.to ? <div className="gmail-card-date">To: {message.to}</div> : null}
      <div className="gmail-card-subject">{message.subject || "(no subject)"}</div>
      {message.date ? <div className="gmail-card-date">{message.date}</div> : null}
      {message.body_text ? <pre className="gmail-card-body">{message.body_text}</pre> : null}
    </article>
  );
}

function ContactCard({ contact, onEmail }: { contact: ContactRecord; onEmail: (contact: ContactRecord) => void }) {
  const label = contact.display_name || contact.email || "Unnamed contact";
  const aliases = Array.isArray(contact.aliases) ? contact.aliases.filter(Boolean).join(", ") : "";
  return (
    <article className="contact-card">
      <div className="contact-card-name">{label}</div>
      <div className="contact-card-email">{contact.email}</div>
      {aliases ? <div className="contact-card-meta">Aliases: {aliases}</div> : null}
      {contact.source ? <div className="contact-card-meta">Source: {contact.source}</div> : null}
      <div className="contact-card-actions">
        <button type="button" className="ghost contact-card-action" onClick={() => onEmail(contact)}>
          Email
        </button>
      </div>
    </article>
  );
}

function EmailReviewCard({ review }: { review: EmailReview }) {
  return (
    <article className="email-review-card">
      <div className="email-review-row">
        <span>To</span>
        <strong>{review.to.join(", ")}</strong>
      </div>
      <div className="email-review-row">
        <span>Subject</span>
        <strong>{review.subject || "(no subject)"}</strong>
      </div>
      <pre className="email-review-body">{review.body}</pre>
    </article>
  );
}

function WorkContextCard({
  context,
  completed,
  completing,
  index,
  onComplete,
  onConfirmIntegration,
  onCancelIntegration,
}: {
  context: WorkContextRecord;
  completed: boolean;
  completing: boolean;
  index: number;
  onComplete: (contextId: string, index: number) => void;
  onConfirmIntegration: (confirmationId: string, room: string, targetSessionId: string, assistantPersona?: string) => void;
  onCancelIntegration: (confirmationId: string, room: string, targetSessionId: string, assistantPersona?: string) => void;
}) {
  const active = String(context.status || "").toLowerCase() === "active" && !completed;
  const location = [context.active_room, context.active_persona].filter(Boolean).join(" / ");
  const confirmationId = workContextConfirmationId(context);
  const confirmationLabel = workContextConfirmationLabel(context);
  const cancellationLabel = workContextCancellationLabel(context);
  const confirmationAssistantPersona = workContextConfirmationAssistantPersona(context);
  const hasConfirmation = Boolean(confirmationId && active);
  const targetSessionId = String(context.session_id || "").trim();
  const targetRoom = String(context.active_room || "").trim();
  return (
    <article className="work-context-card">
      <div className="work-context-topline">
        <span className="work-context-index">{index}</span>
        <strong>{context.title || "Untitled work"}</strong>
      </div>
      {context.summary ? <div className="work-context-summary">{context.summary}</div> : null}
      {location ? <div className="work-context-meta">{location}</div> : null}
      <div className="work-context-actions">
        {hasConfirmation ? (
          <>
            <button
              type="button"
              className="primary work-context-action"
              onClick={() => onConfirmIntegration(confirmationId, targetRoom, targetSessionId, confirmationAssistantPersona)}
            >
              {confirmationLabel}
            </button>
            <button
              type="button"
              className="ghost work-context-action"
              onClick={() => onCancelIntegration(confirmationId, targetRoom, targetSessionId, confirmationAssistantPersona)}
            >
              {cancellationLabel}
            </button>
          </>
        ) : null}
        {!hasConfirmation ? (
          <button type="button" className="ghost work-context-action" disabled={!active || completing} onClick={() => onComplete(context.context_id || "", index)}>
            {completing ? "Completing..." : active ? "Done" : "Completed"}
          </button>
        ) : null}
      </div>
    </article>
  );
}

export function ChatTranscript({
  activePersona,
  activeRoom,
  activeWorkContexts,
  backendBanner,
  chatScope,
  completedWorkContextIds,
  completingWorkContextId,
  confirmedIntegrationIds,
  confirmingIntegrationId,
  error,
  loading,
  logRef,
  messages,
  nancyMode,
  pendingNancyCompose,
  pendingBreakRoomJoke,
  pendingRoomNavigation,
  pendingSessionList,
  pendingWorkspaceSwitch,
  roomStatus,
  sessionId,
  onChatScopeChange,
  onCancelIntegration,
  onConfirmIntegration,
  onEmailContact,
  onEnableNancyMode,
  onRevealBreakRoomPunchline,
  onDismissBreakRoomJoke,
  onKeepCurrentRoom,
  onKeepSessionListPending,
  onKeepCurrentWorkspace,
  onOpenGmailThread,
  onCompleteWorkContext,
  onSwitchRoomNow,
  onShowSessionListNow,
  onSwitchWorkspaceNow,
}: ChatTranscriptProps) {
  const nancyComposeNotice = pendingNancyComposeNotice(pendingNancyCompose);
  const showNancyComposePanel = Boolean(String(pendingNancyCompose?.stage || "").trim());
  const needsNancyRoutingHint = activeRoom !== "my_office" && !nancyMode;
  const roomNavigationNotice = pendingRoomNavigationNotice(pendingRoomNavigation);
  const showRoomNavigationPanel = Boolean(roomNavigationNotice);
  const sessionListNotice = pendingSessionListNotice(pendingSessionList);
  const showSessionListPanel = Boolean(sessionListNotice);
  const workspaceSwitchNotice = pendingWorkspaceSwitchNotice(pendingWorkspaceSwitch);
  const showWorkspaceSwitchPanel = Boolean(workspaceSwitchNotice);
  const breakRoomJokeNotice = pendingBreakRoomJokeNotice(pendingBreakRoomJoke);
  const showBreakRoomJokePanel = Boolean(breakRoomJokeNotice);
  return (
    <>
      <div className="terminal-panel-title">Chat Window</div>
      <div className="room-status-bar">{roomStatus}</div>
      {backendBanner ? <div className="backend-banner">{backendBanner}</div> : null}
      {activeWorkContexts.length ? (
        <section className="active-work-context-strip">
          <div className="active-work-context-label">{activeWorkContextNoticeText(activeWorkContexts)}</div>
          <div className="work-context-card-list active-work-context-list">
            {activeWorkContexts.map((context, index) => (
              <WorkContextCard
                key={context.context_id || `${index}`}
                context={context}
                completed={Boolean(context.context_id && completedWorkContextIds.includes(context.context_id))}
                completing={Boolean(context.context_id && completingWorkContextId === context.context_id)}
                index={index + 1}
                onComplete={(contextId, activeIndex) => onCompleteWorkContext(contextId, activeIndex, activeRoom, sessionId)}
                onConfirmIntegration={(confirmationId, room, targetSessionId) =>
                  onConfirmIntegration(confirmationId, room || activeRoom, targetSessionId || sessionId)
                }
                onCancelIntegration={(confirmationId, room, targetSessionId, assistantPersona) =>
                  onCancelIntegration(confirmationId, room || activeRoom, targetSessionId || sessionId, assistantPersona)
                }
              />
            ))}
          </div>
        </section>
      ) : null}
      {showNancyComposePanel ? (
        <section className="active-work-context-strip">
          <div className="active-work-context-label">Nancy draft in progress</div>
          <div className="work-context-card-list active-work-context-list">
            <article className="work-context-card">
              <div className="work-context-summary">{nancyComposeNotice}</div>
              {pendingNancyCompose?.to ? <div className="work-context-meta">To: {pendingNancyCompose.to}</div> : null}
              {needsNancyRoutingHint ? <div className="work-context-meta">Use Nancy mode or start your next message with "Nancy," to continue from this room.</div> : null}
              {needsNancyRoutingHint ? (
                <div className="work-context-actions">
                  <button type="button" className="ghost work-context-action" onClick={onEnableNancyMode}>
                    Use Nancy
                  </button>
                </div>
              ) : null}
            </article>
          </div>
        </section>
      ) : null}
      {showBreakRoomJokePanel ? (
        <section className="active-work-context-strip">
          <div className="active-work-context-label">Break Room joke pending</div>
          <div className="work-context-card-list active-work-context-list">
            <article className="work-context-card">
              <div className="work-context-summary">{breakRoomJokeNotice}</div>
              <div className="work-context-actions">
                <button type="button" className="primary work-context-action" onClick={onRevealBreakRoomPunchline}>
                  Reveal Punchline
                </button>
                <button type="button" className="ghost work-context-action" onClick={onDismissBreakRoomJoke}>
                  Clear
                </button>
              </div>
            </article>
          </div>
        </section>
      ) : null}
      {showWorkspaceSwitchPanel ? (
        <section className="active-work-context-strip">
          <div className="active-work-context-label">Workspace switch pending</div>
          <div className="work-context-card-list active-work-context-list">
            <article className="work-context-card">
              <div className="work-context-summary">{workspaceSwitchNotice}</div>
              <div className="work-context-actions">
                <button type="button" className="primary work-context-action" onClick={onSwitchWorkspaceNow}>
                  Switch Now
                </button>
                <button type="button" className="ghost work-context-action" onClick={onKeepCurrentWorkspace}>
                  Stay Here
                </button>
              </div>
            </article>
          </div>
        </section>
      ) : null}
      {showRoomNavigationPanel ? (
        <section className="active-work-context-strip">
          <div className="active-work-context-label">Room move pending</div>
          <div className="work-context-card-list active-work-context-list">
            <article className="work-context-card">
              <div className="work-context-summary">{roomNavigationNotice}</div>
              <div className="work-context-actions">
                <button type="button" className="primary work-context-action" onClick={onSwitchRoomNow}>
                  Move Now
                </button>
                <button type="button" className="ghost work-context-action" onClick={onKeepCurrentRoom}>
                  Stay Here
                </button>
              </div>
            </article>
          </div>
        </section>
      ) : null}
      {showSessionListPanel ? (
        <section className="active-work-context-strip">
          <div className="active-work-context-label">Session list pending</div>
          <div className="work-context-card-list active-work-context-list">
            <article className="work-context-card">
              <div className="work-context-summary">{sessionListNotice}</div>
              <div className="work-context-actions">
                <button type="button" className="primary work-context-action" onClick={onShowSessionListNow}>
                  List Sessions
                </button>
                <button type="button" className="ghost work-context-action" onClick={onKeepSessionListPending}>
                  Not Now
                </button>
              </div>
            </article>
          </div>
        </section>
      ) : null}
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
              {shouldShowMessageText(message) ? <div className="chat-text">{message.text}</div> : null}
              {message.gmailMessages?.length ? (
                <div className="gmail-card-list">
                  {message.gmailMessages.map((gmailMessage) => (
                    <GmailSummaryCard
                      key={gmailMessage.id || `${gmailMessage.index}`}
                      message={gmailMessage}
                      onOpen={(selected) => onOpenGmailThread(selected, message.room || activeRoom, message.sessionId || sessionId)}
                    />
                  ))}
                </div>
              ) : null}
              {message.gmailMessage ? <GmailDetailCard message={message.gmailMessage} /> : null}
              {message.gmailThread?.length ? (
                <div className="gmail-card-list">
                  {message.gmailThread.map((gmailMessage) => (
                    <GmailDetailCard key={gmailMessage.id} message={gmailMessage} />
                  ))}
                </div>
              ) : null}
              {message.contacts?.length ? (
                <div className="contact-card-list">
                  {message.contacts.map((contact) => (
                    <ContactCard
                      key={contact.email || contact.display_name}
                      contact={contact}
                      onEmail={(selected) => onEmailContact(selected, message.room || activeRoom, message.sessionId || sessionId)}
                    />
                  ))}
                </div>
              ) : null}
              {message.emailReview ? <EmailReviewCard review={message.emailReview} /> : null}
              {message.workContexts?.length ? (
                <div className="work-context-card-list">
                  {message.workContexts.map((context, index) => (
                    <WorkContextCard
                      key={context.context_id || `${index}`}
                      context={context}
                      completed={Boolean(context.context_id && completedWorkContextIds.includes(context.context_id))}
                      completing={Boolean(context.context_id && completingWorkContextId === context.context_id)}
                      index={index + 1}
                      onComplete={(contextId, activeIndex) => onCompleteWorkContext(contextId, activeIndex, message.room || activeRoom, message.sessionId || sessionId)}
                      onConfirmIntegration={(confirmationId, room, targetSessionId, assistantPersona) =>
                        onConfirmIntegration(confirmationId, room || message.room || activeRoom, targetSessionId || message.sessionId || sessionId, assistantPersona)
                      }
                      onCancelIntegration={(confirmationId, room, targetSessionId, assistantPersona) =>
                        onCancelIntegration(confirmationId, room || message.room || activeRoom, targetSessionId || message.sessionId || sessionId, assistantPersona)
                      }
                    />
                  ))}
                </div>
              ) : null}
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
