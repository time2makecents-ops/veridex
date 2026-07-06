import { describe, expect, it } from "vitest";

import {
  assistantMessageForResponse,
  activeWorkContextNoticeText,
  contactEmailRequest,
  confirmationLabelForAction,
  pendingBreakRoomJokeNotice,
  pendingNancyComposeNotice,
  pendingRoomNavigationNotice,
  pendingSessionListNotice,
  pendingWorkspaceSwitchNotice,
  roomStatusText,
  roomPersonaValues,
  shouldShowMessageText,
  workContextCancellationLabel,
  workContextConfirmationAssistantPersona,
  workContextConfirmationLabel,
  speakerForStructuredResponse,
  visibleMessagesForScope,
  workContextConfirmationId,
  workContextCompleteArgs,
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

  it("cleans raw Gmail HTML and quoted chains before rendering cards", () => {
    const message = assistantMessageForResponse(
      {
        gmail_message: {
          id: "msg_1",
          from: "Alex <alex@example.com>",
          body_text:
            "Got it.\n\nOn Thu, Jul 2, 2026 at 1:19 AM JR <jr@example.com> wrote:\n> Previous note.\n\n<div dir=\"ltr\">Got it.</div>",
        },
        gmail_thread: [
          {
            id: "msg_2",
            from: "JR <jr@example.com>",
            body_text: "<div dir=\"ltr\">Thanks.<br>JR</div>",
          },
        ],
      },
      "Loaded Gmail thread.",
      "Nancy",
      "my_office",
      "sess_1",
    );

    expect(message.gmailMessage?.body_text).toBe("Got it.");
    expect(message.gmailThread?.[0].body_text).toBe("Thanks.\nJR");
  });

  it("carries contact cards and hides duplicate contact-list text", () => {
    const message = assistantMessageForResponse(
      {
        contacts: [
          {
            email: "time2makecents@gmail.com",
            display_name: "James Willis",
            aliases: ["James", "Time2"],
            source: "gmail",
          },
        ],
      },
      "Found 1 contact(s). Select a contact card to use it.",
      "Nancy",
      "my_office",
      "sess_1",
    );

    expect(message.contacts?.[0].email).toBe("time2makecents@gmail.com");
    expect(shouldShowMessageText(message)).toBe(false);
  });

  it("carries work-context cards and hides duplicate work-context text", () => {
    const message = assistantMessageForResponse(
      {
        contexts: [
          {
            context_id: "ctx_manual_1",
            title: "Finalize launch plan",
            summary: "Coordinate Sales and Marketing.",
            status: "active",
            active_room: "sales_department",
            active_persona: "Sales Director",
          },
        ],
      },
      "Active work context:\n1. Finalize launch plan - Coordinate Sales and Marketing.",
      "Navigator",
      "sales_department",
      "sess_1",
    );

    expect(message.workContexts?.[0].title).toBe("Finalize launch plan");
    expect(message.workContexts?.[0].active_room).toBe("sales_department");
    expect(shouldShowMessageText(message)).toBe(false);
  });

  it("detects Nancy confirmation ids from active work context refs", () => {
    expect(
      workContextConfirmationId({
        context_id: "ctx_1",
        status: "active",
        refs: {
          kind: "nancy_email_confirmation",
          confirmation_id: "confirm_123",
        },
      }),
    ).toBe("confirm_123");
  });

  it("detects calendar confirmation ids from active work context refs", () => {
    expect(
      workContextConfirmationId({
        context_id: "ctx_calendar",
        status: "active",
        refs: {
          kind: "integration_confirmation",
          confirmation_id: "confirm_calendar",
          action_kind: "calendar.create",
        },
      }),
    ).toBe("confirm_calendar");
  });

  it("labels integration confirmation actions by kind", () => {
    expect(
      workContextConfirmationLabel({
        context_id: "ctx_calendar",
        refs: {
          kind: "integration_confirmation",
          action_kind: "calendar.update",
        },
      }),
    ).toBe("Confirm Calendar Update");
    expect(
      workContextConfirmationLabel({
        context_id: "ctx_email",
        refs: {
          kind: "nancy_email_confirmation",
          confirmation_id: "confirm_123",
        },
      }),
    ).toBe("Confirm Gmail Send");
  });

  it("labels integration dismissal actions by kind", () => {
    expect(
      workContextCancellationLabel({
        context_id: "ctx_calendar",
        refs: {
          kind: "integration_confirmation",
          action_kind: "calendar.cancel",
        },
      }),
    ).toBe("Dismiss Calendar Cancel");
    expect(
      workContextCancellationLabel({
        context_id: "ctx_email",
        refs: {
          kind: "nancy_email_confirmation",
          confirmation_id: "confirm_123",
        },
      }),
    ).toBe("Dismiss Gmail Send");
  });

  it("marks resumed confirmation work as Nancy-governed", () => {
    expect(
      workContextConfirmationAssistantPersona({
        context_id: "ctx_calendar",
        refs: {
          kind: "integration_confirmation",
          action_kind: "calendar.update",
        },
      }),
    ).toBe("Nancy");
    expect(
      workContextConfirmationAssistantPersona({
        context_id: "ctx_email",
        refs: {
          kind: "nancy_email_confirmation",
          confirmation_id: "confirm_123",
        },
      }),
    ).toBe("Nancy");
  });

  it("ignores non-confirmation work contexts", () => {
    expect(
      workContextConfirmationId({
        context_id: "ctx_2",
        refs: {
          kind: "manual_active_work",
        },
      }),
    ).toBe("");
  });

  it("formats pending Nancy compose guidance for body stage", () => {
    expect(
      pendingNancyComposeNotice({
        stage: "body",
        to: "time2makecents@gmail.com",
        subject: "Project update",
      }),
    ).toBe("Nancy is waiting for the body for time2makecents@gmail.com. Subject: Project update");
  });

  it("formats pending workspace switch guidance", () => {
    expect(
      pendingWorkspaceSwitchNotice({
        workspace_id: "ws_new",
        label: "Launch",
      }),
    ).toBe('Workspace "Launch" is ready. Switch now and start a new session there, or stay here.');
  });

  it("formats pending room navigation guidance", () => {
    expect(
      pendingRoomNavigationNotice({
        room_title: "Marketing & Advertising",
        persona: "Marketing Director",
      }),
    ).toBe("Move to Marketing & Advertising (Marketing Director) now, or stay here.");
  });

  it("formats pending session-list guidance", () => {
    expect(
      pendingSessionListNotice({
        request_text: "what sessions are in this workspace",
      }),
    ).toBe("List the sessions in this workspace now, or keep working here.");
  });

  it("formats pending break-room joke guidance", () => {
    expect(
      pendingBreakRoomJokeNotice({
        setup: "Why did the launch plan cross the room?",
      }),
    ).toBe("Break Room setup waiting: Why did the launch plan cross the room?");
  });

  it("builds a Nancy contact email request from the selected contact card", () => {
    expect(
      contactEmailRequest({
        email: "time2makecents@gmail.com",
        display_name: "James Willis",
      }),
    ).toBe("Nancy, email time2makecents@gmail.com");
  });

  it("builds work-context completion args with durable context id when present", () => {
    expect(workContextCompleteArgs("ctx_manual_exact", 2, "sess_1")).toEqual({
      context_id: "ctx_manual_exact",
      session_id: "sess_1",
    });
    expect(workContextCompleteArgs("", 2, "sess_1")).toEqual({
      active_index: 2,
      session_id: "sess_1",
    });
  });

  it("summarizes active work context for the cross-room strip", () => {
    expect(
      activeWorkContextNoticeText([
        {
          context_id: "ctx_manual_1",
          title: "Finalize launch plan",
          summary: "Coordinate Sales and Marketing.",
          status: "active",
          active_room: "sales_department",
          active_persona: "Sales Director",
        },
        {
          context_id: "ctx_done",
          title: "Completed item",
          status: "completed",
        },
      ]),
    ).toBe("Active work: Finalize launch plan - Coordinate Sales and Marketing. (sales_department / Sales Director)");
    expect(activeWorkContextNoticeText([])).toBe("");
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
