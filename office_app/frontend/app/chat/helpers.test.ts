import { describe, expect, it } from "vitest";

import { roomStatusText, visibleMessagesForScope } from "./helpers";
import type { Message } from "./types";

describe("roomStatusText", () => {
  it("includes capabilities and example requests when present", () => {
    const text = roomStatusText("marketing_room", "Marketing Director", {
      primary_capabilities: ["campaign_strategy", "market_research"],
      example_requests: ["find social media trends for coffee shops"],
    });

    expect(text).toContain("Now in Marketing & Advertising. Persona: Marketing Director.");
    expect(text).toContain("Capabilities: campaign_strategy, market_research.");
    expect(text).toContain("Try: find social media trends for coffee shops");
  });

  it("falls back to the base transition when no profile is present", () => {
    expect(roomStatusText("lobby", "Receptionist")).toBe("Now in Lobby. Persona: Receptionist.");
  });
});

describe("visibleMessagesForScope", () => {
  const messages: Message[] = [
    { id: "1", role: "user", text: "room one", room: "sales_department", sessionId: "sess_1" },
    { id: "2", role: "assistant", text: "room two", room: "marketing_room", sessionId: "sess_1" },
    { id: "3", role: "assistant", text: "global", sessionId: "sess_1" },
    { id: "4", role: "assistant", text: "other session", room: "sales_department", sessionId: "sess_2" },
  ];

  it("filters to the active room within the active session for room scope", () => {
    expect(visibleMessagesForScope(messages, "sess_1", "room", "sales_department").map((item) => item.id)).toEqual([
      "1",
      "3",
    ]);
  });

  it("shows all active-session messages for global scope", () => {
    expect(visibleMessagesForScope(messages, "sess_1", "global", "sales_department").map((item) => item.id)).toEqual([
      "1",
      "2",
      "3",
    ]);
  });
});
