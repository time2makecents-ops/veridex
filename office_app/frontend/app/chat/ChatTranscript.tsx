import type { RefObject } from "react";

import { shouldShowMessageText } from "./helpers";
import type { ChatScope, ContactRecord, EmailReview, GmailMessageDetail, GmailMessageSummary, Message } from "./types";

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
  onEmailContact: (contact: ContactRecord, room: string, targetSessionId: string) => void;
  onOpenGmailThread: (message: GmailMessageSummary, room: string, targetSessionId: string) => void;
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
  onEmailContact,
  onOpenGmailThread,
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
