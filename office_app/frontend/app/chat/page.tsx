"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  activateSession,
  activateWorkspace,
  callTool,
  createSession,
  createWorkspace,
  deleteSession,
  deleteWorkspace,
  getCurrentUser,
  listWorkspaceFiles,
  listWorkspaceArtifacts,
  listSessions,
  listWorkspaces,
  loadTranscript,
  request,
  requestText,
  renameSession,
  updateWorkspaceMetadata,
  type FileRecord,
  type SessionRecord,
  type UserRecord,
  type WorkspaceRecord,
  type ArtifactRecord,
} from "@/lib/api";
import { clearStoredSessionId, getSessionShortLabel, getStoredSessionId, setStoredSessionId } from "@/lib/session";
import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
import { ChatTranscript } from "./ChatTranscript";
import { ChatToolbar } from "./ChatToolbar";
import { DocumentReader } from "./DocumentReader";
import { AttachmentPanel, LoadFilePanel, SaveFilePanel } from "./FilePanels";
import {
  assistantMessageForResponse,
  backendDisconnectedMessage,
  createMessage,
  deleteSessionNotice,
  deleteSessionRoomPersona,
  hiddenSessionsWith,
  integrationConfirmationMessage,
  providerBadgeForResponse,
  roomPersonaValues,
  sessionById,
  sessionDraftValues,
  speakerForStructuredResponse,
  visibleMessagesForScope,
  visibleSessions,
  workspaceById,
  workspaceDraftValues,
  workspaceLabelById,
  workspaceMetadataValues,
} from "./helpers";
import { RoomDirectoryPanel } from "./RoomDirectoryPanel";
import { SessionNamePrompt, SessionPanel } from "./SessionPanel";
import {
  DEFAULT_PERSONA,
  DEFAULT_ROOM_ID,
  type ChatScope,
  type ChatStructuredResponse,
  type DeleteSessionStructuredResponse,
  type DeleteWorkspaceStructuredResponse,
  type LobbyState,
  type Message,
  type ProviderBadge,
} from "./types";
import { useChatFiles } from "./useChatFiles";
import { useChatMenus } from "./useChatMenus";
import { useChatRoomState } from "./useChatRoomState";
import { WorkspacePanel } from "./WorkspacePanel";

