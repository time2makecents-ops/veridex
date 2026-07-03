import { useCallback, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { useRouter } from "next/navigation";

import { callTool, request, requestText, type WorkspaceRecord } from "@/lib/api";
import { clearStoredSessionId } from "@/lib/session";

import {
  assistantMessageForResponse,
  createMessage,
  providerBadgeForResponse,
  roomPersonaValues,
  speakerForStructuredResponse,
  workspaceLabelById,
} from "./helpers";
import { buildNancyModeRequest, effectiveNancyMode } from "./shortcutHelpers";
import { type ChatStructuredResponse, type GmailMessageSummary, type Message, type ProviderBadge } from "./types";

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
  refreshCurrentThread: (nextSessionId?: string) => Promise<void>;
  refreshSessions: (activeSessionId?: string) => Promise<void>;
  refreshWorkspaces: (activeWorkspaceId?: string) => Promise<WorkspaceRecord[]>;
  sessionId: string;
  setConfirmedIntegrationIds: (updater: (current: string[]) => string[]) => void;
  setConfirmingIntegrationId: (value: string) => void;
  setDraft: (value: string) => void;
  setError: (message: string) => void;
  setLoading: (value: boolean) => void;
  setProviderBadge: (badge: ProviderBadge | null) => void;
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
      refreshCurrentThread,
      refreshSessions,
      refreshWorkspaces,
      router,
      sessionId,
      setDraft,
      setError,
      setLoading,
      setProviderBadge,
      workspaces,
    ],
  );

  const confirmIntegrationAction = useCallback(
    async (confirmationId: string, room: string, targetSessionId: string) => {
      if (!confirmationId) {
        return;
      }
      setConfirmingIntegrationId(confirmationId);
      setError("");
      try {
        const response = await callTool("office.integration_confirm", { confirmation_id: confirmationId, session_id: targetSessionId });
        setConfirmedIntegrationIds((current) => [...current, confirmationId]);
        appendMessage(
          createMessage({
            role: "assistant",
            speaker: "Nancy",
            text: requestText(response),
            room,
            sessionId: targetSessionId,
          }),
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to confirm the external action.");
      } finally {
        setConfirmingIntegrationId("");
      }
    },
    [appendMessage, setConfirmedIntegrationIds, setConfirmingIntegrationId, setError],
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
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load Gmail thread.");
      }
    },
    [appendMessage, setError],
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
    confirmIntegrationAction,
    handleDraftKeyDown,
    handleSubmit,
    openGmailThread,
    sendText,
  };
}
