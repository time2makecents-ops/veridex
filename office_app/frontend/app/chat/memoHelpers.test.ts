import { describe, expect, it } from "vitest";

import { buildMemoDispatchArgs, memoFromLabel, memoRoomOptions } from "./memoHelpers";

describe("memoFromLabel", () => {
  it("uses the active room title and persona for the form sender", () => {
    expect(memoFromLabel("sales_department", "Sales Director")).toBe("Sales Department - Sales Director");
  });
});

describe("memoRoomOptions", () => {
  it("excludes the active room and non-operational break room", () => {
    const options = memoRoomOptions("sales_department");
    const ids = options.map((room) => room.id);

    expect(ids).not.toContain("sales_department");
    expect(ids).not.toContain("break_room");
    expect(ids).toContain("marketing_room");
    expect(ids).toContain("my_office");
  });
});

describe("buildMemoDispatchArgs", () => {
  it("keeps subject optional and trims form text", () => {
    expect(
      buildMemoDispatchArgs({
        toRoom: "marketing_room",
        subject: "  Campaign follow-up  ",
        body: "  Please review the campaign plan.  ",
        sessionId: "sess_1",
      }),
    ).toEqual({
      to_room: "marketing_room",
      subject: "Campaign follow-up",
      body: "Please review the campaign plan.",
      session_id: "sess_1",
    });
  });

  it("omits blank subjects so the backend can generate one", () => {
    expect(
      buildMemoDispatchArgs({
        toRoom: "control_room",
        subject: "   ",
        body: "Check the routing health.",
      }),
    ).toEqual({
      to_room: "control_room",
      body: "Check the routing health.",
    });
  });
});
