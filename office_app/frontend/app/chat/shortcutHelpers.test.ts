import { describe, expect, it } from "vitest";

import {
  buildNavigatorModeRequest,
  buildNancyModeRequest,
  effectiveNancyMode,
  isNancyButtonHighlighted,
  NAVIGATOR_MODE_PREFIX,
  NANCY_MODE_PREFIX,
  nextNancyMode,
} from "./shortcutHelpers";

describe("Nancy mode", () => {
  it("routes room-local messages to Nancy without requiring a room switch", () => {
    expect(NANCY_MODE_PREFIX).toBe("Nancy, ");
    expect(buildNancyModeRequest("send an email to jane@example.com")).toBe("Nancy, send an email to jane@example.com");
  });

  it("does not duplicate the Nancy prefix", () => {
    expect(buildNancyModeRequest("Nancy, send an email to jane@example.com")).toBe("Nancy, send an email to jane@example.com");
  });

  it("keeps My Office as normal Nancy room chat", () => {
    expect(effectiveNancyMode("my_office", true)).toBe(false);
    expect(nextNancyMode("my_office", true)).toBe(false);
    expect(nextNancyMode("my_office", false)).toBe(false);
  });

  it("highlights Nancy in My Office or when over-the-shoulder mode is active", () => {
    expect(isNancyButtonHighlighted("my_office", false)).toBe(true);
    expect(isNancyButtonHighlighted("sales_department", true)).toBe(true);
    expect(isNancyButtonHighlighted("sales_department", false)).toBe(false);
  });
});

describe("Navigator panel mode", () => {
  it("routes panel messages to Navigator", () => {
    expect(NAVIGATOR_MODE_PREFIX).toBe("Navigator, ");
    expect(buildNavigatorModeRequest("run a status report")).toBe("Navigator, run a status report");
  });

  it("does not duplicate the Navigator prefix", () => {
    expect(buildNavigatorModeRequest("Navigator, run a status report")).toBe("Navigator, run a status report");
  });
});