export default function ChatPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const {
    attachmentMode,
    attachmentOpen,
    loadMenuOpen,
    roomMenuOpen,
    saveMenuOpen,
    sessionMenuOpen,
    workspaceMenuOpen,
    setAttachmentMode,
    setLoadMenuOpen,
    setRoomMenuOpen,
    setSaveMenuOpen,
    setSessionMenuOpen,
    setWorkspaceMenuOpen,
    toggleAttachmentPanel,
    toggleLoadMenu,
    toggleRoomMenu,
    toggleSaveMenu,
    toggleSessionMenu,
    toggleWorkspaceMenu,
  } = useChatMenus();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [workspacesLoading, setWorkspacesLoading] = useState(false);
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState("");
  const [newWorkspaceTitleDraft, setNewWorkspaceTitleDraft] = useState("");
  const [workspaceTitleDraft, setWorkspaceTitleDraft] = useState("");
  const [workspaceDescriptionDraft, setWorkspaceDescriptionDraft] = useState("");
  const [workspaceSelectionId, setWorkspaceSelectionId] = useState("");
  const [workspaceSelectionSessions, setWorkspaceSelectionSessions] = useState<SessionRecord[]>([]);
  const [workspaceSelectionArtifacts, setWorkspaceSelectionArtifacts] = useState<ArtifactRecord[]>([]);
  const [workspaceSelectionFiles, setWorkspaceSelectionFiles] = useState<FileRecord[]>([]);
  const [workspaceSelectionLoading, setWorkspaceSelectionLoading] = useState(false);
  const [activeWorkspaceLabel, setActiveWorkspaceLabel] = useState("");
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState("");
  const [hiddenSessionIds, setHiddenSessionIds] = useState<string[]>([]);
  const [sessionActionNotice, setSessionActionNotice] = useState("");
  const [sessionTitleDraft, setSessionTitleDraft] = useState("");
  const [sessionDescriptionDraft, setSessionDescriptionDraft] = useState("");
  const [sessionPromptTargetId, setSessionPromptTargetId] = useState("");
  const [chatScope, setChatScope] = useState<ChatScope>("room");
  const [backendBanner, setBackendBanner] = useState("");
  const [providerBadge, setProviderBadge] = useState<ProviderBadge | null>(null);
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [confirmingIntegrationId, setConfirmingIntegrationId] = useState("");
  const [confirmedIntegrationIds, setConfirmedIntegrationIds] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const hiddenSessionIdsRef = useRef<Set<string>>(new Set());
  const {
    activePersona,
    activeRoom,
    currentTitle,
    recentRooms,
    roomStatus,
    switchingRoom,
    appendRoomTransition,
    applyActiveRoom,
    applyHydratedMessages,
    handleRoomSelect,
  } = useChatRoomState({
    sessionId,
    setBackendBanner,
    setChatScope,
    setError,
    setMessages,
    setRoomMenuOpen,
  });
  const {
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
  } = useChatFiles({
    activeRoom,
    sessionId,
    setAttachmentMode,
    setBackendBanner,
    setError,
    setLoadMenuOpen,
    setSaveMenuOpen,
    appendSavedFileMessage: (text) => {
      appendMessage(
        createMessage({
          role: "assistant",
          speaker: "System",
          text,
          room: activeRoom,
          sessionId,
        }),
      );
    },
  });

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
        const nextRoomPersona = roomPersonaValues(structured);
        setWorkspaceId(nextWorkspace);
        setActiveWorkspaceLabel(nextWorkspace);
        applyActiveRoom(nextRoomPersona.room, nextRoomPersona.persona);
        applyHydratedMessages(nextRoomPersona.room, nextRoomPersona.persona, transcriptEntries, sessionId);
        void refreshWorkspaces(nextWorkspace);
        void refreshSessions();
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to load lobby state.";
        showError(message);
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

  useEffect(() => {
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    const loadUser = async () => {
      try {
        const user = await getCurrentUser();
        if (!cancelled) {
          setCurrentUser(user);
        }
      } catch {
        if (!cancelled) {
          setCurrentUser(null);
        }
      }
    };
    void loadUser();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const sessionLabel = useMemo(() => getSessionShortLabel(sessionId), [sessionId]);
  const currentWorkspace = useMemo(() => workspaceById(workspaces, workspaceId), [workspaceId, workspaces]);
  const currentWorkspaceLabel = activeWorkspaceLabel || currentWorkspace?.label || workspaceId || "Unassigned";
  const currentSession = useMemo(() => sessionById(sessions, sessionId), [sessionId, sessions]);
  const currentSessionTitle = currentSession?.title || sessionLabel;
  const currentSessionDescription = currentSession?.description || "";
  const visibleMessages = useMemo(
    () => visibleMessagesForScope(messages, sessionId, chatScope, activeRoom),
    [activeRoom, chatScope, messages, sessionId],
  );

  function clearFeedback() {
    setError("");
    setBackendBanner("");
  }

  function showError(message: string) {
    setError(message);
    setBackendBanner(backendDisconnectedMessage(message));
  }

  function appendMessage(message: Message) {
    setMessages((current) => [...current, message]);
  }

  function applyWorkspaceDraft(
    workspace: WorkspaceRecord | undefined,
    fallbackTitle = "",
    fallbackDescription = "",
  ) {
    const draftValues = workspaceDraftValues(workspace, fallbackTitle, fallbackDescription);
    setWorkspaceTitleDraft(draftValues.title);
    setWorkspaceDescriptionDraft(draftValues.description);
  }

  function applySessionDraft(
    session: Pick<SessionRecord, "title" | "description"> | undefined,
    fallbackTitle = "",
    fallbackDescription = "",
  ) {
    const draftValues = sessionDraftValues(session, fallbackTitle, fallbackDescription);
    setSessionTitleDraft(draftValues.title);
    setSessionDescriptionDraft(draftValues.description);
  }

  function applyWorkspaceSelectionDetails(
    nextSessions: SessionRecord[],
    nextArtifacts: ArtifactRecord[],
    nextFiles: FileRecord[],
  ) {
    setWorkspaceSelectionSessions(nextSessions);
    setWorkspaceSelectionArtifacts(nextArtifacts);
    setWorkspaceSelectionFiles(nextFiles);
  }

  function clearSessionPrompt() {
    setSessionPromptTargetId("");
  }

  function showSessionActionNotice(notice: string, options: { banner?: boolean } = {}) {
    if (options.banner) {
      setBackendBanner(notice);
    }
    setSessionActionNotice(notice);
  }

  function applySessionWorkspace(
    nextSessionId: string,
    nextWorkspaceId: string,
    workspaceLabel: string,
    options: { persistSession?: boolean; forceRoomScope?: boolean } = {},
  ) {
    if (options.persistSession) {
      setStoredSessionId(nextSessionId);
    }
    setSessionId(nextSessionId);
    setWorkspaceId(nextWorkspaceId);
    setActiveWorkspaceLabel(workspaceLabel);
    if (options.forceRoomScope) {
      setChatScope("room");
    }
  }

  async function hydrateThreadMessages(nextSessionId: string, room: string, persona: string) {
    applyActiveRoom(room, persona);
    const transcriptEntries = await loadTranscript(120, nextSessionId);
    applyHydratedMessages(room, persona, transcriptEntries, nextSessionId);
  }

  async function refreshWorkspaces(activeWorkspaceId?: string): Promise<WorkspaceRecord[]> {
    if (!sessionId) {
      return [];
    }
    setWorkspacesLoading(true);
    try {
      const response = await listWorkspaces();
      setWorkspaces(response);
      const targetId = activeWorkspaceId || workspaceId;
      const active = workspaceById(response, targetId);
      if (active) {
        applyWorkspaceDraft(active);
        setActiveWorkspaceLabel(String(active.label || active.workspace_id || ""));
        if (!workspaceSelectionId) {
          setWorkspaceSelectionId(String(active.workspace_id || ""));
        }
      }
      return response;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load workspaces.";
      showError(message);
      return [];
    } finally {
      setWorkspacesLoading(false);
    }
  }

  async function refreshSessions(activeSessionId?: string) {
    if (!sessionId) {
      return;
    }
    setSessionsLoading(true);
    try {
      const response = await listSessions();
      const hiddenIds = hiddenSessionIdsRef.current;
      setSessions(visibleSessions(response, hiddenIds));
      const targetId = activeSessionId || sessionId;
      const active = sessionById(response, targetId);
      if (active) {
        applySessionDraft(active);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load sessions.";
      showError(message);
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
    const stateResponse = await callTool("office.state_get", { session_id: chosenSessionId });
    const structured = stateResponse.structuredContent as LobbyState | undefined;
    if (!structured) {
      return;
    }
    const nextWorkspace = String(structured.workspace_id || workspaceId);
    const nextRoomPersona = roomPersonaValues(structured);
    applySessionWorkspace(chosenSessionId, nextWorkspace, workspaceLabelById(workspaces, nextWorkspace), {
      persistSession: true,
    });
    applyActiveRoom(nextRoomPersona.room, nextRoomPersona.persona);
    applyHydratedMessages(nextRoomPersona.room, nextRoomPersona.persona, transcriptEntries, chosenSessionId);
  }

  async function refreshWorkspaceSessionLists(nextWorkspaceId: string, nextSessionId: string) {
    await refreshWorkspaces(nextWorkspaceId);
    await refreshSessions(nextSessionId);
  }

  async function handleWorkspaceSelect(targetWorkspaceId: string) {
    if (!targetWorkspaceId || targetWorkspaceId === workspaceId) {
      setWorkspaceMenuOpen(false);
      return;
    }
    clearFeedback();
    try {
      const activated = await activateWorkspace(targetWorkspaceId);
      const nextWorkspaceId = String(activated.workspace_id || targetWorkspaceId);
      const nextSessionId = String(activated.session_id || sessionId);
      const workspaceState = activated as { workspace_state?: LobbyState };
      const nextRoomPersona = roomPersonaValues(workspaceState.workspace_state);
      applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
        persistSession: true,
        forceRoomScope: true,
      });
      await hydrateThreadMessages(nextSessionId, nextRoomPersona.room, nextRoomPersona.persona);
      await refreshWorkspaceSessionLists(nextWorkspaceId, nextSessionId);
      await refreshFiles(nextSessionId, nextRoomPersona.room);
      setWorkspaceMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to activate workspace.";
      showError(message);
    }
  }

  async function handleCreateWorkspace() {
    const title = newWorkspaceTitleDraft.trim() || "New Workspace";
    clearFeedback();
    try {
      const created = await createWorkspace(title);
      const nextWorkspaceId = String(created.workspace_id || "");
      const activated = await activateWorkspace(nextWorkspaceId);
      const nextSessionId = String(activated.session_id || sessionId);
      applySessionWorkspace(nextSessionId, nextWorkspaceId, String(created.label || title), {
        persistSession: true,
        forceRoomScope: true,
      });
      const draftValues = workspaceDraftValues(created, title);
      setWorkspaceTitleDraft(draftValues.title);
      setNewWorkspaceTitleDraft("");
      await hydrateThreadMessages(nextSessionId, DEFAULT_ROOM_ID, DEFAULT_PERSONA);
      await refreshWorkspaceSessionLists(nextWorkspaceId, nextSessionId);
      await refreshFiles(nextSessionId, DEFAULT_ROOM_ID);
      setWorkspaceMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create workspace.";
      showError(message);
    }
  }

  async function loadWorkspaceSelection(targetWorkspaceId: string, preserveDrafts = false) {
    if (!targetWorkspaceId) {
      return;
    }
    setWorkspaceSelectionId(targetWorkspaceId);
    if (!preserveDrafts) {
      const selectedWorkspace = workspaceById(workspaces, targetWorkspaceId);
      applyWorkspaceDraft(selectedWorkspace);
    }
    setWorkspaceSelectionLoading(true);
    try {
      const [sessionsForWorkspace, artifactsForWorkspace, filesForWorkspace] = await Promise.all([
        listSessions(targetWorkspaceId),
        listWorkspaceArtifacts(targetWorkspaceId),
        listWorkspaceFiles(targetWorkspaceId),
      ]);
      applyWorkspaceSelectionDetails(sessionsForWorkspace, artifactsForWorkspace, filesForWorkspace);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load selected workspace details.";
      showError(message);
      applyWorkspaceSelectionDetails([], [], []);
    } finally {
      setWorkspaceSelectionLoading(false);
    }
  }

  async function handleSaveWorkspaceMetadata() {
    const targetWorkspaceId = workspaceSelectionId || workspaceId;
    if (!targetWorkspaceId) {
      return;
    }
    clearFeedback();
    try {
      const selectedWorkspace = workspaceById(workspaces, targetWorkspaceId);
      await updateWorkspaceMetadata(
        targetWorkspaceId,
        workspaceMetadataValues(
          selectedWorkspace,
          workspaceTitleDraft,
          workspaceDescriptionDraft,
          currentWorkspaceLabel,
          targetWorkspaceId,
        ),
      );
      const refreshed = await refreshWorkspaces(workspaceId);
      const refreshedSelected = workspaceById(refreshed, targetWorkspaceId);
      if (refreshedSelected) {
        applyWorkspaceDraft(refreshedSelected);
      }
      await loadWorkspaceSelection(targetWorkspaceId, true);
      showSessionActionNotice("Workspace details saved.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to save workspace details.";
      showError(message);
    }
  }

  async function handleDeleteWorkspace(targetWorkspaceId: string) {
    if (!targetWorkspaceId || deletingWorkspaceId === targetWorkspaceId) {
      return;
    }
    const targetWorkspace = workspaceById(workspaces, targetWorkspaceId);
    const targetLabel = targetWorkspace?.label || targetWorkspaceId;
    if (!window.confirm(`Archive workspace "${targetLabel}"? It will disappear from your workspace list.`)) {
      return;
    }
    setDeletingWorkspaceId(targetWorkspaceId);
    clearFeedback();
    try {
      const response = await deleteWorkspace(targetWorkspaceId);
      const structured = response.structuredContent as DeleteWorkspaceStructuredResponse | undefined;
      const nextWorkspaceId = String(structured?.workspace_id || response.workspace_id || workspaceId);
      const nextSessionId = String(structured?.session_id || response.session_id || sessionId);
      const nextRoomPersona = roomPersonaValues(structured?.workspace_state);
      const archivedLabel = String(structured?.archived_workspace?.label || targetLabel || targetWorkspaceId);
      const switchedWorkspace = Boolean(structured?.switched_workspace);
      const selectionDeleted = workspaceSelectionId === targetWorkspaceId;

      const refreshed = await refreshWorkspaces(nextWorkspaceId);
      if (selectionDeleted) {
        setWorkspaceSelectionId(nextWorkspaceId);
      }

      if (switchedWorkspace || targetWorkspaceId === workspaceId || selectionDeleted) {
        applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(refreshed, nextWorkspaceId), {
          persistSession: true,
          forceRoomScope: true,
        });
        await hydrateThreadMessages(nextSessionId, nextRoomPersona.room, nextRoomPersona.persona);
        await refreshSessions(nextSessionId);
        await refreshFiles(nextSessionId, nextRoomPersona.room);
      }

      await loadWorkspaceSelection(nextWorkspaceId, true);
      showSessionActionNotice(`Archived workspace ${archivedLabel}.`);
      setWorkspaceMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to archive workspace.";
      showError(message);
    } finally {
      setDeletingWorkspaceId("");
    }
  }

  async function handleSessionSelect(targetSessionId: string) {
    if (!targetSessionId || targetSessionId === sessionId) {
      setSessionMenuOpen(false);
      return;
    }
    clearFeedback();
    try {
      const response = await activateSession(targetSessionId);
      const nextSessionId = String(response.session_id || targetSessionId);
      const nextWorkspaceId = String(response.active_workspace_id || response.workspace_id || workspaceId);
      applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
        persistSession: true,
      });
      applySessionDraft(response);
      await refreshCurrentThread(nextSessionId);
      await refreshWorkspaces(nextWorkspaceId);
      await refreshFiles(nextSessionId);
      await refreshSessions(nextSessionId);
      setChatScope("room");
      setSessionMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to activate session.";
      showError(message);
    }
  }

  useEffect(() => {
    if (!workspaceMenuOpen) {
      return;
    }
    const initialId = workspaceSelectionId || workspaceId;
    if (initialId) {
      void loadWorkspaceSelection(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceMenuOpen, workspaceId]);

  async function handleDeleteSession(targetSessionId: string) {
    if (!targetSessionId || deletingSessionId === targetSessionId) {
      return;
    }
    const target = sessionById(sessions, targetSessionId);
    const targetTitle = target?.title || targetSessionId;
    if (!window.confirm(`Delete session "${targetTitle}" and its transcript?`)) {
      return;
    }
    setDeletingSessionId(targetSessionId);
    clearFeedback();
    setSessionActionNotice("");
    try {
      const response = await deleteSession(targetSessionId, sessionId);
      const structured = response.structuredContent as DeleteSessionStructuredResponse | undefined;
      const nextSessionId = String(structured?.session_id || response.session_id || sessionId);
      const nextWorkspaceId = String(structured?.workspace_id || response.workspace_id || workspaceId);
      const activeRoomPersona = deleteSessionRoomPersona(structured, activeRoom, activePersona);
      const deletedWasCurrent = targetSessionId === sessionId;
      const replacementTitle = String(structured?.active_session?.title || nextSessionId || "a fresh session");

      hiddenSessionIdsRef.current = hiddenSessionsWith(hiddenSessionIdsRef.current, targetSessionId);
      setHiddenSessionIds(Array.from(hiddenSessionIdsRef.current));
      setSessions((current) => visibleSessions(current, hiddenSessionIdsRef.current));

      applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
        persistSession: true,
        forceRoomScope: true,
      });

      await refreshSessions(nextSessionId);
      await refreshWorkspaces(nextWorkspaceId);

      if (deletedWasCurrent && nextSessionId) {
        applyActiveRoom(activeRoomPersona.room, activeRoomPersona.persona);
        await refreshCurrentThread(nextSessionId);
        await refreshFiles(nextSessionId, activeRoomPersona.room);
      }

      if (Boolean(structured?.created_replacement_session)) {
        setSessionPromptTargetId(nextSessionId);
        applySessionDraft(structured?.active_session, "New Session", "Fresh session.");
      } else {
        clearSessionPrompt();
      }

      const notice = deleteSessionNotice(targetTitle, deletedWasCurrent, replacementTitle);
      showSessionActionNotice(notice, { banner: true });

      appendMessage(
        createMessage({
          role: "system",
          speaker: "System",
          text: notice,
          room: activeRoomPersona.room || activeRoom,
          sessionId: nextSessionId || sessionId,
        }),
      );

      setSessionMenuOpen(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to delete session.";
      showError(message);
    } finally {
      setDeletingSessionId("");
    }
  }

  async function handleSaveSessionNamePrompt() {
    const targetSessionId = sessionPromptTargetId;
    if (!targetSessionId) {
      return;
    }
    const title = sessionTitleDraft.trim() || "New Session";
    const description = sessionDescriptionDraft.trim() || title;
    clearFeedback();
    try {
      const renamed = await renameSession(targetSessionId, title, description);
      const nextSessionId = String(renamed.session_id || targetSessionId);
      applySessionDraft(renamed, title, description);
      setStoredSessionId(nextSessionId);
      setSessionId(nextSessionId);
      clearSessionPrompt();
      await refreshSessions(nextSessionId);
      await refreshWorkspaces(workspaceId);
      await refreshCurrentThread(nextSessionId);
      showSessionActionNotice(`Renamed session to ${renamed.title || title}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to rename session.";
      showError(message);
    }
  }

  function handleCancelSessionNamePrompt() {
    clearSessionPrompt();
  }

  async function handleCreateSession() {
    const title = sessionTitleDraft.trim() || "New Session";
    const description = sessionDescriptionDraft.trim() || title;
    clearFeedback();
    try {
      const created = await createSession(title, description);
      const nextSessionId = String(created.session_id || "");
      const nextWorkspaceId = String(created.active_workspace_id || created.workspace_id || workspaceId);
      applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
        persistSession: true,
        forceRoomScope: true,
      });
      applySessionDraft(created, title, description);
      applyActiveRoom(DEFAULT_ROOM_ID, DEFAULT_PERSONA);
      await refreshCurrentThread(nextSessionId);
      await refreshWorkspaces(nextWorkspaceId);
      await refreshFiles(nextSessionId, DEFAULT_ROOM_ID);
      await refreshSessions(nextSessionId);
      setSessionMenuOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create session.";
      showError(message);
    }
  }

  async function sendText(text: string) {
    const value = text.trim();
    if (!value || loading) {
      return;
    }
    const outgoingSessionId = sessionId;
    setDraft("");
    clearFeedback();
    setLoading(true);
    appendMessage(createMessage({ role: "user", text: value, room: activeRoom, sessionId: outgoingSessionId }));
    try {
      const response = await request(value, outgoingSessionId);
      const assistantText = requestText(response);
      const structuredResponse = response.structuredContent as ChatStructuredResponse | undefined;
      const nextWorkspaceId = String(response.workspace_id || structuredResponse?.workspace_id || workspaceId);
      const nextSessionId = String(response.session_id || structuredResponse?.session_id || outgoingSessionId);
      const nextRoomPersona = roomPersonaValues(structuredResponse, activeRoom, activePersona);
      const nextRoom = nextRoomPersona.room;
      const nextPersona = nextRoomPersona.persona;
      const nextSpeaker = speakerForStructuredResponse(structuredResponse, nextPersona);
      const nextProviderBadge = providerBadgeForResponse(structuredResponse);
      if (nextProviderBadge) {
        setProviderBadge(nextProviderBadge);
      }
      if (nextSessionId && nextSessionId !== outgoingSessionId) {
        applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
          persistSession: true,
          forceRoomScope: true,
        });
        await refreshCurrentThread(nextSessionId);
        await refreshWorkspaces(nextWorkspaceId);
        await refreshSessions(nextSessionId);
        return;
      }
      applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
        persistSession: Boolean(nextSessionId),
      });
      applyActiveRoom(nextRoom, nextPersona);
      appendMessage(assistantMessageForResponse(structuredResponse, assistantText, nextSpeaker, nextRoom, nextSessionId));
      if (nextRoom !== activeRoom || nextPersona !== activePersona) {
        appendRoomTransition(nextRoom, nextPersona);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed.";
      showError(message);
      appendMessage(createMessage({ role: "assistant", text: message, room: activeRoom, sessionId: outgoingSessionId }));
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

  async function confirmIntegrationAction(confirmationId: string, room: string, targetSessionId: string) {
    if (!confirmationId || confirmingIntegrationId) {
      return;
    }
    setConfirmingIntegrationId(confirmationId);
    setError("");
    try {
      const response = await callTool("office.integration_confirm", { confirmation_id: confirmationId, session_id: targetSessionId });
      setConfirmedIntegrationIds((current) => [...current, confirmationId]);
      appendMessage(integrationConfirmationMessage(requestText(response), room, targetSessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to confirm the external action.");
    } finally {
      setConfirmingIntegrationId("");
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
          <ChatHeader
            currentSessionDescription={currentSessionDescription}
            currentSessionTitle={currentSessionTitle}
            currentTitle={currentTitle}
            currentUser={currentUser}
            currentWorkspaceLabel={currentWorkspaceLabel}
            providerBadge={providerBadge}
            sessionId={sessionId}
            workspaceMenuOpen={workspaceMenuOpen}
            onAdminOpen={() => router.push("/admin")}
            onProfileOpen={() => router.push("/profile")}
            onWorkspaceMenuToggle={toggleWorkspaceMenu}
          />

          {workspaceMenuOpen ? (
            <WorkspacePanel
              deletingWorkspaceId={deletingWorkspaceId}
              newWorkspaceTitleDraft={newWorkspaceTitleDraft}
              workspaceDescriptionDraft={workspaceDescriptionDraft}
              workspaceSelectionArtifacts={workspaceSelectionArtifacts}
              workspaceSelectionFiles={workspaceSelectionFiles}
              workspaceSelectionId={workspaceSelectionId}
              workspaceSelectionLoading={workspaceSelectionLoading}
              workspaceSelectionSessions={workspaceSelectionSessions}
              workspaceTitleDraft={workspaceTitleDraft}
              workspaces={workspaces}
              workspacesLoading={workspacesLoading}
              onCreateWorkspace={() => void handleCreateWorkspace()}
              onDeleteWorkspace={(targetWorkspaceId) => void handleDeleteWorkspace(targetWorkspaceId)}
              onLoadWorkspaceSelection={(targetWorkspaceId) => void loadWorkspaceSelection(targetWorkspaceId)}
              onNewWorkspaceTitleDraftChange={setNewWorkspaceTitleDraft}
              onSaveWorkspaceMetadata={() => void handleSaveWorkspaceMetadata()}
              onWorkspaceDescriptionDraftChange={setWorkspaceDescriptionDraft}
              onWorkspaceSelect={(targetWorkspaceId) => void handleWorkspaceSelect(targetWorkspaceId)}
              onWorkspaceTitleDraftChange={setWorkspaceTitleDraft}
            />
          ) : null}
          <ChatToolbar
            activeRoom={activeRoom}
            loadMenuOpen={loadMenuOpen}
            recentRooms={recentRooms}
            roomMenuOpen={roomMenuOpen}
            saveMenuOpen={saveMenuOpen}
            sessionMenuOpen={sessionMenuOpen}
            onLoadMenuToggle={toggleLoadMenu}
            onRoomMenuToggle={toggleRoomMenu}
            onRoomSelect={(roomId) => void handleRoomSelect(roomId)}
            onSaveMenuToggle={toggleSaveMenu}
            onSessionMenuToggle={toggleSessionMenu}
          />

          {sessionMenuOpen ? (
            <SessionPanel
              deletingSessionId={deletingSessionId}
              sessionActionNotice={sessionActionNotice}
              sessionDescriptionDraft={sessionDescriptionDraft}
              sessionId={sessionId}
              sessions={sessions}
              sessionsLoading={sessionsLoading}
              sessionTitleDraft={sessionTitleDraft}
              onCreateSession={() => void handleCreateSession()}
              onDeleteSession={(targetSessionId) => void handleDeleteSession(targetSessionId)}
              onSessionDescriptionDraftChange={setSessionDescriptionDraft}
              onSessionSelect={(targetSessionId) => void handleSessionSelect(targetSessionId)}
              onSessionTitleDraftChange={setSessionTitleDraft}
            />
          ) : null}
          <SessionNamePrompt
            sessionDescriptionDraft={sessionDescriptionDraft}
            sessionPromptTargetId={sessionPromptTargetId}
            sessionTitleDraft={sessionTitleDraft}
            onCancelSessionNamePrompt={handleCancelSessionNamePrompt}
            onSaveSessionNamePrompt={() => void handleSaveSessionNamePrompt()}
            onSessionDescriptionDraftChange={setSessionDescriptionDraft}
            onSessionTitleDraftChange={setSessionTitleDraft}
          />
          {roomMenuOpen ? <RoomDirectoryPanel activeRoom={activeRoom} onRoomSelect={(roomId) => void handleRoomSelect(roomId)} /> : null}

          {saveMenuOpen ? (
            <SaveFilePanel
              fileKind={fileKind}
              fileScope={fileScope}
              lastSavedFile={lastSavedFile}
              privateBucket={privateBucket}
              selectedUploadName={selectedUploadName}
              selectedUploadReady={selectedUploadReady}
              uploadNote={uploadNote}
              onFileKindChange={setFileKind}
              onFileScopeChange={setFileScope}
              onOpenPicker={openPicker}
              onPrivateBucketChange={setPrivateBucket}
              onSubmitSelectedUpload={() => void submitSelectedUpload()}
            />
          ) : null}
          {loadMenuOpen ? (
            <LoadFilePanel
              loadScope={loadScope}
              privateBucket={privateBucket}
              privateFiles={privateFiles}
              workspaceFiles={workspaceFiles}
              onDownloadFile={downloadFile}
              onLoadScopeChange={setLoadScope}
              onOpenReader={(file) => void openReader(file)}
              onPrivateBucketChange={setPrivateBucket}
            />
          ) : null}
        </div>
      </section>

      <section className="card lobby-chat-card">
        <ChatTranscript
          activePersona={activePersona}
          activeRoom={activeRoom}
          backendBanner={backendBanner}
          chatScope={chatScope}
          confirmedIntegrationIds={confirmedIntegrationIds}
          confirmingIntegrationId={confirmingIntegrationId}
          error={error}
          loading={loading}
          logRef={logRef}
          messages={visibleMessages}
          roomStatus={roomStatus}
          sessionId={sessionId}
          onChatScopeChange={setChatScope}
          onConfirmIntegration={(confirmationId, room, targetSessionId) => void confirmIntegrationAction(confirmationId, room, targetSessionId)}
        />
        <ChatComposer
          activePersona={activePersona}
          draft={draft}
          draftRef={draftRef}
          loading={loading}
          onDraftChange={setDraft}
          onFileActionsToggle={() => {
            toggleAttachmentPanel();
          }}
          onKeyDown={handleDraftKeyDown}
          onSubmit={handleSubmit}
        />

        {attachmentOpen ? (
          <AttachmentPanel
            attachmentMode={attachmentMode}
            filesLoading={filesLoading}
            privateFiles={privateFiles}
            selectedUploadName={selectedUploadName}
            selectedUploadReady={selectedUploadReady}
            workspaceFiles={workspaceFiles}
            onAttachmentModeChange={setAttachmentMode}
            onOpenPicker={openPicker}
            onRefreshFiles={() => void refreshFiles()}
            onSubmitSelectedUpload={() => void submitSelectedUpload()}
          />
        ) : null}
      </section>
      {readerOpen ? (
        <DocumentReader
          readerFile={readerFile}
          readerLoading={readerLoading}
          readerText={readerText}
          readerTitle={readerTitle}
          onClose={() => setReaderOpen(false)}
          onDownload={downloadFile}
        />
      ) : null}
    </main>
  );
}
