"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { callTool, loadTranscript } from "@/lib/api";
import { clearStoredSessionId, getSessionShortLabel, getStoredSessionId } from "@/lib/session";

import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
import { ChatTranscript } from "./ChatTranscript";
import { ChatToolbar } from "./ChatToolbar";
import { DocumentReader } from "./DocumentReader";
import { AttachmentPanel, LoadFilePanel, SaveFilePanel } from "./FilePanels";
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
import {
  type ChatScope,
  type LobbyState,
  type Message,
  type ProviderBadge,
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
  const [confirmingIntegrationId, setConfirmingIntegrationId] = useState("");
  const [confirmedIntegrationIds, setConfirmedIntegrationIds] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

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
    sessionPromptTargetId,
    sessionTitleDraft,
    setNewWorkspaceTitleDraft,
    setSessionDescriptionDraft,
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
    setChatScope,
    setError,
    setRoomMenuOpen,
    setSessionId,
    setSessionMenuOpen,
    setWorkspaceId,
    setWorkspaceMenuOpen,
    workspaceId,
  });

  const { confirmIntegrationAction, handleDraftKeyDown, handleSubmit } = useChatComposerActions({
    activePersona,
    activeRoom,
    appendMessage,
    appendRoomTransition,
    applyActiveRoom,
    applySessionWorkspace,
    draft,
    draftRef,
    loading,
    refreshCurrentThread,
    refreshSessions,
    refreshWorkspaces,
    sessionId,
    setConfirmedIntegrationIds,
    setConfirmingIntegrationId,
    setDraft,
    setError,
    setLoading,
    setProviderBadge,
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

  function appendMessage(message: Message) {
    setMessages((current) => [...current, message]);
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
