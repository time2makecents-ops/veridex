"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  adminCreateUser,
  adminDeleteUser,
  adminDeleteWorkspace,
  adminGetUser,
  adminListUsers,
  adminListWorkspaces,
  adminLoadTranscript,
  getCurrentUser,
  type AdminUserDetail,
  type TranscriptEntry,
  type WorkspaceRecord,
  type UserRecord,
} from "@/lib/api";
import { getStoredSessionId } from "@/lib/session";

type DetailTab = "profile" | "sessions" | "artifacts";

function transcriptLine(entry: TranscriptEntry): string {
  const speaker = String(entry.speaker || entry.role || "Unknown").trim() || "Unknown";
  const text = String(entry.text || "").trim();
  return `${speaker}: ${text}`;
}

function artifactPreviewText(value: unknown): string {
  const text = String(value || "").trim();
  if (!text) {
    return "No preview available.";
  }
  return text.length > 220 ? `${text.slice(0, 217).trimEnd()}...` : text;
}

function workspaceStatusText(workspace: WorkspaceRecord): string {
  const status = String(workspace.status || "active").trim().toLowerCase();
  if (status === "archived") {
    const archivedAt = String(workspace.archived_at || "").trim();
    const deletedBy = String(workspace.deleted_by_user_id || "").trim();
    const parts = ["Archived"];
    if (deletedBy) {
      parts.push("Removed by user");
    }
    if (archivedAt) {
      parts.push(`Archived at ${archivedAt}`);
    }
    return parts.join(" - ");
  }
  return "Active";
}

