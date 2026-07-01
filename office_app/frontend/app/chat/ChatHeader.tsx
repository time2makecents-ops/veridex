import type { UserRecord } from "@/lib/api";

import type { ProviderBadge } from "./types";

type ChatHeaderProps = {
  currentSessionDescription: string;
  currentSessionTitle: string;
  currentTitle: string;
  currentUser: UserRecord | null;
  currentWorkspaceLabel: string;
  providerBadge: ProviderBadge | null;
  sessionId: string;
  workspaceMenuOpen: boolean;
  onAdminOpen: () => void;
  onProfileOpen: () => void;
  onWorkspaceMenuToggle: () => void;
};

export function ChatHeader({
  currentSessionDescription,
  currentSessionTitle,
  currentTitle,
  currentUser,
  currentWorkspaceLabel,
  providerBadge,
  sessionId,
  workspaceMenuOpen,
  onAdminOpen,
  onProfileOpen,
  onWorkspaceMenuToggle,
}: ChatHeaderProps) {
  return (
    <div className="lobby-title-row">
      <div className="stack" style={{ gap: 4 }}>
        <div className="terminal-label">Veridex</div>
        {providerBadge ? (
          <div className={`provider-badge ${providerBadge.fallbackUsed ? "provider-badge-fallback" : ""}`}>
            {providerBadge.provider}
            {providerBadge.fallbackUsed ? " fallback" : ""}
          </div>
        ) : null}
        <h1 className="title">{currentTitle}</h1>
        <div className="muted">{currentSessionDescription || "No session description yet."}</div>
      </div>
      <div className="session-inline">
        <button type="button" className="option-button admin-link-button" onClick={onProfileOpen}>
          Profile
        </button>
        {currentUser?.is_admin ? (
          <button type="button" className="option-button admin-link-button" onClick={onAdminOpen}>
            Admin
          </button>
        ) : null}
        <button
          type="button"
          className={`ghost workspace-inline ${workspaceMenuOpen ? "toolbar-button-active" : ""}`}
          onClick={onWorkspaceMenuToggle}
        >
          <span className="workspace-inline-label">Workspace</span>
          <span className="workspace-inline-value">{currentWorkspaceLabel}</span>
        </button>
        <div className="workspace-inline">
          <span className="workspace-inline-label">Session</span>
          <span className="workspace-inline-value">{currentSessionTitle}</span>
        </div>
        <div className="muted">{sessionId}</div>
      </div>
    </div>
  );
}
