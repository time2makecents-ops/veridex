import type { FileRecord } from "@/lib/api";
import { fileDownloadUrl } from "@/lib/api";

import { fileSortLabel } from "./helpers";
import {
  FILE_KIND_OPTIONS,
  FILE_SCOPE_OPTIONS,
  PRIVATE_BUCKET_OPTIONS,
  type AttachmentMode,
  type FileScope,
  type SavedFileNotice,
} from "./types";

type FilePanelsProps = {
  attachmentMode: AttachmentMode;
  fileKind: string;
  fileScope: FileScope;
  filesLoading: boolean;
  lastSavedFile: SavedFileNotice | null;
  loadScope: FileScope;
  privateBucket: string;
  privateFiles: FileRecord[];
  selectedUploadName: string;
  selectedUploadReady: boolean;
  uploadNote: string;
  workspaceFiles: FileRecord[];
  onAttachmentModeChange: (mode: AttachmentMode) => void;
  onDownloadFile: (file: FileRecord) => void;
  onFileKindChange: (kind: string) => void;
  onFileScopeChange: (scope: FileScope) => void;
  onLoadScopeChange: (scope: FileScope) => void;
  onOpenPicker: () => void;
  onOpenReader: (file: FileRecord) => void;
  onPrivateBucketChange: (bucket: string) => void;
  onRefreshFiles: () => void;
  onSubmitSelectedUpload: () => void;
};

