export type MeetingSectionKey = "agenda" | "decisions" | "action_items" | "parking_lot";

export type MeetingState = {
  meeting_id: string;
  room_id: string;
  title: string;
  agenda: string[];
  decisions: string[];
  action_items: string[];
  parking_lot: string[];
  created_utc: string;
  updated_utc: string;
};

export const MEETING_SECTION_CONFIG: Array<{ key: MeetingSectionKey; label: string; addTool: string }> = [
  { key: "agenda", label: "Agenda", addTool: "office.meeting_state_add_agenda" },
  { key: "decisions", label: "Decisions", addTool: "office.meeting_state_record_decision" },
  { key: "action_items", label: "Action Items", addTool: "office.meeting_state_add_action_item" },
  { key: "parking_lot", label: "Parking Lot", addTool: "office.meeting_state_add_parking_lot" },
];

function textList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];
}

export function shouldShowMeetingWorkspace(activeRoom: string): boolean {
  return activeRoom === "conference_room";
}

export function meetingStateFromStructuredContent(value: unknown): MeetingState | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const structured = value as Record<string, unknown>;
  if (structured.needs_meeting) {
    return null;
  }
  const meetingId = String(structured.meeting_id || "").trim();
  if (!meetingId) {
    return null;
  }
  return {
    meeting_id: meetingId,
    room_id: String(structured.room_id || "conference_room"),
    title: String(structured.title || ""),
    agenda: textList(structured.agenda),
    decisions: textList(structured.decisions),
    action_items: textList(structured.action_items),
    parking_lot: textList(structured.parking_lot),
    created_utc: String(structured.created_utc || ""),
    updated_utc: String(structured.updated_utc || ""),
  };
}

export function meetingBriefArtifactId(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }
  const structured = value as { artifact?: { artifact_id?: unknown } };
  return String(structured.artifact?.artifact_id || "").trim();
}
