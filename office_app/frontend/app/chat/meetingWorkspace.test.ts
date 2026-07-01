import { describe, expect, it } from "vitest";

import {
  MEETING_SECTION_CONFIG,
  meetingBriefArtifactId,
  meetingStateFromStructuredContent,
  shouldShowMeetingWorkspace,
} from "./meetingWorkspace";

describe("shouldShowMeetingWorkspace", () => {
  it("only shows the workspace controls in Conference Room", () => {
    expect(shouldShowMeetingWorkspace("conference_room")).toBe(true);
    expect(shouldShowMeetingWorkspace("sales_department")).toBe(false);
    expect(shouldShowMeetingWorkspace("")).toBe(false);
  });
});

describe("MEETING_SECTION_CONFIG", () => {
  it("keeps the editable meeting sections in brief order", () => {
    expect(MEETING_SECTION_CONFIG.map((section) => section.key)).toEqual([
      "agenda",
      "decisions",
      "action_items",
      "parking_lot",
    ]);
    expect(MEETING_SECTION_CONFIG.map((section) => section.label)).toEqual([
      "Agenda",
      "Decisions",
      "Action Items",
      "Parking Lot",
    ]);
  });
});

describe("meetingStateFromStructuredContent", () => {
  it("returns null when the backend says a meeting needs to be started", () => {
    expect(meetingStateFromStructuredContent({ needs_meeting: true, workspace_id: "ws_1" })).toBeNull();
  });

  it("normalizes a meeting state response into editable text lists", () => {
    const state = meetingStateFromStructuredContent({
      meeting_id: "MEET-1",
      room_id: "conference_room",
      title: "Vendor Kickoff",
      agenda: ["review budget", 7, ""],
      decisions: ["use option b"],
      action_items: ["Sam sends notes"],
      parking_lot: ["pricing"],
      created_utc: "2026-04-21T12:00:00Z",
      updated_utc: "2026-04-21T12:05:00Z",
    });

    expect(state).toEqual({
      meeting_id: "MEET-1",
      room_id: "conference_room",
      title: "Vendor Kickoff",
      agenda: ["review budget", "7"],
      decisions: ["use option b"],
      action_items: ["Sam sends notes"],
      parking_lot: ["pricing"],
      created_utc: "2026-04-21T12:00:00Z",
      updated_utc: "2026-04-21T12:05:00Z",
    });
  });
});

describe("meetingBriefArtifactId", () => {
  it("extracts the saved artifact id for polished brief source linking", () => {
    expect(meetingBriefArtifactId({ artifact: { artifact_id: "art_123" } })).toBe("art_123");
    expect(meetingBriefArtifactId({ artifact: {} })).toBe("");
  });
});
