import { useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { callTool, loadTranscript, type TranscriptEntry } from "@/lib/api";

import { backendDisconnectedMessage, lobbyOrientationText, mapTranscriptEntries, roomById, roomStatusText } from "./helpers";
import { DEFAULT_PERSONA, DEFAULT_ROOM_ID, type ChatScope, type LobbyState, type Message, type NancyEmailComposeState, type RoomCapabilityProfile, type WorkContextRecord } from "./types";

type UseChatRoomStateArgs = {
  sessionId: string;
  setBackendBanner: (message: string) => void;
  setActiveWorkContexts: (contexts: WorkContextRecord[]) => void;
  setChatScope: (scope: ChatScope) => void;
  setError: (message: string) => void;
  setPendingNancyCompose: (compose: NancyEmailComposeState | undefined) => void;
  setPendingBreakRoomJoke: (pending: LobbyState["pending_break_room_joke"] | undefined) => void;
  setPendingRoomNavigation: (pending: LobbyState["pending_room_navigation"] | undefined) => void;
  setPendingSessionList: (pending: LobbyState["pending_session_list"] | undefined) => void;
  setPendingWorkspaceSwitch: (pending: LobbyState["pending_workspace_switch"] | undefined) => void;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setRoomMenuOpen: (open: boolean) => void;
};

export function pushRecentRoom(existing: string[], roomId: string): string[] {
  const next = [roomId, ...existing.filter((item) => item !== roomId)];
  return next.slice(0, 3);
}

export function useChatRoomState({
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
}: UseChatRoomStateArgs) {
  const [activeRoom, setActiveRoom] = useState(DEFAULT_ROOM_ID);
  const [activePersona, setActivePersona] = useState(DEFAULT_PERSONA);
  const [switchingRoom, setSwitchingRoom] = useState<string>("");
  const [recentRooms, setRecentRooms] = useState<string[]>([]);
  const [roomStatus, setRoomStatus] = useState("Waiting for room state.");
  const roomStatusRequestRef = useRef(0);
  const currentRoom = useMemo(() => roomById(activeRoom), [activeRoom]);
  const currentTitle = currentRoom?.title || activeRoom;

  async function hydrateRoomStatus(roomId: string, persona: string, targetSessionId?: string) {
    const baseline = roomStatusText(roomId, persona);
    setRoomStatus(baseline);
    const requestId = roomStatusRequestRef.current + 1;
    roomStatusRequestRef.current = requestId;
    const nextSessionId = String(targetSessionId || sessionId || "");
    if (!nextSessionId) {
      return;
    }
    try {
      const response = await callTool("office.room_capabilities", { room_id: roomId, session_id: nextSessionId });
      if (roomStatusRequestRef.current !== requestId) {
        return;
      }
      const structured = response.structuredContent as { profile?: RoomCapabilityProfile } | undefined;
      setRoomStatus(roomStatusText(roomId, persona, structured?.profile));
    } catch {
      if (roomStatusRequestRef.current === requestId) {
        setRoomStatus(baseline);
      }
    }
  }

  function applyActiveRoom(room: string, persona: string) {
    setActiveRoom(room);
    setActivePersona(persona);
    setRecentRooms((current) => pushRecentRoom(current, room));
  }

  function applyHydratedMessages(
    nextRoom: string,
    nextPersona: string,
    transcriptEntries: TranscriptEntry[],
    hydratedSessionId?: string,
  ) {
    void hydrateRoomStatus(nextRoom, nextPersona, hydratedSessionId || sessionId);
    const hydratedMessages = mapTranscriptEntries(transcriptEntries);
    if (hydratedMessages.length) {
      setMessages(hydratedMessages);
    } else {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          speaker: nextPersona,
          text: nextRoom === DEFAULT_ROOM_ID ? lobbyOrientationText(nextPersona) : `${nextPersona} ready.`,
          sessionId: hydratedSessionId || sessionId,
          room: nextRoom,
        },
      ]);
    }
  }

  function appendRoomTransition(roomId: string, persona: string) {
    void hydrateRoomStatus(roomId, persona, sessionId);
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
      const structured = response.structuredContent as {
        active_room?: string;
        active_persona?: string;
        active_work_context?: WorkContextRecord[];
        pending_nancy_email_compose?: NancyEmailComposeState;
        pending_break_room_joke?: LobbyState["pending_break_room_joke"];
        pending_room_navigation?: LobbyState["pending_room_navigation"];
        pending_session_list?: LobbyState["pending_session_list"];
        pending_workspace_switch?: LobbyState["pending_workspace_switch"];
      } | undefined;
      const nextRoom = String(structured?.active_room || roomId);
      const nextPersona = String(structured?.active_persona || roomById(nextRoom)?.persona || DEFAULT_PERSONA);
      setActiveWorkContexts(Array.isArray(structured?.active_work_context) ? structured.active_work_context : []);
      setPendingNancyCompose(structured?.pending_nancy_email_compose);
      setPendingBreakRoomJoke(structured?.pending_break_room_joke);
      setPendingRoomNavigation(structured?.pending_room_navigation);
      setPendingSessionList(structured?.pending_session_list);
      setPendingWorkspaceSwitch(structured?.pending_workspace_switch);
      const transcriptEntries = await loadTranscript(120, sessionId);
      applyActiveRoom(nextRoom, nextPersona);
      setChatScope("room");
      applyHydratedMessages(nextRoom, nextPersona, transcriptEntries, sessionId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to change room.";
      setError(message);
      setBackendBanner(backendDisconnectedMessage(message));
    } finally {
      setSwitchingRoom("");
    }
  }

  return {
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
  };
}
