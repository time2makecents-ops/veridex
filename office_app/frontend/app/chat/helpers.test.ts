import { describe, expect, it } from "vitest";

import {
  assistantMessageForResponse,
  confirmationLabelForAction,
  roomStatusText,
  roomPersonaValues,
  shouldShowMessageText,
  speakerForStructuredResponse,
  visibleMessagesForScope,
} from "./helpers";
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

  it("trims empty profile entries and limits the displayed capabilities", () => {
    const text = roomStatusText("conference_room", "Facilitator", {
      primary_capabilities: [" planning ", "", "agenda", "decisions", "action_items", "parking_lot"],
      example_requests: ["show meeting state", ""],
    });

    expect(text).toContain("Capabilities: planning, agenda, decisions.");
    expect(text).toContain("Try: show meeting state");
    expect(text).not.toContain("action_items");
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

describe("confirmation helpers", () => {
  it("keeps Nancy as speaker for Nancy clarify responses", () => {
    expect(
      speakerForStructuredResponse(
        {
          speaker: "Nancy",
          routing: { route_kind: "clarify" },
        },
        "Sales Director",
      ),
    ).toBe("Nancy");
  });

  it("uses Navigator for clarify responses without an explicit speaker", () => {
    expect(
      speakerForStructuredResponse(
        {
          routing: { route_kind: "clarify" },
        },
        "Sales Director",
      ),
    ).toBe("Navigator");
  });

  it("labels Gmail send confirmations and leaves other actions unlabeled", () => {
    expect(confirmationLabelForAction("gmail.send")).toBe("Confirm Gmail Send");
    expect(confirmationLabelForAction("calendar.create")).toBeUndefined();
  });

  it("carries confirmation metadata onto assistant messages", () => {
    const message = assistantMessageForResponse(
      {
        confirmation_id: "confirm_123",
        action_kind: "gmail.send",
      },
      "Review and confirm the send.",
      "Navigator",
      "sales_department",
      "sess_1",
    );

    expect(message.confirmationId).toBe("confirm_123");
    expect(message.confirmationLabel).toBe("Confirm Gmail Send");
    expect(message.room).toBe("sales_department");
    expect(message.sessionId).toBe("sess_1");
    expect(message.speaker).toBe("Navigator");
    expect(message.text).toBe("Review and confirm the send.");
  });

  it("carries Gmail cards and email review metadata onto assistant messages", () => {
    const message = assistantMessageForResponse(
      {
        gmail_messages: [
          {
            id: "msg_1",
            index: 1,
            from: "Alex <alex@example.com>",
            subject: "Project update",
            date: "Thu, 2 Jul 2026 08:00:00 -0700",
            snippet: "Latest status.",
          },
        ],
        email_review: {
          to: ["jane@example.com"],
          subject: "Welcome",
          body: "Thanks for trying Veridex.",
        },
        gmail_thread: [
          {
            id: "msg_1",
            from: "Alex <alex@example.com>",
            subject: "Project update",
            body_text: "Thread body",
          },
        ],
      },
      "Found 1 Gmail message.",
      "Nancy",
      "my_office",
      "sess_1",
    );

    expect(message.gmailMessages?.[0].subject).toBe("Project update");
    expect(message.emailReview?.body).toBe("Thanks for trying Veridex.");
    expect(message.gmailThread?.[0].body_text).toBe("Thread body");
  });

  it("hides duplicate plain text when structured Gmail cards are present", () => {
    expect(
      shouldShowMessageText({
        id: "msg",
        role: "assistant",
        speaker: "Nancy",
        text: "Found 2 Gmail message(s).\n1. From...",
        gmailMessages: [{ id: "gmail_1", from: "Alex <alex@example.com>", subject: "Update" }],
      }),
    ).toBe(false);
    expect(
      shouldShowMessageText({
        id: "msg",
        role: "assistant",
        speaker: "Nancy",
        text: "Loaded Gmail thread.",
        gmailThread: [{ id: "gmail_1", from: "Alex <alex@example.com>", body_text: "Full body" }],
      }),
    ).toBe(false);
    expect(shouldShowMessageText({ id: "plain", role: "assistant", text: "Normal reply" })).toBe(true);
  });
});

describe("roomPersonaValues", () => {
  it("falls back to the default room and persona when state is missing", () => {
    expect(roomPersonaValues(undefined)).toEqual({ room: "lobby", persona: "Receptionist" });
  });

  it("uses active room and persona from state when present", () => {
    expect(roomPersonaValues({ active_room: "marketing_room", active_persona: "Marketing Director" })).toEqual({
      room: "marketing_room",
      persona: "Marketing Director",
    });
  });
});