export function SaveFilePanel({
  fileKind,
  fileScope,
  lastSavedFile,
  privateBucket,
  selectedUploadName,
  selectedUploadReady,
  uploadNote,
  onFileKindChange,
  onFileScopeChange,
  onOpenPicker,
  onPrivateBucketChange,
  onSubmitSelectedUpload,
}: Pick<
  FilePanelsProps,
  | "fileKind"
  | "fileScope"
  | "lastSavedFile"
  | "privateBucket"
  | "selectedUploadName"
  | "selectedUploadReady"
  | "uploadNote"
  | "onFileKindChange"
  | "onFileScopeChange"
  | "onOpenPicker"
  | "onPrivateBucketChange"
  | "onSubmitSelectedUpload"
>) {
  return (
    <div className="dropdown-panel">
      <div className="dropdown-group">
        <div className="dropdown-group-title">File Type</div>
        <div className="toolbar-row">
          {FILE_KIND_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`ghost toolbar-button ${fileKind === option.value ? "toolbar-button-active" : ""}`}
              onClick={() => onFileKindChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">Save To</div>
        <div className="dropdown-grid">
          {FILE_SCOPE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`ghost room-option ${fileScope === option.value ? "toolbar-button-active" : ""}`}
              onClick={() => onFileScopeChange(option.value)}
            >
              <span>{option.label}</span>
              <span className="room-option-persona">{option.description}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">Private organization</div>
        <div className="toolbar-row">
          {PRIVATE_BUCKET_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`ghost toolbar-button ${privateBucket === option.value ? "toolbar-button-active" : ""}`}
              onClick={() => onPrivateBucketChange(option.value)}
              disabled={fileScope !== "private"}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="muted">Private files are saved in a separate database. Access them through Nancy memo requests.</div>
      </div>
      <div className="dropdown-group">
        <div className="toolbar-row">
          <button type="button" className="secondary" onClick={onOpenPicker}>
            Choose file
          </button>
          <button type="button" className="primary" onClick={onSubmitSelectedUpload} disabled={!selectedUploadReady}>
            Upload
          </button>
        </div>
        {selectedUploadName ? <div className="muted">Selected: {selectedUploadName}</div> : null}
        {lastSavedFile ? (
          <div className="muted">
            Last saved: {lastSavedFile.name} {"->"} {lastSavedFile.scope}
            {lastSavedFile.scopeRef ? ` (${lastSavedFile.scopeRef})` : ""}
          </div>
        ) : null}
        {uploadNote ? <div className="muted">{uploadNote}</div> : null}
      </div>
    </div>
  );
}

export function LoadFilePanel({
  loadScope,
  privateBucket,
  privateFiles,
  workspaceFiles,
  onDownloadFile,
  onLoadScopeChange,
  onOpenReader,
  onPrivateBucketChange,
}: Pick<
  FilePanelsProps,
  | "loadScope"
  | "privateBucket"
  | "privateFiles"
  | "workspaceFiles"
  | "onDownloadFile"
  | "onLoadScopeChange"
  | "onOpenReader"
  | "onPrivateBucketChange"
>) {
  const files = loadScope === "private" ? privateFiles : workspaceFiles;
  return (
    <div className="dropdown-panel">
      <div className="dropdown-group">
        <div className="dropdown-group-title">Load document</div>
        <div className="muted">Choose a document to open in the reader window.</div>
      </div>
      <div className="dropdown-group">
        <div className="button-grid">
          {FILE_SCOPE_OPTIONS.map((option) => (
            <button
              key={`load-${option.value}`}
              type="button"
              className={`option-button ${loadScope === option.value ? "is-active" : ""}`}
              onClick={() => onLoadScopeChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        {loadScope === "private" ? (
          <div className="button-grid compact-grid">
            {PRIVATE_BUCKET_OPTIONS.map((option) => (
              <button
                key={`load-private-${option.value}`}
                type="button"
                className={`option-button ${privateBucket === option.value ? "is-active" : ""}`}
                onClick={() => onPrivateBucketChange(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="dropdown-group">
        <div className="dropdown-group-title">
          {loadScope === "private"
            ? "Private Files"
            : loadScope === "room"
              ? "Current Room Files"
              : loadScope === "session"
                ? "Current Session Files"
                : "Public Files"}
        </div>
        <div className="load-list">
          {files.length ? (
            files.map((file) => (
              <div key={file.file_id} className="load-item">
                <button type="button" className="load-item-main" onClick={() => onOpenReader(file)}>
                  <span className="load-item-title">{file.original_name}</span>
                  <span className="load-item-meta">{fileSortLabel(file)}</span>
                </button>
                <button type="button" className="secondary load-download-button" onClick={() => onDownloadFile(file)}>
                  Download
                </button>
              </div>
            ))
          ) : (
            <div className="muted">
              {loadScope === "private"
                ? "No private files yet."
                : loadScope === "room"
                  ? "No room files yet."
                  : loadScope === "session"
                    ? "No session files yet."
                    : "No public files yet."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function AttachmentPanel({
  attachmentMode,
  filesLoading,
  privateFiles,
  selectedUploadName,
  selectedUploadReady,
  workspaceFiles,
  onAttachmentModeChange,
  onOpenPicker,
  onRefreshFiles,
  onSubmitSelectedUpload,
}: Pick<
  FilePanelsProps,
  | "attachmentMode"
  | "filesLoading"
  | "privateFiles"
  | "selectedUploadName"
  | "selectedUploadReady"
  | "workspaceFiles"
  | "onAttachmentModeChange"
  | "onOpenPicker"
  | "onRefreshFiles"
  | "onSubmitSelectedUpload"
>) {
  return (
    <div className="dropdown-panel attachment-panel">
      <div className="toolbar-row">
        <button
          type="button"
          className={`ghost toolbar-button ${attachmentMode === "download" ? "toolbar-button-active" : ""}`}
          onClick={() => {
            onAttachmentModeChange("download");
            onRefreshFiles();
          }}
        >
          Download
        </button>
        <button
          type="button"
          className={`ghost toolbar-button ${attachmentMode === "upload" ? "toolbar-button-active" : ""}`}
          onClick={() => onAttachmentModeChange("upload")}
        >
          Upload
        </button>
      </div>

      {attachmentMode === "upload" ? (
        <div className="stack">
          <div className="toolbar-row">
            <button type="button" className="secondary" onClick={onOpenPicker}>
              Choose file
            </button>
            <button type="button" className="primary" onClick={onSubmitSelectedUpload} disabled={!selectedUploadReady}>
              Upload now
            </button>
          </div>
          {selectedUploadName ? <div className="muted">Selected: {selectedUploadName}</div> : null}
        </div>
      ) : (
        <div className="stack">
          <div className="dropdown-group-title">Room / Workspace Files</div>
          {filesLoading ? <div className="muted">Loading files...</div> : null}
          <div className="download-list">
            {workspaceFiles.length ? (
              workspaceFiles.map((file) => (
                <a key={file.file_id} className="download-item" href={fileDownloadUrl(file)} target="_blank" rel="noreferrer">
                  <span>{file.original_name}</span>
                  <span className="room-option-persona">{file.scope || "workspace"} - {file.kind || "file"}</span>
                </a>
              ))
            ) : (
              <div className="muted">No workspace files yet.</div>
            )}
          </div>

          <div className="dropdown-group-title">Private Files</div>
          <div className="download-list">
            {privateFiles.length ? (
              privateFiles.map((file) => (
                <a key={file.file_id} className="download-item" href={fileDownloadUrl(file)} target="_blank" rel="noreferrer">
                  <span>{file.original_name}</span>
                  <span className="room-option-persona">private - {file.kind || "file"}</span>
                </a>
              ))
            ) : (
              <div className="muted">No private files yet.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
