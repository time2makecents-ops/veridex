"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  activateSession,
  activateWorkspace,
  callTool,
  createSession,
  createWorkspace,
  extractFileText,
  fileDownloadUrl,
  listFiles,
  listSessions,
  listWorkspaces,
  loadTranscript,
  request,
  requestText,
  uploadFile,
  type FileRecord,
  type WorkspaceRecord,
  type SessionRecord,
  type TranscriptEntry,
} from "@/lib/api";
import { clearStoredSessionId, getSessionShortLabel, getStoredSessionId, setStoredSessionId } from "@/lib/session";
import { ROOM_GROUPS, ROOMS, type RoomInfo } from "@/lib/rooms";

type LobbyState = {
  workspace_id: string;
  active_room: string;
  active_persona: string;
};

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  speaker?: string;
  room?: string;
  sessionId?: string;
};

type SavedFileNotice = {
  name: string;
  scope: string;
  scopeRef: string;
  fileId: string;
};

type FileScope = "room" | "session" | "public" | "private";
type ChatScope = "room" | "global";

const FILE_KIND_OPTIONS = [
  { value: "audio", label: "Audio" },
  { value: "video", label: "Video" },
  { value: "document", label: "Document" },
  { value: "code", label: "Code" },
  { value: "other", label: "Other" },
];

const FILE_SCOPE_OPTIONS: Array<{ value: FileScope; label: string; description: string }> = [
  { value: "room", label: "Room", description: "Saved to the current room for everyone in that room." },
  { value: "session", label: "Session", description: "Only accessible in this session." },
  { value: "public", label: "Public", description: "Accessible anywhere in Veridex." },
  { value: "private", label: "Private", description: "Stored separately. Access via Nancy memo." },
];

const PRIVATE_BUCKET_OPTIONS = [
  { value: "by_type", label: "By type" },
  { value: "by_date", label: "By date" },
  { value: "by_project", label: "By project" },
  { value: "by_memo", label: "By memo" },
];

function roomById(roomId: string): RoomInfo | undefined {
  return ROOMS.find((room) => room.id === roomId);
}

function roomTransitionText(roomId: string, persona: string): string {
  const title = roomById(roomId)?.title || roomId;
  return `Now in ${title}. Persona: ${persona}.`;
}

