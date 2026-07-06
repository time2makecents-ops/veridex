import { useEffect, useRef, useState } from "react";

import {
  activateSession,
  activateWorkspace,
  callTool,
  createSession,
  createWorkspace,
  deleteSession,
  deleteWorkspace,
  getCurrentUser,
  listWorkspaceArtifacts,
  listWorkspaceFiles,
  listSessions,
  listWorkspaces,
  loadTranscript,
  renameSession,
  updateWorkspaceMetadata,
  type ArtifactRecord,
  type FileRecord,
  type SessionRecord,
  type TranscriptEntry,
  type UserRecord,
  type WorkspaceRecord,
} from "@/lib/api";
import { clearStoredSessionId, setStoredSessionId } from "@/lib/session";

import {
  backendDisconnectedMessage,
  deleteSessionNotice,
  deleteSessionRoomPersona,
  hiddenSessionsWith,
  roomPersonaValues,
  sessionById,
  sessionDraftValues,
  visibleSessions,
  workspaceById,
  workspaceDraftValues,
  workspaceLabelById,
  workspaceMetadataValues,
} from "./helpers";
import {
  DEFAULT_PERSONA,
  DEFAULT_ROOM_ID,
  type ChatScope,
  type LobbyState,
  type Message,
  type NancyEmailComposeState,
  type SessionPromptMode,
  type WorkContextRecord,
} from "./types";

type UseChatWorkspaceSessionArgs = {
  activePersona: string;
  activeRoom: string;
  appendMessage: (message: Message) => void;
  applyActiveRoom: (room: string, persona: string) => void;
  applyHydratedMessages: (
    room: string,
    persona: string,
    transcriptEntries: TranscriptEntry[],
    hydratedSessionId?: string,
  ) => void;
  refreshFiles: (sessionId?: string, roomId?: string) => Promise<void>;
  sessionId: string;
  setBackendBanner: (message: string) => void;
  setChatScope: (scope: ChatScope) => void;
  setError: (message: string) => void;
  setPendingNancyCompose: (compose: NancyEmailComposeState | undefined) => void;
  setPendingBreakRoomJoke: (pending: LobbyState["pending_break_room_joke"] | undefined) => void;
  setPendingRoomNavigation: (pending: LobbyState["pending_room_navigation"] | undefined) => void;
  setPendingSessionList: (pending: LobbyState["pending_session_list"] | undefined) => void;
  setPendingWorkspaceSwitch: (pending: LobbyState["pending_workspace_switch"] | undefined) => void;
  setRoomMenuOpen: (open: boolean) => void;
  setActiveWorkContexts: (contexts: WorkContextRecord[]) => void;
  setSessionId: (value: string) => void;
  setSessionMenuOpen: (open: boolean) => void;
  setWorkspaceId: (value: string) => void;
  setWorkspaceMenuOpen: (open: boolean) => void;
  workspaceId: string;
};

