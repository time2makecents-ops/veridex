import { useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { callTool, loadTranscript, type TranscriptEntry } from "@/lib/api";

import { backendDisconnectedMessage, lobbyOrientationText, mapTranscriptEntries, roomById, roomStatusText } from "./helpers";
import { DEFAULT_PERSONA, DEFAULT_ROOM_ID, type ChatScope, type Message, type RoomCapabilityProfile } from "./types";

type UseChatRoomStateArgs = {
  sessionId: string;
  setBackendBanner: (message: string) => void;
  setChatScope: (scope: ChatScope) => void;
  setError: (message: string) => void;
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
  setChatScope,
  setError,
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
      const structured = response.structuredContent as { active_room?: string; active_persona?: string } | undefined;
      const nextRoom = String(structured?.active_room || roomId);
      const nextPersona = String(structured?.active_persona || roomById(nextRoom)?.persona || DEFAULT_PERSONA);
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
