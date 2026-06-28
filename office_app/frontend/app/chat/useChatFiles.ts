import { useRef, useState } from "react";

import { extractFileText, fileDownloadUrl, listFiles, uploadFile, type FileRecord } from "@/lib/api";

import { backendDisconnectedMessage, readFileAsDataUrl } from "./helpers";
import type { AttachmentMode, FileScope, SavedFileNotice } from "./types";

type UseChatFilesArgs = {
  activeRoom: string;
  sessionId: string;
  setAttachmentMode: (mode: AttachmentMode) => void;
  setBackendBanner: (message: string) => void;
  setError: (message: string) => void;
  setLoadMenuOpen: (open: boolean) => void;
  setSaveMenuOpen: (open: boolean) => void;
  appendSavedFileMessage: (message: string) => void;
};

export function useChatFiles({
  activeRoom,
  sessionId,
  setAttachmentMode,
  setBackendBanner,
  setError,
  setLoadMenuOpen,
  setSaveMenuOpen,
  appendSavedFileMessage,
}: UseChatFilesArgs) {
  const [fileKind, setFileKind] = useState("document");
  const [fileScope, setFileScope] = useState<FileScope>("room");
  const [loadScope, setLoadScope] = useState<FileScope>("room");
  const [privateBucket, setPrivateBucket] = useState("by_type");
  const [workspaceFiles, setWorkspaceFiles] = useState<FileRecord[]>([]);
  const [privateFiles, setPrivateFiles] = useState<FileRecord[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);
  const [readerTitle, setReaderTitle] = useState("");
  const [readerText, setReaderText] = useState("");
  const [readerLoading, setReaderLoading] = useState(false);
  const [readerFile, setReaderFile] = useState<FileRecord | null>(null);
  const [selectedUploadName, setSelectedUploadName] = useState("");
  const [selectedUploadDataUrl, setSelectedUploadDataUrl] = useState("");
  const [selectedUploadMime, setSelectedUploadMime] = useState("");
  const [selectedUploadDescription, setSelectedUploadDescription] = useState("");
  const [selectedUploadReady, setSelectedUploadReady] = useState(false);
  const [uploadNote, setUploadNote] = useState("");
  const [lastSavedFile, setLastSavedFile] = useState<SavedFileNotice | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function openReader(file: FileRecord) {
    setLoadMenuOpen(false);
    setReaderOpen(true);
    setReaderLoading(true);
    setReaderTitle(file.original_name || "Document");
    setReaderFile(file);
    setReaderText("");
    setError("");
    try {
      const text = await extractFileText(file);
      setReaderText(text);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to read file.";
      setReaderText(message);
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    } finally {
      setReaderLoading(false);
    }
  }

  async function refreshFiles(nextSessionId?: string, nextRoomId?: string) {
    const chosenSessionId = nextSessionId || sessionId;
    const chosenRoomId = nextRoomId || activeRoom;
    if (!chosenSessionId) {
      return;
    }
    setFilesLoading(true);
    try {
      if (loadScope === "private") {
        const privateResponse = await listFiles("private", privateBucket);
        setWorkspaceFiles([]);
        setPrivateFiles(privateResponse.files || []);
      } else {
        const scopeRef = loadScope === "room" ? chosenRoomId : loadScope === "session" ? chosenSessionId : "public";
        const response = await listFiles(loadScope, scopeRef);
        setWorkspaceFiles(response.files || []);
        setPrivateFiles([]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load files.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    } finally {
      setFilesLoading(false);
    }
  }

  async function handleUploadSelected(file: File) {
    setError("");
    const dataUrl = await readFileAsDataUrl(file);
    const scopeRef =
      fileScope === "room"
        ? activeRoom
        : fileScope === "session"
          ? sessionId
          : fileScope === "private"
            ? privateBucket
            : "public";
    try {
      const saved = await uploadFile({
        name: file.name,
        data_url: dataUrl,
        mime_type: file.type || undefined,
        kind: fileKind,
        scope: fileScope,
        scope_ref: scopeRef,
        description: selectedUploadDescription || undefined,
      });
      const savedNotice = {
        name: saved.original_name || file.name,
        scope: String(saved.scope || fileScope),
        scopeRef: String(saved.scope_ref || scopeRef),
        fileId: String(saved.file_id || ""),
      };
      const note = `${savedNotice.name} saved to ${savedNotice.scope}${savedNotice.scopeRef ? ` (${savedNotice.scopeRef})` : ""}.`;
      setLastSavedFile(savedNotice);
      setUploadNote(note);
      setSelectedUploadName("");
      setSelectedUploadDataUrl("");
      setSelectedUploadMime("");
      setSelectedUploadDescription("");
      setSelectedUploadReady(false);
      setAttachmentMode("download");
      await refreshFiles();
      appendSavedFileMessage(`Saved file ${savedNotice.name} to ${savedNotice.scope}${savedNotice.scopeRef ? ` (${savedNotice.scopeRef})` : ""}.`);
      setSaveMenuOpen(false);
      setLoadMenuOpen(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    }
  }

  async function onPickFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setSelectedUploadName(file.name);
    setSelectedUploadMime(file.type || "");
    const dataUrl = await readFileAsDataUrl(file);
    setSelectedUploadDataUrl(dataUrl);
    setSelectedUploadReady(true);
  }

  async function submitSelectedUpload() {
    if (!selectedUploadReady || !selectedUploadDataUrl || !selectedUploadName) {
      setError("Choose a file first.");
      return;
    }
    const blob = await fetch(selectedUploadDataUrl).then((response) => response.blob());
    const file = new File([blob], selectedUploadName, { type: selectedUploadMime });
    await handleUploadSelected(file);
  }

  function openPicker() {
    fileInputRef.current?.click();
  }

  function downloadFile(file: FileRecord) {
    window.open(fileDownloadUrl(file), "_blank", "noopener,noreferrer");
  }

  return {
    fileInputRef,
    fileKind,
    fileScope,
    filesLoading,
    lastSavedFile,
    loadScope,
    privateBucket,
    privateFiles,
    readerFile,
    readerLoading,
    readerOpen,
    readerText,
    readerTitle,
    selectedUploadName,
    selectedUploadReady,
    uploadNote,
    workspaceFiles,
    downloadFile,
    onPickFile,
    openPicker,
    openReader,
    refreshFiles,
    setFileKind,
    setFileScope,
    setLoadScope,
    setPrivateBucket,
    setReaderOpen,
    submitSelectedUpload,
  };
}
