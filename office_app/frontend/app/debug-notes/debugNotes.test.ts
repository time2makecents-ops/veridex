import { describe, expect, it } from "vitest";

import { buildDebugNotePayload, debugNoteContextKey, normalizeDebugPagePath, prepareDebugNoteForEditing } from "./debugNotes";

describe("normalizeDebugPagePath", () => {
  it("normalizes empty and malformed paths to safe route keys", () => {
    expect(normalizeDebugPagePath("")).toBe("/");
    expect(normalizeDebugPagePath("chat")).toBe("/chat");
    expect(normalizeDebugPagePath("///admin/users?tab=all#top")).toBe("/admin/users");
  });
});

describe("buildDebugNotePayload", () => {
  it("keeps route text and optional runtime context together", () => {
    expect(
      buildDebugNotePayload({
        pagePath: "/chat",
        text: "room label is stale",
        sessionId: "sess_123",
        workspaceId: "ws_123",
        activeRoom: "hr_department",
        activePersona: "HR Manager",
      }),
    ).toEqual({
      page_path: "/chat",
      text: "room label is stale",
      session_id: "sess_123",
      workspace_id: "ws_123",
      active_room: "hr_department",
      active_persona: "HR Manager",
    });
  });

  it("builds room/persona scoped query params for chat notes", () => {
    expect(
      buildDebugNotePayload({
        pagePath: "/chat",
        text: "",
        activeRoom: "conference_room",
        activePersona: "Facilitator",
      }),
    ).toMatchObject({
      page_path: "/chat",
      active_room: "conference_room",
      active_persona: "Facilitator",
    });
  });
});

describe("debugNoteContextKey", () => {
  it("changes when the active chat room or persona changes", () => {
    expect(debugNoteContextKey("/chat", "lobby", "Receptionist")).toBe("/chat|lobby|Receptionist");
    expect(debugNoteContextKey("/chat", "sales_department", "Sales Director")).toBe(
      "/chat|sales_department|Sales Director",
    );
    expect(debugNoteContextKey("/profile", "sales_department", "Sales Director")).toBe("/profile");
  });
});

describe("prepareDebugNoteForEditing", () => {
  it("places the cursor two blank lines after existing note text", () => {
    expect(prepareDebugNoteForEditing("first note")).toEqual({
      text: "first note\n\n",
      selectionStart: 12,
    });
  });

  it("does not add extra spacing when the note already ends with two newlines", () => {
    expect(prepareDebugNoteForEditing("first note\n\n")).toEqual({
      text: "first note\n\n",
      selectionStart: 12,
    });
  });
});
