"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { callTool, listActiveWorkContexts, loadTranscript } from "@/lib/api";
import { clearStoredSessionId, getSessionShortLabel, getStoredSessionId } from "@/lib/session";

import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
import { ChatTranscript } from "./ChatTranscript";
import { ChatToolbar } from "./ChatToolbar";
import { DocumentReader } from "./DocumentReader";
import { AttachmentPanel, LoadFilePanel, SaveFilePanel } from "./FilePanels";
import { MeetingWorkspacePanel } from "./MeetingWorkspacePanel";
import { MemoPanel } from "./MemoPanel";
import {
  backendDisconnectedMessage,
  createMessage,
  roomPersonaValues,
  sessionById,
  visibleMessagesForScope,
  workspaceById,
} from "./helpers";
import { RoomDirectoryPanel } from "./RoomDirectoryPanel";
import { SessionNamePrompt, SessionPanel } from "./SessionPanel";
import { nextNancyMode } from "./shortcutHelpers";
import {
  type ChatScope,
  type LobbyState,
  type Message,
  type NancyEmailComposeState,
  type PendingRoomNavigationState,
  type PendingWorkspaceSwitchState,
  type ProviderBadge,
  type WorkContextRecord,
} from "./types";
import { useChatFiles } from "./useChatFiles";
import { useChatMenus } from "./useChatMenus";
import { useChatRoomState } from "./useChatRoomState";
import { useChatComposerActions } from "./useChatComposerActions";
import { useChatWorkspaceSession } from "./useChatWorkspaceSession";
import { WorkspacePanel } from "./WorkspacePanel";

