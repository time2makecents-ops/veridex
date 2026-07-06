import { useCallback, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { useRouter } from "next/navigation";

import { callTool, request, requestText, type WorkspaceRecord } from "@/lib/api";
import { clearStoredSessionId } from "@/lib/session";

import {
  assistantMessageForResponse,
  contactEmailRequest,
  createMessage,
  providerBadgeForResponse,
  roomPersonaValues,
  speakerForStructuredResponse,
  workContextCompleteArgs,
  workspaceLabelById,
} from "./helpers";
import { buildNancyModeRequest, effectiveNancyMode } from "./shortcutHelpers";
import {
  type ChatStructuredResponse,
  type ContactRecord,
  type GmailMessageSummary,
  type Message,
  type NancyEmailComposeState,
  type PendingRoomNavigationState,
  type PendingWorkspaceSwitchState,
  type ProviderBadge,
  type SessionPromptMode,
} from "./types";

type UseChatComposerActionsArgs = {
  activePersona: string;
  activeRoom: string;
  appendMessage: (message: Message) => void;
  appendRoomTransition: (roomId: string, persona: string) => void;
  applyActiveRoom: (room: string, persona: string) => void;
  applySessionWorkspace: (nextSessionId: string, nextWorkspaceId: string, workspaceLabel: string, options?: { persistSession?: boolean; forceRoomScope?: boolean }) => void;
  draft: string;
  draftRef: RefObject<HTMLTextAreaElement | null>;
  loading: boolean;
  nancyMode: boolean;
  onWorkContextChanged: () => void;
  refreshCurrentThread: (nextSessionId?: string) => Promise<void>;
  refreshSessions: (activeSessionId?: string) => Promise<void>;
  refreshWorkspaces: (activeWorkspaceId?: string) => Promise<WorkspaceRecord[]>;
  sessionId: string;
  setConfirmedIntegrationIds: (updater: (current: string[]) => string[]) => void;
  setConfirmingIntegrationId: (value: string) => void;
  setCompletedWorkContextIds: (updater: (current: string[]) => string[]) => void;
  setCompletingWorkContextId: (value: string) => void;
  setDraft: (value: string) => void;
  setError: (message: string) => void;
  setLoading: (value: boolean) => void;
  setPendingNancyCompose: (compose: NancyEmailComposeState | undefined) => void;
  setPendingBreakRoomJoke: (pending: ChatStructuredResponse["pending_break_room_joke"] | undefined) => void;
  setPendingRoomNavigation: (pending: PendingRoomNavigationState | undefined) => void;
  setPendingSessionList: (pending: ChatStructuredResponse["pending_session_list"] | undefined) => void;
  setPendingWorkspaceSwitch: (pending: PendingWorkspaceSwitchState | undefined) => void;
  setProviderBadge: (badge: ProviderBadge | null) => void;
  setSessionPromptMode: (mode: SessionPromptMode) => void;
  setSessionPromptTargetId: (value: string) => void;
  workspaces: WorkspaceRecord[];
};

export function useChatComposerActions({
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
  onWorkContextChanged,
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
}: UseChatComposerActionsArgs) {
  const router = useRouter();

  const sendText = useCallback(
    async (text: string) => {
      const value = text.trim();
      if (!value || loading) {
        return;
      }
      const outgoingSessionId = sessionId;
      setDraft("");
      setError("");
      setLoading(true);
      appendMessage(createMessage({ role: "user", text: value, room: activeRoom, sessionId: outgoingSessionId }));
      try {
        const routeToNancy = effectiveNancyMode(activeRoom, nancyMode);
        const routedValue = routeToNancy ? buildNancyModeRequest(value) : value;
        const response = await request(routedValue, outgoingSessionId);
        const assistantText = requestText(response);
        const structuredResponse = response.structuredContent as ChatStructuredResponse | undefined;
        const nextWorkspaceId = String(response.workspace_id || structuredResponse?.workspace_id || "");
        const nextSessionId = String(response.session_id || structuredResponse?.session_id || outgoingSessionId);
        const nextRoomPersona = routeToNancy ? { room: activeRoom, persona: activePersona } : roomPersonaValues(structuredResponse, activeRoom, activePersona);
        const nextRoom = nextRoomPersona.room;
        const nextPersona = nextRoomPersona.persona;
        const nextSpeaker = speakerForStructuredResponse(structuredResponse, nextPersona);
        const nextProviderBadge = providerBadgeForResponse(structuredResponse);
        if (nextProviderBadge) {
          setProviderBadge(nextProviderBadge);
        }
        if (structuredResponse?.clear_pending_nancy_email) {
          setPendingNancyCompose(undefined);
        } else if (structuredResponse?.nancy_email_compose) {
          setPendingNancyCompose(structuredResponse.nancy_email_compose);
        }
        if (structuredResponse?.clear_pending_break_room_joke) {
          setPendingBreakRoomJoke(undefined);
        } else if (structuredResponse?.pending_break_room_joke) {
          setPendingBreakRoomJoke(structuredResponse.pending_break_room_joke);
        }
        if (structuredResponse?.clear_pending_room_navigation || (structuredResponse?.active_room && structuredResponse?.routing?.capability === "room.navigate")) {
          setPendingRoomNavigation(undefined);
        } else if (structuredResponse?.pending_room_navigation) {
          setPendingRoomNavigation(structuredResponse.pending_room_navigation);
        }
        if (structuredResponse?.clear_pending_session_list || structuredResponse?.routing?.capability === "session.list") {
          setPendingSessionList(undefined);
        } else if (structuredResponse?.pending_session_list) {
          setPendingSessionList(structuredResponse.pending_session_list);
        }
        if (structuredResponse?.clear_pending_workspace_switch) {
          setPendingWorkspaceSwitch(undefined);
        } else if (structuredResponse?.pending_workspace_switch) {
          setPendingWorkspaceSwitch(structuredResponse.pending_workspace_switch);
        }
        if (structuredResponse?.clear_pending_session_prompt) {
          setSessionPromptMode("create");
          setSessionPromptTargetId("");
        } else if (structuredResponse?.pending_session_rename) {
          setSessionPromptMode("rename");
          setSessionPromptTargetId(nextSessionId || outgoingSessionId);
        }
        if (nextSessionId && nextSessionId !== outgoingSessionId) {
          applySessionWorkspace(nextSessionId, nextWorkspaceId, workspaceLabelById(workspaces, nextWorkspaceId), {
            persistSession: true,
            forceRoomScope: true,
          });
          await refreshCurrentThread(nextSessionId);
          await refreshWorkspaces(nextWorkspaceId);
          await refreshSessions(nextSessionId);
          onWorkContextChanged();
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
        onWorkContextChanged();
      } catch (err) {
        const message = err instanceof Error ? err.message : "Request failed.";
        setError(message);
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
    },
    [
      activePersona,
      activeRoom,
      appendMessage,
      appendRoomTransition,
      applyActiveRoom,
      applySessionWorkspace,
      draftRef,
      loading,
      nancyMode,
      onWorkContextChanged,
      refreshCurrentThread,
      refreshSessions,
      refreshWorkspaces,
      router,
      sessionId,
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
    ],
  );

  const confirmIntegrationAction = useCallback(
    async (confirmationId: string, room: string, targetSessionId: string, assistantPersona?: string) => {
      if (!confirmationId) {
        return;
      }
      setConfirmingIntegrationId(confirmationId);
      setError("");
      try {
        const response = await callTool("office.integration_confirm", {
          confirmation_id: confirmationId,
          session_id: targetSessionId,
          ...(assistantPersona ? { assistant_persona: assistantPersona } : {}),
        });
        setConfirmedIntegrationIds((current) => [...current, confirmationId]);
        setPendingNancyCompose(undefined);
        appendMessage(
          createMessage({
            role: "assistant",
            speaker: "Nancy",
            text: requestText(response),
            room,
            sessionId: targetSessionId,
          }),
        );
        onWorkContextChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to confirm the external action.");
      } finally {
        setConfirmingIntegrationId("");
      }
    },
    [appendMessage, onWorkContextChanged, setConfirmedIntegrationIds, setConfirmingIntegrationId, setError, setPendingNancyCompose],
  );

  const cancelIntegrationAction = useCallback(
    async (confirmationId: string, room: string, targetSessionId: string, assistantPersona?: string) => {
      if (!confirmationId) {
        return;
      }
      setConfirmingIntegrationId(confirmationId);
      setError("");
      try {
        const response = await callTool("office.integration_cancel", {
          confirmation_id: confirmationId,
          session_id: targetSessionId,
          ...(assistantPersona ? { assistant_persona: assistantPersona } : {}),
        });
        const structuredResponse = response.structuredContent as ChatStructuredResponse | undefined;
        if (structuredResponse?.clear_pending_nancy_email) {
          setPendingNancyCompose(undefined);
        }
        appendMessage(
          createMessage({
            role: "assistant",
            speaker: "Nancy",
            text: requestText(response),
            room,
            sessionId: targetSessionId,
          }),
        );
        onWorkContextChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to dismiss the external action.");
      } finally {
        setConfirmingIntegrationId("");
      }
    },
    [appendMessage, onWorkContextChanged, setConfirmingIntegrationId, setError, setPendingNancyCompose],
  );

  const openGmailThread = useCallback(
    async (message: GmailMessageSummary, room: string, targetSessionId: string) => {
      const threadId = String(message.threadId || "").trim();
      const messageId = String(message.id || "").trim();
      if (!threadId && !messageId) {
        return;
      }
      setError("");
      try {
        const response = await callTool(threadId ? "office.gmail_thread_read" : "office.gmail_read", {
          thread_id: threadId,
          message_id: messageId,
          session_id: targetSessionId,
        });
        const structuredResponse = response.structuredContent as ChatStructuredResponse | undefined;
        appendMessage(assistantMessageForResponse(structuredResponse, requestText(response), "Nancy", room, targetSessionId));
        onWorkContextChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load Gmail thread.");
      }
    },
    [appendMessage, onWorkContextChanged, setError],
  );

  const startEmailToContact = useCallback(
    async (contact: ContactRecord, room: string, targetSessionId: string) => {
      const requestValue = contactEmailRequest(contact);
      if (!String(contact.email || "").trim()) {
        return;
      }
      setError("");
      try {
        const response = await request(requestValue, targetSessionId);
        const structuredResponse = response.structuredContent as ChatStructuredResponse | undefined;
        if (structuredResponse?.clear_pending_nancy_email) {
          setPendingNancyCompose(undefined);
        } else if (structuredResponse?.nancy_email_compose) {
          setPendingNancyCompose(structuredResponse.nancy_email_compose);
        }
        if (structuredResponse?.clear_pending_break_room_joke) {
          setPendingBreakRoomJoke(undefined);
        } else if (structuredResponse?.pending_break_room_joke) {
          setPendingBreakRoomJoke(structuredResponse.pending_break_room_joke);
        }
        if (structuredResponse?.clear_pending_room_navigation || (structuredResponse?.active_room && structuredResponse?.routing?.capability === "room.navigate")) {
          setPendingRoomNavigation(undefined);
        } else if (structuredResponse?.pending_room_navigation) {
          setPendingRoomNavigation(structuredResponse.pending_room_navigation);
        }
        if (structuredResponse?.clear_pending_session_list || structuredResponse?.routing?.capability === "session.list") {
          setPendingSessionList(undefined);
        } else if (structuredResponse?.pending_session_list) {
          setPendingSessionList(structuredResponse.pending_session_list);
        }
        if (structuredResponse?.clear_pending_workspace_switch) {
          setPendingWorkspaceSwitch(undefined);
        } else if (structuredResponse?.pending_workspace_switch) {
          setPendingWorkspaceSwitch(structuredResponse.pending_workspace_switch);
        }
        if (structuredResponse?.clear_pending_session_prompt) {
          setSessionPromptMode("create");
          setSessionPromptTargetId("");
        } else if (structuredResponse?.pending_session_rename) {
          setSessionPromptMode("rename");
          setSessionPromptTargetId(targetSessionId);
        }
        appendMessage(assistantMessageForResponse(structuredResponse, requestText(response), "Nancy", room, targetSessionId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to start Nancy email compose.");
      }
    },
    [appendMessage, setError, setPendingNancyCompose, setPendingBreakRoomJoke, setPendingRoomNavigation, setPendingSessionList, setPendingWorkspaceSwitch, setSessionPromptMode, setSessionPromptTargetId],
  );

  const completeWorkContext = useCallback(
    async (contextId: string, activeIndex: number, room: string, targetSessionId: string) => {
      if (!String(contextId || "").trim() && activeIndex < 1) {
        return;
      }
      const trimmedContextId = String(contextId || "").trim();
      if (trimmedContextId) {
        setCompletingWorkContextId(trimmedContextId);
      }
      setError("");
      try {
        const response = await callTool("office.work_context_complete", workContextCompleteArgs(contextId, activeIndex, targetSessionId));
        const structuredResponse = response.structuredContent as ChatStructuredResponse | undefined;
        const completedContexts = Array.isArray(structuredResponse?.contexts) ? structuredResponse.contexts : [];
        const completedIds = completedContexts.map((context) => String(context.context_id || "").trim()).filter(Boolean);
        if (completedIds.length) {
          setCompletedWorkContextIds((current) => Array.from(new Set([...current, ...completedIds])));
        }
        appendMessage(assistantMessageForResponse(structuredResponse, requestText(response), "Navigator", room, targetSessionId));
        onWorkContextChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to complete work context.");
      } finally {
        if (trimmedContextId) {
          setCompletingWorkContextId("");
        }
      }
    },
    [appendMessage, onWorkContextChanged, setCompletedWorkContextIds, setCompletingWorkContextId, setError],
  );

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      await sendText(draft);
    },
    [draft, sendText],
  );

  const handleDraftKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
        return;
      }
      event.preventDefault();
      void sendText(draft);
    },
    [draft, sendText],
  );

  return {
    completeWorkContext,
    cancelIntegrationAction,
    confirmIntegrationAction,
    handleDraftKeyDown,
    handleSubmit,
    openGmailThread,
    sendText,
    startEmailToContact,
  };
}
