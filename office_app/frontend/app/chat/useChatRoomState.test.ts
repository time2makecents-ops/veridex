import { describe, expect, it } from "vitest";

import { pushRecentRoom } from "./useChatRoomState";

describe("pushRecentRoom", () => {
  it("adds the first room when the history is empty", () => {
    expect(pushRecentRoom([], "lobby")).toEqual(["lobby"]);
  });

  it("adds the newest room to the front and removes duplicates", () => {
    expect(pushRecentRoom(["lobby", "marketing_room", "sales_department"], "marketing_room")).toEqual([
      "marketing_room",
      "lobby",
      "sales_department",
    ]);
  });

  it("caps the list at three rooms", () => {
    expect(pushRecentRoom(["lobby", "marketing_room", "sales_department"], "conference_room")).toEqual([
      "conference_room",
      "lobby",
      "marketing_room",
    ]);
  });
});