export function useChatWorkspaceSession({
  activePersona,
  activeRoom,
  appendMessage,
  applyActiveRoom,
  applyHydratedMessages,
  refreshFiles,
  sessionId,
  setBackendBanner,
  setChatScope,
  setError,
  setPendingNancyCompose,
  setPendingBreakRoomJoke,
  setPendingRoomNavigation,
  setPendingSessionList,
  setPendingWorkspaceSwitch,
  setRoomMenuOpen,
  setActiveWorkContexts,
  setSessionId,
  setSessionMenuOpen,
  setWorkspaceId,
  setWorkspaceMenuOpen,
  workspaceId,
}: UseChatWorkspaceSessionArgs) {
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
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
  const [sessionPromptMode, setSessionPromptMode] = useState<SessionPromptMode>("create");
  const hiddenSessionIdsRef = useRef<Set<string>>(new Set());

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

  function clearFeedback() {
    setError("");
    setBackendBanner("");
  }

  function showError(message: string) {
    setError(message);
    setBackendBanner(backendDisconnectedMessage(message));
  }

  function applyWorkspaceDraft(workspace: WorkspaceRecord | undefined, fallbackTitle = "", fallbackDescription = "") {
    const draftValues = workspaceDraftValues(workspace, fallbackTitle, fallbackDescription);
    setWorkspaceTitleDraft(draftValues.title);
    setWorkspaceDescriptionDraft(draftValues.description);
  }

  function applySessionDraft(session: Pick<SessionRecord, "title" | "description"> | undefined, fallbackTitle = "", fallbackDescription = "") {
    const draftValues = sessionDraftValues(session, fallbackTitle, fallbackDescription);
    setSessionTitleDraft(draftValues.title);
    setSessionDescriptionDraft(draftValues.description);
  }

  function applyWorkspaceSelectionDetails(nextSessions: SessionRecord[], nextArtifacts: ArtifactRecord[], nextFiles: FileRecord[]) {
    setWorkspaceSelectionSessions(nextSessions);
    setWorkspaceSelectionArtifacts(nextArtifacts);
    setWorkspaceSelectionFiles(nextFiles);
  }

  function clearSessionPrompt() {
    setSessionPromptTargetId("");
    setSessionPromptMode("create");
  }

  function syncPendingSessionPrompt(nextSessionId: string, workspaceState: LobbyState | undefined) {
    if (workspaceState?.pending_session_rename) {
      setSessionPromptMode("rename");
      setSessionPromptTargetId(nextSessionId);
      return;
    }
    if (workspaceState?.pending_session_create) {
      setSessionPromptMode("create");
      setSessionPromptTargetId(nextSessionId);
      return;
    }
    clearSessionPrompt();
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
    setActiveWorkContexts(Array.isArray(structured.active_work_context) ? structured.active_work_context : []);
    setPendingNancyCompose(structured.pending_nancy_email_compose);
    setPendingBreakRoomJoke(structured.pending_break_room_joke);
    setPendingRoomNavigation(structured.pending_room_navigation);
    setPendingSessionList(structured.pending_session_list);
    setPendingWorkspaceSwitch(structured.pending_workspace_switch);
    syncPendingSessionPrompt(chosenSessionId, structured);
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
      setActiveWorkContexts(Array.isArray(workspaceState.workspace_state?.active_work_context) ? workspaceState.workspace_state.active_work_context : []);
      setPendingNancyCompose(workspaceState.workspace_state?.pending_nancy_email_compose);
      setPendingBreakRoomJoke(workspaceState.workspace_state?.pending_break_room_joke);
      setPendingRoomNavigation(workspaceState.workspace_state?.pending_room_navigation);
      setPendingSessionList(workspaceState.workspace_state?.pending_session_list);
      setPendingWorkspaceSwitch(workspaceState.workspace_state?.pending_workspace_switch);
      syncPendingSessionPrompt(nextSessionId, workspaceState.workspace_state);
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
      const workspaceState = activated as { workspace_state?: LobbyState };
      setActiveWorkContexts(Array.isArray(workspaceState.workspace_state?.active_work_context) ? workspaceState.workspace_state.active_work_context : []);
      setPendingNancyCompose(workspaceState.workspace_state?.pending_nancy_email_compose);
      setPendingBreakRoomJoke(workspaceState.workspace_state?.pending_break_room_joke);
      setPendingRoomNavigation(workspaceState.workspace_state?.pending_room_navigation);
      setPendingSessionList(workspaceState.workspace_state?.pending_session_list);
      setPendingWorkspaceSwitch(workspaceState.workspace_state?.pending_workspace_switch);
      syncPendingSessionPrompt(nextSessionId, workspaceState.workspace_state);
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
          activeWorkspaceLabel || workspaceLabelById(workspaces, targetWorkspaceId) || targetWorkspaceId,
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
      const structured = response.structuredContent as { workspace_id?: string; session_id?: string; workspace_state?: LobbyState; archived_workspace?: { label?: string }; switched_workspace?: boolean } | undefined;
      const nextWorkspaceId = String(structured?.workspace_id || response.workspace_id || workspaceId);
      const nextSessionId = String(structured?.session_id || response.session_id || sessionId);
      const nextRoomPersona = roomPersonaValues(structured?.workspace_state);
      setActiveWorkContexts(Array.isArray(structured?.workspace_state?.active_work_context) ? structured.workspace_state.active_work_context : []);
      setPendingNancyCompose(structured?.workspace_state?.pending_nancy_email_compose);
      setPendingBreakRoomJoke(structured?.workspace_state?.pending_break_room_joke);
      setPendingRoomNavigation(structured?.workspace_state?.pending_room_navigation);
      setPendingSessionList(structured?.workspace_state?.pending_session_list);
      setPendingWorkspaceSwitch(structured?.workspace_state?.pending_workspace_switch);
      syncPendingSessionPrompt(nextSessionId, structured?.workspace_state);
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
      const workspaceState = response as { workspace_state?: LobbyState };
      setActiveWorkContexts(Array.isArray(workspaceState.workspace_state?.active_work_context) ? workspaceState.workspace_state.active_work_context : []);
      setPendingNancyCompose(workspaceState.workspace_state?.pending_nancy_email_compose);
      setPendingBreakRoomJoke(workspaceState.workspace_state?.pending_break_room_joke);
      setPendingRoomNavigation(workspaceState.workspace_state?.pending_room_navigation);
      setPendingSessionList(workspaceState.workspace_state?.pending_session_list);
      setPendingWorkspaceSwitch(workspaceState.workspace_state?.pending_workspace_switch);
      syncPendingSessionPrompt(nextSessionId, workspaceState.workspace_state);
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
      const structured = response.structuredContent as
        | {
            session_id?: string;
            workspace_id?: string;
            deleted_session_id?: string;
            created_replacement_session?: boolean;
            active_session?: { active_room?: string; active_persona?: string; title?: string; description?: string };
            workspace_state?: LobbyState;
          }
        | undefined;
      const nextSessionId = String(structured?.session_id || response.session_id || sessionId);
      const nextWorkspaceId = String(structured?.workspace_id || response.workspace_id || workspaceId);
      const activeRoomPersona = deleteSessionRoomPersona(structured, activeRoom, activePersona);
      setActiveWorkContexts(Array.isArray(structured?.workspace_state?.active_work_context) ? structured.workspace_state.active_work_context : []);
      setPendingNancyCompose(structured?.workspace_state?.pending_nancy_email_compose);
      setPendingBreakRoomJoke(structured?.workspace_state?.pending_break_room_joke);
      setPendingRoomNavigation(structured?.workspace_state?.pending_room_navigation);
      setPendingSessionList(structured?.workspace_state?.pending_session_list);
      setPendingWorkspaceSwitch(structured?.workspace_state?.pending_workspace_switch);
      syncPendingSessionPrompt(nextSessionId, structured?.workspace_state);
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
        setSessionPromptMode("create");
        setSessionPromptTargetId(nextSessionId);
        applySessionDraft(structured?.active_session, "New Session", "Fresh session.");
      } else {
        clearSessionPrompt();
      }

      const notice = deleteSessionNotice(targetTitle, deletedWasCurrent, replacementTitle);
      showSessionActionNotice(notice, { banner: true });

      appendMessage(
        {
          id: crypto.randomUUID(),
          role: "system",
          speaker: "System",
          text: notice,
          room: activeRoomPersona.room || activeRoom,
          sessionId: nextSessionId || sessionId,
        },
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

  return {
    activeWorkspaceLabel,
    applySessionWorkspace,
    currentUser,
    deletingSessionId,
    deletingWorkspaceId,
    handleCancelSessionNamePrompt,
    handleCreateSession,
    handleCreateWorkspace,
    handleDeleteSession,
    handleDeleteWorkspace,
    handleSaveSessionNamePrompt,
    handleSaveWorkspaceMetadata,
    handleSessionSelect,
    handleWorkspaceSelect,
    hiddenSessionIds,
    loadWorkspaceSelection,
    newWorkspaceTitleDraft,
    refreshCurrentThread,
    refreshSessions,
    refreshWorkspaceSessionLists,
    refreshWorkspaces,
    sessionActionNotice,
    sessionDescriptionDraft,
    sessionPromptMode,
    sessionPromptTargetId,
    sessionTitleDraft,
    setHiddenSessionIds,
    setNewWorkspaceTitleDraft,
    setSessionDescriptionDraft,
    setSessionPromptMode,
    setSessionPromptTargetId,
    setSessionTitleDraft,
    setWorkspaceDescriptionDraft,
    setWorkspaceSelectionId,
    setWorkspaceTitleDraft,
    sessions,
    sessionsLoading,
    workspaceDescriptionDraft,
    workspaceSelectionArtifacts,
    workspaceSelectionFiles,
    workspaceSelectionId,
    workspaceSelectionLoading,
    workspaceSelectionSessions,
    workspaceTitleDraft,
    workspaces,
    workspacesLoading,
  };
}