export default function AdminPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("profile");
  const [selectedTranscriptSessionId, setSelectedTranscriptSessionId] = useState("");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [creatingUser, setCreatingUser] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState("");
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [createName, setCreateName] = useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createPin, setCreatePin] = useState("");

  useEffect(() => {
    const stored = getStoredSessionId();
    if (!stored) {
      router.replace("/");
      return;
    }
    setSessionId(stored);
  }, [router]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoadingUsers(true);
      setLoadingWorkspaces(true);
      setError("");
      try {
        const [user, allUsers, allWorkspaces] = await Promise.all([getCurrentUser(), adminListUsers(), adminListWorkspaces()]);
        if (cancelled) {
          return;
        }
        setCurrentUser(user);
        setUsers(allUsers);
        setWorkspaces(allWorkspaces);
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Unable to load admin tools.";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setLoadingUsers(false);
          setLoadingWorkspaces(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!selectedUserId || !detailOpen || !currentUser?.is_admin) {
      return;
    }
    let cancelled = false;
    const loadDetail = async () => {
      setLoadingDetail(true);
      setError("");
      try {
        const nextDetail = await adminGetUser(selectedUserId);
        if (cancelled) {
          return;
        }
        setDetail(nextDetail);
        const firstSessionId = String(nextDetail.sessions[0]?.session_id || "");
        setSelectedTranscriptSessionId(firstSessionId);
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Unable to load user detail.";
          setError(message);
          setDetail(null);
          setTranscript([]);
          setSelectedTranscriptSessionId("");
        }
      } finally {
        if (!cancelled) {
          setLoadingDetail(false);
        }
      }
    };
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [currentUser?.is_admin, detailOpen, selectedUserId]);

  useEffect(() => {
    if (!selectedUserId || !selectedTranscriptSessionId || !detailOpen || !currentUser?.is_admin) {
      setTranscript([]);
      return;
    }
    let cancelled = false;
    const loadTranscript = async () => {
      setLoadingTranscript(true);
      setError("");
      try {
        const entries = await adminLoadTranscript(selectedUserId, selectedTranscriptSessionId, 500);
        if (!cancelled) {
          setTranscript(entries);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Unable to load transcript.";
          setError(message);
          setTranscript([]);
        }
      } finally {
        if (!cancelled) {
          setLoadingTranscript(false);
        }
      }
    };
    void loadTranscript();
    return () => {
      cancelled = true;
    };
  }, [currentUser?.is_admin, detailOpen, selectedTranscriptSessionId, selectedUserId]);

  const selectedSessionTitle = useMemo(() => {
    const sessions = detail?.sessions || [];
    const match = sessions.find((session) => String(session.session_id) === selectedTranscriptSessionId);
    return match?.title || selectedTranscriptSessionId;
  }, [detail?.sessions, selectedTranscriptSessionId]);

  async function refreshAdminLists(preferredUserId?: string) {
    const [allUsers, allWorkspaces] = await Promise.all([adminListUsers(), adminListWorkspaces()]);
    setUsers(allUsers);
    setWorkspaces(allWorkspaces);
    if (preferredUserId && allUsers.some((user) => String(user.user_id) === preferredUserId)) {
      setSelectedUserId(preferredUserId);
      return;
    }
    if (selectedUserId && allUsers.some((user) => String(user.user_id) === selectedUserId)) {
      return;
    }
    setSelectedUserId("");
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingUser(true);
    setError("");
    setNotice("");
    try {
      const response = await adminCreateUser({
        name: createName.trim(),
        display_name: createDisplayName.trim(),
        pin_code: createPin.trim(),
      });
      const structured = response.structuredContent as { user?: UserRecord } | undefined;
      const createdUserId = String(structured?.user?.user_id || "");
      setCreateName("");
      setCreateDisplayName("");
      setCreatePin("");
      setNotice(`Created user ${structured?.user?.display_name || structured?.user?.name || "User"}.`);
      await refreshAdminLists(createdUserId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create user.";
      setError(message);
    } finally {
      setCreatingUser(false);
    }
  }

  function openUserDetail(userId: string) {
    setSelectedUserId(userId);
    setDetail(null);
    setTranscript([]);
    setSelectedTranscriptSessionId("");
    setDetailTab("profile");
    setDetailOpen(true);
    setError("");
  }

  function closeUserDetail() {
    setDetailOpen(false);
    setDetail(null);
    setTranscript([]);
    setSelectedTranscriptSessionId("");
    setSelectedUserId("");
  }

  async function handleDeleteUser(target: UserRecord) {
    const targetId = String(target.user_id || "");
    if (!targetId || deletingUserId === targetId) {
      return;
    }
    const targetName = target.display_name || target.name || targetId;
    if (!window.confirm(`Delete user "${targetName}" and all of their sessions, transcripts, and saved data?`)) {
      return;
    }
    setDeletingUserId(targetId);
    setError("");
    setNotice("");
    try {
      await adminDeleteUser(targetId);
      setNotice(`Deleted user ${targetName}.`);
      closeUserDetail();
      await refreshAdminLists();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to delete user.";
      setError(message);
    } finally {
      setDeletingUserId("");
    }
  }

  async function handleDeleteWorkspace(target: WorkspaceRecord) {
    const targetId = String(target.workspace_id || "");
    if (!targetId || deletingWorkspaceId === targetId) {
      return;
    }
    const targetName = target.label || target.workspace_id || targetId;
    if (String(target.status || "active").trim().toLowerCase() !== "archived") {
      setError("Workspace must be archived before hard delete.");
      return;
    }
    if (!window.confirm(`Hard delete archived workspace "${targetName}"? This cannot be undone.`)) {
      return;
    }
    setDeletingWorkspaceId(targetId);
    setError("");
    setNotice("");
    try {
      await adminDeleteWorkspace(targetId);
      setNotice(`Deleted workspace ${targetName}.`);
      await refreshAdminLists();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to delete workspace.";
      setError(message);
    } finally {
      setDeletingWorkspaceId("");
    }
  }

  async function handleOpenWorkspaceDetail(target: WorkspaceRecord) {
    const targetId = String(target.workspace_id || "");
    if (!targetId) {
      return;
    }
    router.push(`/admin/workspaces/${encodeURIComponent(targetId)}`);
  }

  return (
    <main className="admin-screen">
      <section className="admin-header">
        <div>
          <div className="terminal-label">Veridex</div>
          <h1 className="admin-title">Admin</h1>
          <p className="muted">Manage users, inspect transcripts, review saved artifacts, and remove accounts.</p>
        </div>
        <div className="admin-header-actions">
          <button type="button" className="option-button" onClick={() => router.push("/chat")}>
            Back to Chat
          </button>
        </div>
      </section>

      {error ? <div className="admin-banner admin-banner-error">{error}</div> : null}
      {notice ? <div className="admin-banner admin-banner-success">{notice}</div> : null}

      {!currentUser?.is_admin && !loadingUsers ? (
        <section className="admin-empty-state">
          <h2>Admin access required</h2>
          <p className="muted">This page is only available to the admin account.</p>
        </section>
      ) : (
        <div className="admin-shell">
          <section className="admin-panel admin-create-panel">
            <div className="admin-panel-header">
              <h2>Create User</h2>
            </div>
            <form className="admin-form" onSubmit={handleCreateUser}>
              <label>
                <span>Name</span>
                <input value={createName} onChange={(event) => setCreateName(event.target.value)} required />
              </label>
              <label>
                <span>Display name</span>
                <input value={createDisplayName} onChange={(event) => setCreateDisplayName(event.target.value)} required />
              </label>
              <label>
                <span>PIN</span>
                <input value={createPin} onChange={(event) => setCreatePin(event.target.value)} inputMode="numeric" pattern="\d{4}" required />
              </label>
              <button type="submit" className="option-button is-active" disabled={creatingUser}>
                {creatingUser ? "Creating..." : "Add User"}
              </button>
            </form>
          </section>

          <section className="admin-panel admin-users-panel">
            <div className="admin-panel-header">
              <h2>Users</h2>
              <span className="muted">{loadingUsers ? "Loading..." : `${users.length} total`}</span>
            </div>
            <div className="admin-user-list">
              {users.map((user) => {
                const userId = String(user.user_id || "");
                return (
                  <button
                    key={userId}
                    type="button"
                    className="admin-user-row"
                    onClick={() => openUserDetail(userId)}
                  >
                    <span className="admin-user-name">{user.display_name || user.name || userId}</span>
                    <span className="admin-user-meta">
                      {(user.role || "user").toUpperCase()} - {user.session_count || 0} session{Number(user.session_count || 0) === 1 ? "" : "s"}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="admin-panel admin-workspaces-panel">
            <div className="admin-panel-header">
              <h2>Workspaces</h2>
              <span className="muted">{loadingWorkspaces ? "Loading..." : `${workspaces.length} total`}</span>
            </div>
            <div className="admin-session-list">
              {workspaces.map((workspace) => {
                const workspaceId = String(workspace.workspace_id || "");
                const archived = String(workspace.status || "active").trim().toLowerCase() === "archived";
                return (
                  <div key={workspaceId} className="admin-session-row admin-static-row">
                    <div>
                      <div>{workspace.label || workspaceId}</div>
                      <div className="admin-session-meta">{workspaceId}</div>
                    </div>
                    <div className="admin-session-meta">
                      <div>{workspaceStatusText(workspace)}</div>
                      <div>{Number(workspace.session_count || 0)} session{Number(workspace.session_count || 0) === 1 ? "" : "s"}</div>
                    </div>
                    <div className="admin-inline-actions">
                      <button
                        type="button"
                        className="option-button"
                        onClick={() => void handleOpenWorkspaceDetail(workspace)}
                      >
                        View Workspace
                      </button>
                      <button
                        type="button"
                        className="option-button admin-danger-button"
                        onClick={() => void handleDeleteWorkspace(workspace)}
                        disabled={!archived || deletingWorkspaceId === workspaceId}
                      >
                        {deletingWorkspaceId === workspaceId ? "Deleting..." : archived ? "Hard Delete" : "Archived Only"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}

      {detailOpen ? (
        <div className="admin-modal-scrim" onClick={closeUserDetail}>
          <section className="admin-modal" role="dialog" aria-modal="true" aria-label="User detail" onClick={(event) => event.stopPropagation()}>
            <div className="admin-modal-header">
              <div>
                <div className="terminal-label">User Detail</div>
                <h2 className="admin-modal-title">
                  {detail?.user?.display_name || detail?.user?.name || selectedUserId || "User"}
                </h2>
              </div>
              <button type="button" className="option-button" onClick={closeUserDetail}>
                Close
              </button>
            </div>

            <div className="admin-tab-row">
              <button type="button" className={`option-button ${detailTab === "profile" ? "is-active" : ""}`} onClick={() => setDetailTab("profile")}>
                Profile
              </button>
              <button type="button" className={`option-button ${detailTab === "sessions" ? "is-active" : ""}`} onClick={() => setDetailTab("sessions")}>
                Sessions
              </button>
              <button type="button" className={`option-button ${detailTab === "artifacts" ? "is-active" : ""}`} onClick={() => setDetailTab("artifacts")}>
                Saved Artifacts
              </button>
            </div>

            {loadingDetail ? <p className="muted">Loading user detail...</p> : null}

            {!loadingDetail && detail?.user && detailTab === "profile" ? (
              <div className="admin-modal-body admin-modal-grid">
                <div className="admin-info-block">
                  <h3>Profile</h3>
                  <dl className="admin-kv">
                    <div><dt>User ID</dt><dd>{detail.user.user_id}</dd></div>
                    <div><dt>Name</dt><dd>{detail.user.name || "-"}</dd></div>
                    <div><dt>Display</dt><dd>{detail.user.display_name || "-"}</dd></div>
                    <div><dt>PIN</dt><dd>{detail.user.pin_code || "-"}</dd></div>
                    <div><dt>Role</dt><dd>{detail.user.role || "user"}</dd></div>
                    <div><dt>Default workspace</dt><dd>{detail.user.default_workspace_id || "-"}</dd></div>
                    <div><dt>Last workspace</dt><dd>{detail.user.last_active_workspace_id || "-"}</dd></div>
                    <div><dt>Last session</dt><dd>{detail.user.last_active_session_id || "-"}</dd></div>
                    <div><dt>Created</dt><dd>{detail.user.created_at || "-"}</dd></div>
                    <div><dt>Updated</dt><dd>{detail.user.updated_at || "-"}</dd></div>
                    <div><dt>Folder</dt><dd>{detail.user_folder || "-"}</dd></div>
                  </dl>
                  <div className="admin-inline-actions">
                    <button
                      type="button"
                      className="option-button admin-danger-button"
                      onClick={() => void handleDeleteUser(detail.user)}
                      disabled={deletingUserId === String(detail.user.user_id)}
                    >
                      {deletingUserId === String(detail.user.user_id) ? "Deleting..." : "Delete User"}
                    </button>
                  </div>
                </div>

                <div className="admin-info-block">
                  <h3>Workspaces</h3>
                  <div className="admin-session-list">
                    {detail.workspaces.map((workspace) => (
                      <div key={workspace.workspace_id} className="admin-session-row admin-static-row">
                        <div>
                          <div>{workspace.label || workspace.workspace_id}</div>
                          <div className="admin-session-meta">{workspace.workspace_id}</div>
                        </div>
                        <div className="admin-session-meta">
                          <div>{workspaceStatusText(workspace)}</div>
                          <div>
                            {Number(workspace.session_count || 0)} session{Number(workspace.session_count || 0) === 1 ? "" : "s"}
                          </div>
                        </div>
                        <div className="admin-inline-actions">
                          <button
                            type="button"
                            className="option-button"
                            onClick={() => void handleOpenWorkspaceDetail(workspace)}
                          >
                            View Workspace
                          </button>
                          <button
                            type="button"
                            className="option-button admin-danger-button"
                            onClick={() => void handleDeleteWorkspace(workspace)}
                            disabled={String(workspace.status || "active").trim().toLowerCase() !== "archived"}
                          >
                            {deletingWorkspaceId === workspace.workspace_id ? "Deleting..." : "Hard Delete"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {!loadingDetail && detail?.user && detailTab === "sessions" ? (
              <div className="admin-modal-body admin-modal-grid">
                <div className="admin-info-block">
                  <h3>Sessions</h3>
                  <div className="admin-session-list">
                    {detail.sessions.map((session) => {
                      const value = String(session.session_id || "");
                      const selected = value === selectedTranscriptSessionId;
                      return (
                        <button
                          key={value}
                          type="button"
                          className={`admin-session-row ${selected ? "is-selected" : ""}`}
                          onClick={() => setSelectedTranscriptSessionId(value)}
                        >
                          <span>{session.title || value}</span>
                          <span className="admin-session-meta">{session.active_workspace_id}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="admin-info-block">
                  <h3>Transcript</h3>
                  <div className="muted admin-subtitle">{selectedSessionTitle || "No session selected"}</div>
                  {loadingTranscript ? <p className="muted">Loading transcript...</p> : null}
                  {!loadingTranscript && transcript.length ? (
                    <pre className="admin-transcript">{transcript.map(transcriptLine).join("\n")}</pre>
                  ) : null}
                  {!loadingTranscript && !transcript.length ? <p className="muted">No transcript entries loaded.</p> : null}
                </div>
              </div>
            ) : null}

            {!loadingDetail && detail?.user && detailTab === "artifacts" ? (
              <div className="admin-modal-body">
                <div className="admin-artifact-list">
                  {(detail.artifacts || []).length ? (
                    (detail.artifacts || []).map((artifact) => (
                      <div key={`${artifact.workspace_id || "ws"}:${artifact.artifact_id}`} className="admin-artifact-card">
                        <div className="admin-artifact-title">{artifact.display_name || artifact.artifact_id}</div>
                        <div className="admin-artifact-meta">
                          {artifact.artifact_type || "artifact"} - {artifact.workspace_id || "workspace"}
                        </div>
                        <div className="admin-artifact-preview">{artifactPreviewText(artifact.content_preview)}</div>
                      </div>
                    ))
                  ) : (
                    <p className="muted">No saved artifacts found for this user.</p>
                  )}
                </div>
              </div>
            ) : null}

            {!loadingDetail && !detail?.user ? <p className="muted">Unable to load user detail.</p> : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}
