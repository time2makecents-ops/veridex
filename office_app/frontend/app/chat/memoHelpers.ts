import { ROOMS, type RoomInfo } from "@/lib/rooms";

export type MemoDispatchForm = {
  toRoom: string;
  subject: string;
  body: string;
  sessionId?: string;
};

export function memoFromLabel(activeRoom: string, activePersona: string): string {
  const room = ROOMS.find((item) => item.id === activeRoom);
  const roomTitle = room?.title || activeRoom || "Current room";
  const persona = activePersona || room?.persona || "Current persona";
  return `${roomTitle} - ${persona}`;
}

export function memoRoomOptions(activeRoom: string): RoomInfo[] {
  return ROOMS.filter((room) => room.id !== activeRoom && room.id !== "break_room");
}

export function buildMemoDispatchArgs(form: MemoDispatchForm): Record<string, unknown> {
  const args: Record<string, unknown> = {
    to_room: form.toRoom,
    body: form.body.trim(),
  };
  const subject = form.subject.trim();
  if (subject) {
    args.subject = subject;
  }
  if (form.sessionId) {
    args.session_id = form.sessionId;
  }
  return args;
}