export default function ChatPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [backendBanner, setBackendBanner] = useState("");
  const [providerBadge, setProviderBadge] = useState<ProviderBadge | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatScope, setChatScope] = useState<ChatScope>("room");
  const [nancyMode, setNancyMode] = useState(false);
  const [confirmingIntegrationId, setConfirmingIntegrationId] = useState("");
  const [confirmedIntegrationIds, setConfirmedIntegrationIds] = useState<string[]>([]);
  const [completingWorkContextId, setCompletingWorkContextId] = useState("");
  const [completedWorkContextIds, setCompletedWorkContextIds] = useState<string[]>([]);
  const [activeWorkContexts, setActiveWorkContexts] = useState<WorkContextRecord[]>([]);
  const [pendingNancyCompose, setPendingNancyCompose] = useState<NancyEmailComposeState | undefined>(undefined);
  const [pendingBreakRoomJoke, setPendingBreakRoomJoke] = useState<LobbyState["pending_break_room_joke"] | undefined>(undefined);
  const [pendingRoomNavigation, setPendingRoomNavigation] = useState<PendingRoomNavigationState | undefined>(undefined);
  const [pendingSessionList, setPendingSessionList] = useState<LobbyState["pending_session_list"] | undefined>(undefined);
  const [pendingWorkspaceSwitch, setPendingWorkspaceSwitch] = useState<PendingWorkspaceSwitchState | undefined>(undefined);
  const logRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  const {
    attachmentMode,
    attachmentOpen,
    loadMenuOpen,
    meetingMenuOpen,
    memoMenuOpen,
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
    toggleMeetingMenu,
    toggleMemoMenu,
    toggleRoomMenu,
    toggleSaveMenu,
    toggleSessionMenu,
    toggleWorkspaceMenu,
  } = useChatMenus();

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
    setActiveWorkContexts,
    setChatScope,
    setError,
    setPendingNancyCompose,
    setPendingBreakRoomJoke,
    setPendingRoomNavigation,
    setPendingSessionList,
    setPendingWorkspaceSwitch,
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

  const {
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
    loadWorkspaceSelection,
    newWorkspaceTitleDraft,
    refreshCurrentThread,
    refreshSessions,
    refreshWorkspaces,
    sessionActionNotice,
    sessionDescriptionDraft,
    sessionPromptMode,
    sessionPromptTargetId,
    sessionTitleDraft,
    setNewWorkspaceTitleDraft,
    setSessionDescriptionDraft,
    setSessionPromptMode,
    setSessionPromptTargetId,
    setSessionTitleDraft,
    setWorkspaceDescriptionDraft,
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
  } = useChatWorkspaceSession({
    activePersona,
    activeRoom,
    appendMessage,
    applyActiveRoom,
    applyHydratedMessages,
    refreshFiles,
    sessionId,
    setBackendBanner,
    setActiveWorkContexts,
    setChatScope,
    setError,
    setPendingNancyCompose,
    setPendingBreakRoomJoke,
    setPendingRoomNavigation,
    setPendingSessionList,
    setPendingWorkspaceSwitch,
    setRoomMenuOpen,
    setSessionId,
    setSessionMenuOpen,
    setWorkspaceId,
    setWorkspaceMenuOpen,
    workspaceId,
  });

  const refreshActiveWorkContexts = useCallback(async () => {
    if (!sessionId) {
      setActiveWorkContexts([]);
      return;
    }
    try {
      const rows = await listActiveWorkContexts(8, sessionId);
      setActiveWorkContexts(rows);
    } catch {
      setActiveWorkContexts([]);
    }
  }, [sessionId]);

  const { cancelIntegrationAction, completeWorkContext, confirmIntegrationAction, handleDraftKeyDown, handleSubmit, openGmailThread, sendText, startEmailToContact } = useChatComposerActions({
    activePersona,
    activeRoom,
    appendMessage,
    appendRoomTransition,
    applyActiveRoom,
    applySessionWorkspace,
    draft,
    draftRef,
    loading,
    nancyMode,
    onWorkContextChanged: () => {
      void refreshActiveWorkContexts();
    },
    refreshCurrentThread,
    refreshSessions,
    refreshWorkspaces,
    sessionId,
    setConfirmedIntegrationIds,
    setConfirmingIntegrationId,
    setCompletedWorkContextIds,
    setCompletingWorkContextId,
    setDraft,
    setError,
    setLoading,
    setPendingNancyCompose,
    setPendingBreakRoomJoke,
    setPendingRoomNavigation,
    setPendingSessionList,
    setPendingWorkspaceSwitch,
    setProviderBadge,
    setSessionPromptMode,
    setSessionPromptTargetId,
    workspaces,
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
          callTool("office.state_get", { session_id: sessionId }),
          loadTranscript(120, sessionId),
        ]);
        const structured = stateResponse.structuredContent as LobbyState | undefined;
        if (cancelled || !structured) {
          return;
        }
        const nextWorkspace = String(structured.workspace_id || "");
        const nextRoomPersona = roomPersonaValues(structured);
        setWorkspaceId(nextWorkspace);
        setActiveWorkContexts(Array.isArray(structured.active_work_context) ? structured.active_work_context : []);
        setPendingNancyCompose(structured.pending_nancy_email_compose);
        setPendingBreakRoomJoke(structured.pending_break_room_joke);
        setPendingRoomNavigation(structured.pending_room_navigation);
        setPendingSessionList(structured.pending_session_list);
        setPendingWorkspaceSwitch(structured.pending_workspace_switch);
        if (structured.pending_session_rename) {
          setSessionPromptMode("rename");
          setSessionPromptTargetId(sessionId);
        } else if (structured.pending_session_create) {
          setSessionPromptMode("create");
          setSessionPromptTargetId(sessionId);
        } else {
          setSessionPromptMode("create");
          setSessionPromptTargetId("");
        }
        applyActiveRoom(nextRoomPersona.room, nextRoomPersona.persona);
        applyHydratedMessages(nextRoomPersona.room, nextRoomPersona.persona, transcriptEntries, sessionId);
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

  useEffect(() => {
    void refreshActiveWorkContexts();
  }, [activeRoom, refreshActiveWorkContexts, workspaceId]);

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
  const visibleActiveWorkContexts = useMemo(
    () => activeWorkContexts.filter((context) => !completedWorkContextIds.includes(String(context.context_id || ""))),
    [activeWorkContexts, completedWorkContextIds],
  );

  function appendMessage(message: Message) {
    setMessages((current) => [...current, message]);
  }

  function toggleNancyMode() {
    setNancyMode((current) => nextNancyMode(activeRoom, current));
  }

  async function handleCreateWorkspaceAndFocus() {
    await handleCreateWorkspace();
  }

  return (
    <main className="screen lobby-page lobby-page-plain" data-session={sessionLabel} data-workspace={workspaceId} data-room={activeRoom} data-persona={activePersona}>
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
              onCreateWorkspace={() => void handleCreateWorkspaceAndFocus()}
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
            meetingMenuOpen={meetingMenuOpen}
            nancyMode={nancyMode}
            recentRooms={recentRooms}
            roomMenuOpen={roomMenuOpen}
            saveMenuOpen={saveMenuOpen}
            sessionMenuOpen={sessionMenuOpen}
            onLoadMenuToggle={toggleLoadMenu}
            onMeetingMenuToggle={toggleMeetingMenu}
            onNancyToggle={toggleNancyMode}
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
            sessionPromptMode={sessionPromptMode}
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
          {meetingMenuOpen && activeRoom === "conference_room" ? (
            <MeetingWorkspacePanel
              sessionId={sessionId}
              workspaceId={workspaceId}
              onArtifactSaved={() => {
                if (workspaceSelectionId === workspaceId) {
                  void loadWorkspaceSelection(workspaceId);
                }
              }}
            />
          ) : null}
          {memoMenuOpen ? <MemoPanel activePersona={activePersona} activeRoom={activeRoom} sessionId={sessionId} /> : null}
        </div>
      </section>

      <section className="card lobby-chat-card">
        <ChatTranscript
          activePersona={activePersona}
          activeRoom={activeRoom}
          activeWorkContexts={visibleActiveWorkContexts}
          backendBanner={backendBanner}
          chatScope={chatScope}
          completedWorkContextIds={completedWorkContextIds}
          completingWorkContextId={completingWorkContextId}
          confirmedIntegrationIds={confirmedIntegrationIds}
          confirmingIntegrationId={confirmingIntegrationId}
          error={error}
          loading={loading}
          logRef={logRef}
          messages={visibleMessages}
          nancyMode={nancyMode}
          pendingNancyCompose={pendingNancyCompose}
          pendingBreakRoomJoke={pendingBreakRoomJoke}
          pendingRoomNavigation={pendingRoomNavigation}
          pendingSessionList={pendingSessionList}
          pendingWorkspaceSwitch={pendingWorkspaceSwitch}
          roomStatus={roomStatus}
          sessionId={sessionId}
          onChatScopeChange={setChatScope}
          onConfirmIntegration={(confirmationId, room, targetSessionId, assistantPersona) => void confirmIntegrationAction(confirmationId, room, targetSessionId, assistantPersona)}
          onCancelIntegration={(confirmationId, room, targetSessionId, assistantPersona) => void cancelIntegrationAction(confirmationId, room, targetSessionId, assistantPersona)}
          onEmailContact={(contact, room, targetSessionId) => void startEmailToContact(contact, room, targetSessionId)}
          onEnableNancyMode={() => setNancyMode(true)}
          onRevealBreakRoomPunchline={() => void sendText("punchline")}
          onDismissBreakRoomJoke={() => void sendText("cancel")}
          onKeepCurrentRoom={() => void sendText("no")}
          onKeepSessionListPending={() => void sendText("no")}
          onKeepCurrentWorkspace={() => void sendText("no")}
          onOpenGmailThread={(message, room, targetSessionId) => void openGmailThread(message, room, targetSessionId)}
          onCompleteWorkContext={(contextId, activeIndex, room, targetSessionId) => void completeWorkContext(contextId, activeIndex, room, targetSessionId)}
          onSwitchRoomNow={() => void sendText("yes")}
          onShowSessionListNow={() => void sendText("yes")}
          onSwitchWorkspaceNow={() => void sendText("yes")}
        />
        <ChatComposer
          activePersona={activePersona}
          activeRoom={activeRoom}
          draft={draft}
          draftRef={draftRef}
          loading={loading}
          memoMenuOpen={memoMenuOpen}
          nancyMode={nancyMode}
          onDraftChange={setDraft}
          onFileActionsToggle={() => {
            toggleAttachmentPanel();
          }}
          onKeyDown={handleDraftKeyDown}
          onMemoToggle={toggleMemoMenu}
          onNancyToggle={toggleNancyMode}
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
