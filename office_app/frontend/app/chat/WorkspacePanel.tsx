import type { ArtifactRecord, FileRecord, SessionRecord, WorkspaceRecord } from "@/lib/api";

import { roomById } from "./helpers";

type WorkspacePanelProps = {
  deletingWorkspaceId: string;
  newWorkspaceTitleDraft: string;
  workspaceDescriptionDraft: string;
  workspaceSelectionArtifacts: ArtifactRecord[];
  workspaceSelectionFiles: FileRecord[];
  workspaceSelectionId: string;
  workspaceSelectionLoading: boolean;
  workspaceSelectionSessions: SessionRecord[];
  workspaceTitleDraft: string;
  workspaces: WorkspaceRecord[];
  workspacesLoading: boolean;
  onCreateWorkspace: () => void;
  onDeleteWorkspace: (workspaceId: string) => void;
  onLoadWorkspaceSelection: (workspaceId: string) => void;
  onNewWorkspaceTitleDraftChange: (value: string) => void;
  onSaveWorkspaceMetadata: () => void;
  onWorkspaceDescriptionDraftChange: (value: string) => void;
  onWorkspaceSelect: (workspaceId: string) => void;
  onWorkspaceTitleDraftChange: (value: string) => void;
};

export function WorkspacePanel({
  deletingWorkspaceId,
  newWorkspaceTitleDraft,
  workspaceDescriptionDraft,
  workspaceSelectionArtifacts,
  workspaceSelectionFiles,
  workspaceSelectionId,
  workspaceSelectionLoading,
  workspaceSelectionSessions,
  workspaceTitleDraft,
  workspaces,
  workspacesLoading,
  onCreateWorkspace,
  onDeleteWorkspace,
  onLoadWorkspaceSelection,
  onNewWorkspaceTitleDraftChange,
  onSaveWorkspaceMetadata,
  onWorkspaceDescriptionDraftChange,
  onWorkspaceSelect,
  onWorkspaceTitleDraftChange,
}: WorkspacePanelProps) {
  return (
    <div className="dropdown-panel">
      <div className="dropdown-group">
        <div className="dropdown-group-title">Current Workspaces</div>
        <div className="dropdown-grid">
          {workspacesLoading ? <div className="muted">Loading workspaces...</div> : null}
          {workspaces.map((workspace) => (
            <div key={workspace.workspace_id} className="toolbar-stack" style={{ gap: 6 }}>
              <button
                type="button"
                className={`ghost room-option ${String(workspace.workspace_id) === workspaceSelectionId ? "toolbar-button-active" : ""}`}
                onClick={() => onLoadWorkspaceSelection(workspace.workspace_id)}
              >
                <span>{workspace.label || workspace.workspace_id}</span>
                <span className="room-option-persona">
                  {workspace.session_count || 0} session(s)
                  {workspace.last_room ? ` - ${roomById(String(workspace.last_room))?.title || workspace.last_room}` : ""}
                </span>
              </button>
              <div className="toolbar-row" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => onDeleteWorkspace(workspace.workspace_id)}
                  disabled={deletingWorkspaceId === workspace.workspace_id}
                >
                  {deletingWorkspaceId === workspace.workspace_id ? "Archiving..." : "Delete Workspace"}
                </button>
              </div>
            </div>
          ))}
        </div>
        <div className="dropdown-group">
          <div className="dropdown-group-title">New Workspace</div>
          <div className="toolbar-stack">
            <input
              className="session-input"
              type="text"
              value={newWorkspaceTitleDraft}
              placeholder="Resume"
              onChange={(event) => onNewWorkspaceTitleDraftChange(event.target.value)}
            />
            <div className="toolbar-row">
              <button type="button" className="primary" onClick={onCreateWorkspace}>
                Create Workspace
              </button>
            </div>
          </div>
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">Selected Workspace Details</div>
        <div className="toolbar-stack">
          <input
            className="session-input"
            type="text"
            value={workspaceTitleDraft}
            placeholder="Workspace name"
            onChange={(event) => onWorkspaceTitleDraftChange(event.target.value)}
          />
          <textarea
            className="session-input session-description"
            value={workspaceDescriptionDraft}
            placeholder="Workspace description"
            onChange={(event) => onWorkspaceDescriptionDraftChange(event.target.value)}
          />
          <div className="toolbar-row">
            <button type="button" className="primary" onClick={onSaveWorkspaceMetadata}>
              Save Workspace Details
            </button>
            <button type="button" className="secondary" onClick={() => onWorkspaceSelect(workspaceSelectionId)} disabled={!workspaceSelectionId}>
              Go to Workspace
            </button>
          </div>
          <div className="muted">{workspaceSelectionId ? `Selected: ${workspaceSelectionId}` : "Select a workspace above."}</div>
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">Sessions In Selected Workspace</div>
        <div className="load-list">
          {workspaceSelectionLoading ? <div className="muted">Loading workspace details...</div> : null}
          {!workspaceSelectionLoading && !workspaceSelectionSessions.length ? <div className="muted">No sessions found.</div> : null}
          {!workspaceSelectionLoading
            ? workspaceSelectionSessions.map((session) => (
                <div key={session.session_id} className="download-item">
                  <div className="load-item-title">{session.title || session.session_id}</div>
                  <div className="load-item-meta">{session.description || "No description"}</div>
                </div>
              ))
            : null}
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">Saved Artifacts In Selected Workspace</div>
        <div className="load-list">
          {workspaceSelectionLoading ? <div className="muted">Loading workspace details...</div> : null}
          {!workspaceSelectionLoading && !workspaceSelectionArtifacts.length ? <div className="muted">No artifacts found.</div> : null}
          {!workspaceSelectionLoading
            ? workspaceSelectionArtifacts.map((artifact) => (
                <div key={artifact.artifact_id} className="download-item">
                  <div className="load-item-title">{artifact.display_name || artifact.title || artifact.artifact_id}</div>
                  <div className="load-item-meta">{artifact.artifact_type || "artifact"}</div>
                </div>
              ))
            : null}
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">Files In Selected Workspace</div>
        <div className="load-list">
          {workspaceSelectionLoading ? <div className="muted">Loading workspace details...</div> : null}
          {!workspaceSelectionLoading && !workspaceSelectionFiles.length ? <div className="muted">No files found.</div> : null}
          {!workspaceSelectionLoading
            ? workspaceSelectionFiles.map((file) => (
                <div key={file.file_id} className="download-item">
                  <div className="load-item-title">{file.original_name || file.file_id}</div>
                  <div className="load-item-meta">{file.scope || "workspace"} - {file.kind || "file"}</div>
                </div>
              ))
            : null}
        </div>
      </div>
    </div>
  );
}
