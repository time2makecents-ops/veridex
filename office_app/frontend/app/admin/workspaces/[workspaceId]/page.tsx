"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import {
  adminDeleteWorkspace,
  adminGetWorkspace,
  adminLoadTranscript,
  type AdminWorkspaceDetail,
  type ArtifactRecord,
  type FileRecord,
  type TranscriptEntry,
  type SessionRecord,
  type WorkspaceRecord,
} from "@/lib/api";
import { getStoredSessionId } from "@/lib/session";

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

function fileMeta(file: FileRecord): string {
  const parts = [file.scope || "workspace"];
  if (file.kind) {
    parts.push(file.kind);
  }
  if (file.byte_size) {
    parts.push(`${file.byte_size} bytes`);
  }
  return parts.join(" - ");
}

function artifactMeta(artifact: ArtifactRecord): string {
  const parts = [artifact.artifact_type || "artifact"];
  if (artifact.updated_at) {
    parts.push(`Updated ${artifact.updated_at}`);
  }
  return parts.join(" - ");
}

export default function AdminWorkspaceDetailPage() {
  const router = useRouter();
  const params = useParams<{ workspaceId: string }>();
  const workspaceId = useMemo(() => String(params?.workspaceId || "").trim(), [params?.workspaceId]);
  const [sessionId, setSessionId] = useState("");
  const [detail, setDetail] = useState<AdminWorkspaceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [selectedSessionUserId, setSelectedSessionUserId] = useState("");
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [loadingTranscript, setLoadingTranscript] = useState(false);

  useEffect(() => {
    const stored = getStoredSessionId();
    if (!stored) {
      router.replace("/");
      return;
    }
    setSessionId(stored);
  }, [router]);

  useEffect(() => {
    if (!sessionId || !workspaceId) {
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const nextDetail = await adminGetWorkspace(workspaceId);
        if (!cancelled) {
          setDetail(nextDetail);
          const firstSession = nextDetail.sessions[0];
          setSelectedSessionId(String(firstSession?.session_id || ""));
          setSelectedSessionUserId(String(firstSession?.user_id || ""));
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Unable to load workspace detail.";
          setError(message);
          setDetail(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId, workspaceId]);

  useEffect(() => {
    if (!detail?.workspace || !selectedSessionId || !selectedSessionUserId) {
      setTranscript([]);
      return;
    }
    let cancelled = false;
    const loadTranscript = async () => {
      setLoadingTranscript(true);
      setError("");
      try {
        const entries = await adminLoadTranscript(selectedSessionUserId, selectedSessionId, 500);
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
  }, [detail?.workspace, selectedSessionId, selectedSessionUserId]);

  async function handleDeleteWorkspace() {
    if (!detail?.workspace) {
      return;
    }
    const targetName = detail.workspace.label || detail.workspace.workspace_id || workspaceId;
    if (String(detail.workspace.status || "active").trim().toLowerCase() !== "archived") {
      setError("Workspace must be archived before hard delete.");
      return;
    }
    if (!window.confirm(`Hard delete archived workspace "${targetName}"? This cannot be undone.`)) {
      return;
    }
    setDeleting(true);
    setError("");
    setNotice("");
    try {
      await adminDeleteWorkspace(workspaceId);
      setNotice(`Deleted workspace ${targetName}.`);
      router.push("/admin");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to delete workspace.";
      setError(message);
    } finally {
      setDeleting(false);
    }
  }

  const workspace = detail?.workspace || null;
  const sessions = detail?.sessions || [];
  const artifacts = detail?.artifacts || [];
  const files = detail?.files || [];
  const selectedSessionTitle = sessions.find((session) => session.session_id === selectedSessionId)?.title || selectedSessionId;

  return (
    <main className="admin-shell">
      <div className="admin-panel">
        <div className="admin-panel-header">
          <div>
            <div className="terminal-label">Workspace Detail</div>
            <h2>{workspace?.label || workspaceId || "Workspace"}</h2>
            <div className="muted">{workspaceId || "No workspace selected"}</div>
          </div>
          <div className="admin-inline-actions">
            <button type="button" className="option-button" onClick={() => router.push("/admin")}>
              Back
            </button>
            <button
              type="button"
              className="option-button admin-danger-button"
              onClick={() => void handleDeleteWorkspace()}
              disabled={deleting || !workspace || String(workspace.status || "active").trim().toLowerCase() !== "archived"}
            >
              {deleting ? "Deleting..." : "Hard Delete"}
            </button>
          </div>
        </div>

        {error ? <div className="admin-error">{error}</div> : null}
        {notice ? <div className="admin-notice">{notice}</div> : null}
        {loading ? <p className="muted">Loading workspace detail...</p> : null}

        {!loading && workspace ? (
          <div className="admin-modal-grid">
            <div className="admin-info-block">
              <h3>Workspace</h3>
              <dl className="admin-kv">
                <div><dt>Workspace ID</dt><dd>{workspace.workspace_id}</dd></div>
                <div><dt>Label</dt><dd>{workspace.label || "-"}</dd></div>
                <div><dt>Description</dt><dd>{workspace.description || "-"}</dd></div>
                <div><dt>Status</dt><dd>{workspaceStatusText(workspace)}</dd></div>
                <div><dt>Created</dt><dd>{workspace.created_utc || "-"}</dd></div>
                <div><dt>Archived at</dt><dd>{workspace.archived_at || "-"}</dd></div>
                <div><dt>Archived by</dt><dd>{workspace.archived_by_user_id || "-"}</dd></div>
                <div><dt>Deleted by</dt><dd>{workspace.deleted_by_user_id || "-"}</dd></div>
                <div><dt>Last seen</dt><dd>{workspace.last_seen_utc || "-"}</dd></div>
                <div><dt>Last room</dt><dd>{workspace.last_room || "-"}</dd></div>
              </dl>
            </div>

            <div className="admin-info-block">
              <h3>Sessions</h3>
              <div className="admin-session-list">
                {sessions.length ? (
                  sessions.map((session: SessionRecord) => (
                    <button
                      key={session.session_id}
                      type="button"
                      className={`admin-session-row ${selectedSessionId === session.session_id ? "is-selected" : ""}`}
                      onClick={() => {
                        setSelectedSessionId(session.session_id);
                        setSelectedSessionUserId(String(session.user_id || ""));
                      }}
                    >
                      <div>
                        <div>{session.title || session.session_id}</div>
                        <div className="admin-session-meta">{session.session_id}</div>
                      </div>
                      <div className="admin-session-meta">
                        <div>{session.active_room || "-"}</div>
                        <div>{session.active_persona || "-"}</div>
                      </div>
                    </button>
                  ))
                ) : (
                  <p className="muted">No sessions found.</p>
                )}
              </div>
              <div className="admin-subtitle">{selectedSessionTitle || "No session selected"}</div>
              {loadingTranscript ? <p className="muted">Loading transcript...</p> : null}
              {!loadingTranscript && transcript.length ? (
                <pre className="admin-transcript">{transcript.map((entry) => `${String(entry.speaker || entry.role || "Unknown").trim() || "Unknown"}: ${String(entry.text || "").trim()}`).join("\n")}</pre>
              ) : null}
              {!loadingTranscript && !transcript.length ? <p className="muted">No transcript entries loaded.</p> : null}
            </div>

            <div className="admin-info-block">
              <h3>Saved Artifacts</h3>
              <div className="admin-artifact-list">
                {artifacts.length ? (
                  artifacts.map((artifact: ArtifactRecord) => (
                    <div key={artifact.artifact_id} className="admin-artifact-card">
                      <div className="admin-artifact-title">{artifact.display_name || artifact.title || artifact.artifact_id}</div>
                      <div className="admin-artifact-meta">{artifactMeta(artifact)}</div>
                      <div className="admin-artifact-preview">{String(artifact.content_preview || "").trim() || "No preview available."}</div>
                    </div>
                  ))
                ) : (
                  <p className="muted">No saved artifacts found.</p>
                )}
              </div>
            </div>

            <div className="admin-info-block">
              <h3>Files</h3>
              <div className="admin-session-list">
                {files.length ? (
                  files.map((file: FileRecord) => (
                    <div key={file.file_id} className="admin-session-row admin-static-row">
                      <div>
                        <div>{file.original_name || file.file_id}</div>
                        <div className="admin-session-meta">{file.file_id}</div>
                      </div>
                      <div className="admin-session-meta">
                        <div>{fileMeta(file)}</div>
                        {file.download_url ? (
                          <a className="admin-link" href={file.download_url}>
                            Download
                          </a>
                        ) : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="muted">No files found.</p>
                )}
              </div>
            </div>
          </div>
        ) : null}

        {!loading && !workspace ? <p className="muted">Workspace not found.</p> : null}
      </div>
    </main>
  );
}