export default function ChatPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [activeRoom, setActiveRoom] = useState("lobby");
  const [activePersona, setActivePersona] = useState("Receptionist");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [switchingRoom, setSwitchingRoom] = useState<string>("");
  const [roomMenuOpen, setRoomMenuOpen] = useState(false);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [saveMenuOpen, setSaveMenuOpen] = useState(false);
  const [loadMenuOpen, setLoadMenuOpen] = useState(false);
  const [attachmentOpen, setAttachmentOpen] = useState(false);
  const [attachmentMode, setAttachmentMode] = useState<"upload" | "download">("download");
  const [recentRooms, setRecentRooms] = useState<string[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [workspacesLoading, setWorkspacesLoading] = useState(false);
  const [workspaceTitleDraft, setWorkspaceTitleDraft] = useState("");
  const [activeWorkspaceLabel, setActiveWorkspaceLabel] = useState("");
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionTitleDraft, setSessionTitleDraft] = useState("");
  const [sessionDescriptionDraft, setSessionDescriptionDraft] = useState("");
  const [fileKind, setFileKind] = useState("document");
  const [fileScope, setFileScope] = useState<FileScope>("room");
  const [loadScope, setLoadScope] = useState<FileScope>("room");
  const [chatScope, setChatScope] = useState<ChatScope>("room");
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
  const [roomStatus, setRoomStatus] = useState("Waiting for room state.");
  const [backendBanner, setBackendBanner] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const announcedRoomRef = useRef(false);

  useEffect(() => {
    const stored = getStoredSessionId();
    if (!stored) {
      router.replace("/");
      return;
    }
    setSessionId(stored);
  }, [router]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, switchingRoom]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    let cancelled = false;
    const loadState = async () => {
      try {
        const [stateResponse, transcriptEntries] = await Promise.all([
          callTool("office.state_get", {}),
          loadTranscript(120, sessionId),
        ]);
        const structured = stateResponse.structuredContent as LobbyState | undefined;
        if (cancelled || !structured) {
          return;
        }
        const nextWorkspace = String(structured.workspace_id || "");
        const nextRoom = String(structured.active_room || "lobby");
        const nextPersona = String(structured.active_persona || "Receptionist");
        setWorkspaceId(nextWorkspace);
        setActiveWorkspaceLabel(nextWorkspace);
        setActiveRoom(nextRoom);
        setActivePersona(nextPersona);
        setRecentRooms((current) => pushRecentRoom(current, nextRoom));
        applyHydratedMessages(nextRoom, nextPersona, transcriptEntries);
        void refreshWorkspaces(nextWorkspace);
        void refreshSessions();
      } catch (err) {
          const message = err instanceof Error ? err.message : "Unable to load lobby state.";
          setError(message);
          setBackendBanner(backendDisconnectedMessage(message));
          if (message.toLowerCase().includes("session")) {
            clearStoredSessionId();
            router.replace("/");
          }
        }
    };

    void loadState();
    return () => {
      cancelled = true;
    };
  }, [router, sessionId]);

  const sessionLabel = useMemo(() => getSessionShortLabel(sessionId), [sessionId]);
  const currentWorkspace = useMemo(
    () => workspaces.find((workspace) => String(workspace.workspace_id) === workspaceId),
    [workspaceId, workspaces],
  );
  const currentWorkspaceLabel = activeWorkspaceLabel || currentWorkspace?.label || workspaceId || "Unassigned";
  const currentSession = useMemo(
    () => sessions.find((session) => String(session.session_id) === sessionId),
    [sessionId, sessions],
  );
  const currentSessionTitle = currentSession?.title || sessionLabel;
  const currentSessionDescription = currentSession?.description || "";
  const currentRoom = useMemo(() => roomById(activeRoom), [activeRoom]);
  const currentTitle = currentRoom?.title || activeRoom;
  const visibleMessages = useMemo(
    () =>
      messages.filter((message) => {
        const sessionMatches = message.sessionId === sessionId;
        if (!sessionMatches) {
          return false;
        }
        if (chatScope === "global") {
          return true;
        }
        return !message.room || message.room === activeRoom;
      }),
    [activeRoom, chatScope, messages, sessionId],
  );

  function applyHydratedMessages(nextRoom: string, nextPersona: string, transcriptEntries: TranscriptEntry[]) {
    const nextStatus = roomTransitionText(nextRoom, nextPersona);
    setRoomStatus(nextStatus);
    const hydratedMessages = mapTranscriptEntries(transcriptEntries);
    if (hydratedMessages.length) {
      announcedRoomRef.current = true;
      setMessages(hydratedMessages);
    } else {
      announcedRoomRef.current = true;
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          speaker: "Receptionist",
          text: "Receptionist ready. How may I help you today?",
          sessionId: sessionId,
        },
      ]);
    }
  }

  function pushRecentRoom(existing: string[], roomId: string): string[] {
    const next = [roomId, ...existing.filter((item) => item !== roomId)];
    return next.slice(0, 3);
  }

  async function refreshWorkspaces(activeWorkspaceId?: string) {
    if (!sessionId) {
      return;
    }
    setWorkspacesLoading(true);
    try {
      const response = await listWorkspaces();
      setWorkspaces(response);
      const targetId = activeWorkspaceId || workspaceId;
      const active = response.find((item) => String(item.workspace_id) === targetId);
      if (active) {
        setWorkspaceTitleDraft(String(active.label || ""));
        setActiveWorkspaceLabel(String(active.label || active.workspace_id || ""));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load workspaces.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    } finally {
      setWorkspacesLoading(false);
    }
  }

  function appendRoomTransition(roomId: string, persona: string) {
    const text = roomTransitionText(roomId, persona);
    setRoomStatus(text);
  }

  function backendDisconnectedMessage(message: string): string {
    const text = message.toLowerCase();
    if (
      text.includes("500") ||
      text.includes("failed to fetch") ||
      text.includes("unable to connect") ||
      text.includes("networkerror") ||
      text.includes("request timed out")
    ) {
      return "Veridex backend disconnected. Check the server on port 8078.";
    }
    return "";
  }

  function fileSortLabel(file: FileRecord): string {
    const date = file.created_at ? new Date(file.created_at).toLocaleDateString() : "no date";
    const session = String(file.scope_ref || file.workspace_id || "workspace");
    const kind = file.kind || "file";
    return `${date} - ${session} - ${kind}`;
  }

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

  async function refreshFiles() {
    if (!sessionId) {
      return;
    }
    setFilesLoading(true);
    try {
      if (loadScope === "private") {
        const privateResponse = await listFiles("private", privateBucket);
        setWorkspaceFiles([]);
        setPrivateFiles(privateResponse.files || []);
      } else {
        const scopeRef = loadScope === "room" ? activeRoom : loadScope === "session" ? sessionId : "public";
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

  async function refreshSessions(activeSessionId?: string) {
    if (!sessionId) {
      return;
    }
    setSessionsLoading(true);
    try {
      const response = await listSessions();
      setSessions(response);
      const targetId = activeSessionId || sessionId;
      const active = response.find((item) => String(item.session_id) === targetId);
      if (active) {
        setSessionTitleDraft(String(active.title || ""));
        setSessionDescriptionDraft(String(active.description || ""));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load sessions.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    } finally {
      setSessionsLoading(false);
    }
  }

  async function refreshCurrentThread(nextSessionId?: string) {
    const chosenSessionId = nextSessionId || sessionId;
    if (!chosenSessionId) {
      return;
    }
    const transcriptEntries = await loadTranscript(120, chosenSessionId);
    const stateResponse = await callTool("office.state_get", {});
    const structured = stateResponse.structuredContent as LobbyState | undefined;
    if (!structured) {
      return;
    }
    const nextWorkspace = String(structured.workspace_id || workspaceId);
    const nextRoom = String(structured.active_room || "lobby");
    const nextPersona = String(structured.active_persona || "Receptionist");
    setWorkspaceId(nextWorkspace);
    setActiveWorkspaceLabel(workspaces.find((item) => String(item.workspace_id) === nextWorkspace)?.label || nextWorkspace);
    setSessionId(chosenSessionId);
    setActiveRoom(nextRoom);
    setActivePersona(nextPersona);
    setRecentRooms((current) => pushRecentRoom(current, nextRoom));
    applyHydratedMessages(nextRoom, nextPersona, transcriptEntries);
  }

  async function handleWorkspaceSelect(targetWorkspaceId: string) {
    if (!targetWorkspaceId || targetWorkspaceId === workspaceId) {
      setWorkspaceMenuOpen(false);
      return;
    }
    setError("");
    setBackendBanner("");
    try {
      const activated = await activateWorkspace(targetWorkspaceId);
      const nextWorkspaceId = String(activated.workspace_id || targetWorkspaceId);
      const nextSessionId = String(activated.session_id || sessionId);
      const workspaceState = activated as { workspace_state?: LobbyState };
      const nextRoom = String(workspaceState.workspace_state?.active_room || "lobby");
      const nextPersona = String(workspaceState.workspace_state?.active_persona || "Receptionist");
      setStoredSessionId(nextSessionId);
      setSessionId(nextSessionId);
      setWorkspaceId(nextWorkspaceId);
      setActiveWorkspaceLabel(workspaces.find((item) => String(item.workspace_id) === nextWorkspaceId)?.label || nextWorkspaceId);
      setActiveRoom(nextRoom);
      setActivePersona(nextPersona);
      setChatScope("room");
      setRecentRooms((current) => pushRecentRoom(current, nextRoom));
      const transcriptEntries = await loadTranscript(120, nextSessionId);
      applyHydratedMessages(nextRoom, nextPersona, transcriptEntries);
      await refreshWorkspaces(nextWorkspaceId);
      await refreshSessions(nextSessionId);
      await refreshFiles();
      setWorkspaceMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to activate workspace.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    }
  }

  async function handleCreateWorkspace() {
    const title = workspaceTitleDraft.trim() || "New Workspace";
    setError("");
    setBackendBanner("");
    try {
      const created = await createWorkspace(title);
      const nextWorkspaceId = String(created.workspace_id || "");
      const activated = await activateWorkspace(nextWorkspaceId);
      const nextSessionId = String(activated.session_id || sessionId);
      setStoredSessionId(nextSessionId);
      setSessionId(nextSessionId);
      setWorkspaceId(nextWorkspaceId);
      setActiveWorkspaceLabel(String(created.label || title));
      setActiveRoom("lobby");
      setActivePersona("Receptionist");
      setChatScope("room");
      setRecentRooms((current) => pushRecentRoom(current, "lobby"));
      setWorkspaceTitleDraft(String(created.label || title));
      const transcriptEntries = await loadTranscript(120, nextSessionId);
      applyHydratedMessages("lobby", "Receptionist", transcriptEntries);
      await refreshWorkspaces(nextWorkspaceId);
      await refreshSessions(nextSessionId);
      await refreshFiles();
      setWorkspaceMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create workspace.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    }
  }

  async function handleSessionSelect(targetSessionId: string) {
    if (!targetSessionId || targetSessionId === sessionId) {
      setSessionMenuOpen(false);
      return;
    }
    setError("");
    setBackendBanner("");
    try {
      const response = await activateSession(targetSessionId);
      const nextSessionId = String(response.session_id || targetSessionId);
      const nextWorkspaceId = String(response.active_workspace_id || response.workspace_id || workspaceId);
      setStoredSessionId(nextSessionId);
      setSessionId(nextSessionId);
      setWorkspaceId(nextWorkspaceId);
      setActiveWorkspaceLabel(workspaces.find((item) => String(item.workspace_id) === nextWorkspaceId)?.label || nextWorkspaceId);
      setSessionTitleDraft(String(response.title || ""));
      setSessionDescriptionDraft(String(response.description || ""));
      await refreshCurrentThread(nextSessionId);
      await refreshWorkspaces(nextWorkspaceId);
      await refreshFiles();
      await refreshSessions(nextSessionId);
      setChatScope("room");
      setSessionMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to activate session.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    }
  }

  async function handleCreateSession() {
    const title = sessionTitleDraft.trim() || "New Session";
    const description = sessionDescriptionDraft.trim() || title;
    setError("");
    setBackendBanner("");
    try {
      const created = await createSession(title, description);
      const nextSessionId = String(created.session_id || "");
      const nextWorkspaceId = String(created.active_workspace_id || created.workspace_id || workspaceId);
      setStoredSessionId(nextSessionId);
      setSessionId(nextSessionId);
      setWorkspaceId(nextWorkspaceId);
      setActiveWorkspaceLabel(workspaces.find((item) => String(item.workspace_id) === nextWorkspaceId)?.label || nextWorkspaceId);
      setSessionTitleDraft(String(created.title || title));
      setSessionDescriptionDraft(String(created.description || description));
      setActiveRoom("lobby");
      setActivePersona("Receptionist");
      setChatScope("room");
      setRecentRooms((current) => pushRecentRoom(current, "lobby"));
      await refreshCurrentThread(nextSessionId);
      await refreshWorkspaces(nextWorkspaceId);
      await refreshFiles();
      await refreshSessions(nextSessionId);
      setSessionMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create session.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    }
  }

  async function sendText(text: string) {
    const value = text.trim();
    if (!value || loading) {
      return;
    }
    setDraft("");
    setError("");
    setBackendBanner("");
    setLoading(true);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: value, room: activeRoom, sessionId }]);
    try {
      const response = await request(value);
      const assistantText = requestText(response);
      const nextWorkspaceId = String(response.workspace_id || response.structuredContent?.workspace_id || workspaceId);
      const nextSessionId = String(response.session_id || response.structuredContent?.session_id || sessionId);
      const nextRoom = String((response.structuredContent as { active_room?: string } | undefined)?.active_room || activeRoom);
      const nextPersona = String((response.structuredContent as { active_persona?: string } | undefined)?.active_persona || activePersona);
      setWorkspaceId(nextWorkspaceId);
      setSessionId(nextSessionId);
      setActiveRoom(nextRoom);
      setActivePersona(nextPersona);
      setRecentRooms((current) => pushRecentRoom(current, nextRoom));
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", speaker: nextPersona, text: assistantText, room: nextRoom, sessionId: nextSessionId },
      ]);
      if (nextRoom !== activeRoom || nextPersona !== activePersona) {
        appendRoomTransition(nextRoom, nextPersona);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: message, room: activeRoom, sessionId }]);
      if (message.toLowerCase().includes("session")) {
        clearStoredSessionId();
        router.replace("/");
      }
    } finally {
      setLoading(false);
      window.requestAnimationFrame(() => {
        draftRef.current?.focus();
      });
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendText(draft);
  }

  function handleDraftKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    void sendText(draft);
  }

  async function handleRoomSelect(roomId: string) {
    if (!roomId || roomId === activeRoom || switchingRoom) {
      return;
    }
    setSwitchingRoom(roomId);
    setError("");
    setBackendBanner("");
    setRoomMenuOpen(false);
    try {
      const response = await callTool("office.room_set", { room_id: roomId });
      const structured = response.structuredContent as { active_room?: string; active_persona?: string } | undefined;
      const nextRoom = String(structured?.active_room || roomId);
      const nextPersona = String(structured?.active_persona || roomById(nextRoom)?.persona || "Receptionist");
      const transcriptEntries = await loadTranscript(120, sessionId);
      setActiveRoom(nextRoom);
      setActivePersona(nextPersona);
      setChatScope("room");
      setRecentRooms((current) => pushRecentRoom(current, nextRoom));
      applyHydratedMessages(nextRoom, nextPersona, transcriptEntries);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to change room.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    } finally {
      setSwitchingRoom("");
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
      setLastSavedFile(savedNotice);
      setUploadNote(`${savedNotice.name} saved to ${savedNotice.scope}${savedNotice.scopeRef ? ` (${savedNotice.scopeRef})` : ""}.`);
      setSelectedUploadName("");
      setSelectedUploadDataUrl("");
      setSelectedUploadMime("");
      setSelectedUploadDescription("");
      setSelectedUploadReady(false);
      setAttachmentMode("download");
      await refreshFiles();
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          speaker: "System",
          text: `Saved file ${savedNotice.name} to ${savedNotice.scope}${savedNotice.scopeRef ? ` (${savedNotice.scopeRef})` : ""}.`,
          room: activeRoom,
          sessionId,
        },
      ]);
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

  useEffect(() => {
    if (attachmentOpen) {
      void refreshFiles();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attachmentOpen]);

  useEffect(() => {
    if (loadMenuOpen) {
      void refreshFiles();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRoom, loadMenuOpen, loadScope, privateBucket, sessionId]);

  return (
    <main
      className="screen lobby-page lobby-page-plain"
      data-session={sessionLabel}
      data-workspace={workspaceId}
      data-room={activeRoom}
      data-persona={activePersona}
    >
      <section className="card lobby-page-header">
        <input ref={fileInputRef} type="file" className="hidden-file-input" onChange={onPickFile} />
        <div className="stack">
          <div className="lobby-title-row">
            <div className="stack" style={{ gap: 4 }}>
              <div className="terminal-label">Veridex Lobby</div>
              <h1 className="title">{currentTitle}</h1>
              <div className="muted">{currentSessionDescription || "No session description yet."}</div>
            </div>
            <div className="session-inline">
              <button
                type="button"
                className={`ghost workspace-inline ${workspaceMenuOpen ? "toolbar-button-active" : ""}`}
                onClick={() => {
                  setWorkspaceMenuOpen((current) => !current);
                  setRoomMenuOpen(false);
                  setSessionMenuOpen(false);
                  setSaveMenuOpen(false);
                  setLoadMenuOpen(false);
                  setAttachmentOpen(false);
                }}
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

          {workspaceMenuOpen ? (
            <div className="dropdown-panel">
              <div className="dropdown-group">
                <div className="dropdown-group-title">Current Workspaces</div>
                <div className="dropdown-grid">
                  {workspacesLoading ? <div className="muted">Loading workspaces...</div> : null}
                  {workspaces.map((workspace) => (
                    <button
                      key={workspace.workspace_id}
                      type="button"
                      className={`ghost room-option ${String(workspace.workspace_id) === workspaceId ? "toolbar-button-active" : ""}`}
                      onClick={() => void handleWorkspaceSelect(workspace.workspace_id)}
                    >
                      <span>{workspace.label || workspace.workspace_id}</span>
                      <span className="room-option-persona">
                        {workspace.session_count || 0} session(s)
                        {workspace.last_room ? ` · ${roomById(String(workspace.last_room))?.title || workspace.last_room}` : ""}
                      </span>
                    </button>
                  ))}
                  {!workspacesLoading && !workspaces.length ? <div className="muted">No workspaces yet.</div> : null}
                </div>
              </div>
              <div className="dropdown-group">
                <div className="dropdown-group-title">New Workspace</div>
                <div className="toolbar-stack">
                  <input
                    className="session-input"
                    type="text"
                    value={workspaceTitleDraft}
                    placeholder="Resume"
                    onChange={(event) => setWorkspaceTitleDraft(event.target.value)}
                  />
                  <div className="toolbar-row">
                    <button type="button" className="primary" onClick={() => void handleCreateWorkspace()}>
                      Create Workspace
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className="toolbar-row">
            <button
              type="button"
              className={`ghost toolbar-button ${roomMenuOpen ? "toolbar-button-active" : ""}`}
              onClick={() => {
                setRoomMenuOpen((current) => !current);
                setWorkspaceMenuOpen(false);
                setSessionMenuOpen(false);
                setSaveMenuOpen(false);
                setLoadMenuOpen(false);
                setAttachmentOpen(false);
              }}
            >
              Directory
            </button>
            <button
              type="button"
              className={`ghost toolbar-button ${sessionMenuOpen ? "toolbar-button-active" : ""}`}
              onClick={() => {
                setSessionMenuOpen((current) => !current);
                setWorkspaceMenuOpen(false);
                setRoomMenuOpen(false);
                setSaveMenuOpen(false);
                setLoadMenuOpen(false);
                setAttachmentOpen(false);
              }}
            >
              Sessions
            </button>
            {recentRooms.map((roomId) => {
              const room = roomById(roomId);
              return (
                <button
                  key={roomId}
                  type="button"
                  className={`ghost toolbar-button ${roomId === activeRoom ? "toolbar-button-active" : ""}`}
                  onClick={() => void handleRoomSelect(roomId)}
                >
                  {room?.title || roomId}
                </button>
              );
            })}
            <button
              type="button"
              className={`ghost toolbar-button ${saveMenuOpen ? "toolbar-button-active" : ""}`}
              onClick={() => {
                setSaveMenuOpen((current) => !current);
                setWorkspaceMenuOpen(false);
                setRoomMenuOpen(false);
                setSessionMenuOpen(false);
                setLoadMenuOpen(false);
                setAttachmentOpen(false);
              }}
            >
              Save
            </button>
            <button
              type="button"
              className={`ghost toolbar-button ${loadMenuOpen ? "toolbar-button-active" : ""}`}
              onClick={() => {
                setLoadMenuOpen((current) => !current);
                setWorkspaceMenuOpen(false);
                setRoomMenuOpen(false);
                setSaveMenuOpen(false);
                setSessionMenuOpen(false);
                setAttachmentOpen(false);
              }}
            >
              Load
            </button>
          </div>

          {sessionMenuOpen ? (
            <div className="dropdown-panel">
              <div className="dropdown-group">
                <div className="dropdown-group-title">Current Sessions</div>
                <div className="dropdown-grid">
                  {sessionsLoading ? <div className="muted">Loading sessions...</div> : null}
                  {sessions.map((session) => (
                    <button
                      key={session.session_id}
                      type="button"
                      className={`ghost room-option ${String(session.session_id) === sessionId ? "toolbar-button-active" : ""}`}
                      onClick={() => void handleSessionSelect(session.session_id)}
                    >
                      <span>{session.title || session.session_id}</span>
                      <span className="room-option-persona">
                        {session.description || "No description"}
                        {session.active_room ? ` - ${roomById(String(session.active_room))?.title || session.active_room}` : ""}
                      </span>
                    </button>
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
                    onChange={(event) => setSessionTitleDraft(event.target.value)}
                  />
                  <textarea
                    className="session-input session-description"
                    value={sessionDescriptionDraft}
                    placeholder="Describe this work thread"
                    onChange={(event) => setSessionDescriptionDraft(event.target.value)}
                    rows={3}
                  />
                  <div className="toolbar-row">
                    <button type="button" className="primary" onClick={() => void handleCreateSession()}>
                      Create Session
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {roomMenuOpen ? (
            <div className="dropdown-panel">
              {ROOM_GROUPS.map((group) => (
                <div key={group} className="dropdown-group">
                  <div className="dropdown-group-title">{group}</div>
                  <div className="dropdown-grid">
                    {ROOMS.filter((room) => room.group === group).map((room) => (
                      <button
                        key={room.id}
                        type="button"
                        className={`ghost room-option ${room.id === activeRoom ? "toolbar-button-active" : ""}`}
                        onClick={() => void handleRoomSelect(room.id)}
                      >
                        <span>{room.title}</span>
                        <span className="room-option-persona">{room.persona}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {saveMenuOpen ? (
            <div className="dropdown-panel">
              <div className="dropdown-group">
                <div className="dropdown-group-title">File Type</div>
                <div className="toolbar-row">
                  {FILE_KIND_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`ghost toolbar-button ${fileKind === option.value ? "toolbar-button-active" : ""}`}
                      onClick={() => setFileKind(option.value)}
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
                      onClick={() => setFileScope(option.value)}
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
                      onClick={() => setPrivateBucket(option.value)}
                      disabled={fileScope !== "private"}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <div className="muted">
                  Private files are saved in a separate database. Access them through Nancy memo requests.
                </div>
              </div>
              <div className="dropdown-group">
                <div className="toolbar-row">
                  <button type="button" className="secondary" onClick={openPicker}>
                    Choose file
                  </button>
                  <button type="button" className="primary" onClick={() => void submitSelectedUpload()} disabled={!selectedUploadReady}>
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
          ) : null}

          {loadMenuOpen ? (
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
                      onClick={() => setLoadScope(option.value)}
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
                        onClick={() => setPrivateBucket(option.value)}
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
                  {(loadScope === "private" ? privateFiles : workspaceFiles).length ? (
                    (loadScope === "private" ? privateFiles : workspaceFiles).map((file) => (
                      <div key={file.file_id} className="load-item">
                        <button type="button" className="load-item-main" onClick={() => void openReader(file)}>
                          <span className="load-item-title">{file.original_name}</span>
                          <span className="load-item-meta">{fileSortLabel(file)}</span>
                        </button>
                        <button type="button" className="secondary load-download-button" onClick={() => downloadFile(file)}>
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
          ) : null}
        </div>
      </section>

      <section className="card lobby-chat-card">
        <div className="terminal-panel-title">Chat Window</div>
        <div className="room-status-bar">{roomStatus}</div>
        {backendBanner ? <div className="backend-banner">{backendBanner}</div> : null}
        <div className="toolbar-row" style={{ marginBottom: 10 }}>
          <button
            type="button"
            className={`ghost toolbar-button ${chatScope === "room" ? "toolbar-button-active" : ""}`}
            onClick={() => setChatScope("room")}
          >
            Room Chat
          </button>
          <button
            type="button"
            className={`ghost toolbar-button ${chatScope === "global" ? "toolbar-button-active" : ""}`}
            onClick={() => setChatScope("global")}
          >
            Global Chat
          </button>
        </div>
        <section ref={logRef} className="chat lobby-chat-window">
          {visibleMessages.map((message) => (
            <div key={message.id} className={`bubble ${message.role === "system" ? "assistant" : message.role}`}>
              <div className="chat-role">
                {message.role === "user" ? "You" : message.role === "system" ? "System" : message.speaker || activePersona}
              </div>
              <div className="chat-text">{message.text}</div>
              </div>
            ))}
          {loading ? <div className="muted">Processing...</div> : null}
        </section>
        {error ? <div className="error">{error}</div> : null}

        <div className="composer-actions">
          <button
            type="button"
            className="ghost composer-plus"
            onClick={() => {
              setAttachmentOpen((current) => !current);
              setAttachmentMode("download");
              setWorkspaceMenuOpen(false);
              setSaveMenuOpen(false);
              setRoomMenuOpen(false);
              setLoadMenuOpen(false);
              setSessionMenuOpen(false);
            }}
            aria-label="Open file actions"
          >
            +
          </button>
          <form className="composer lobby-composer" onSubmit={handleSubmit}>
            <textarea
              ref={draftRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleDraftKeyDown}
              placeholder="Speak to the receptionist..."
              rows={3}
            />
            <button className="primary" type="submit" disabled={loading || !draft.trim()}>
              Send
            </button>
          </form>
        </div>

        {attachmentOpen ? (
          <div className="dropdown-panel attachment-panel">
            <div className="toolbar-row">
              <button
                type="button"
                className={`ghost toolbar-button ${attachmentMode === "download" ? "toolbar-button-active" : ""}`}
                onClick={() => {
                  setAttachmentMode("download");
                  void refreshFiles();
                }}
              >
                Download
              </button>
              <button
                type="button"
                className={`ghost toolbar-button ${attachmentMode === "upload" ? "toolbar-button-active" : ""}`}
                onClick={() => setAttachmentMode("upload")}
              >
                Upload
              </button>
            </div>

            {attachmentMode === "upload" ? (
              <div className="stack">
                <div className="toolbar-row">
                  <button type="button" className="secondary" onClick={openPicker}>
                    Choose file
                  </button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => void submitSelectedUpload()}
                    disabled={!selectedUploadReady}
                  >
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
                        <span className="room-option-persona">{file.scope || "workspace"} · {file.kind || "file"}</span>
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
                        <span className="room-option-persona">private · {file.kind || "file"}</span>
                      </a>
                    ))
                  ) : (
                    <div className="muted">No private files yet.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </section>

      {readerOpen ? (
        <section className="card document-reader-shell">
          <div className="terminal-panel-title">Document Reader</div>
          <div className="toolbar-row">
            <div className="reader-title">{readerTitle}</div>
            {readerFile ? (
              <button type="button" className="secondary" onClick={() => downloadFile(readerFile)}>
                Download
              </button>
            ) : null}
            <button type="button" className="ghost toolbar-button" onClick={() => setReaderOpen(false)}>
              Close
            </button>
          </div>
          <div className="reader-window">
            {readerLoading ? <div className="muted">Loading document...</div> : <pre>{readerText || "Select a document."}</pre>}
          </div>
        </section>
      ) : null}
    </main>
  );
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Unable to read file."));
    reader.readAsDataURL(file);
  });
}

function mapTranscriptEntries(entries: TranscriptEntry[]): Message[] {
  const mapped = entries
    .filter((entry) => typeof entry.text === "string" && entry.text.trim())
    .map((entry, index) => {
      const entryRole = String(entry.role || "").trim().toLowerCase();
      const role: Message["role"] = entryRole === "user" ? "user" : entryRole === "system" ? "system" : "assistant";
      const speaker =
        typeof entry.speaker === "string" && entry.speaker.trim()
          ? entry.speaker
          : role === "user"
            ? "You"
            : role === "system"
              ? "System"
              : undefined;
      const idSource = typeof entry.ts === "string" && entry.ts.trim() ? entry.ts : `${index}`;
      return {
        id: `${idSource}-${index}`,
        role,
        speaker,
        text: String(entry.text),
        room: typeof entry.room === "string" && entry.room.trim() ? entry.room : undefined,
        sessionId: typeof entry.session_id === "string" && entry.session_id.trim() ? entry.session_id : undefined,
      };
    });
  const conversational = mapped.filter((entry) => entry.role !== "system");
  return conversational.length ? mapped : mapped.slice(-12);
}
