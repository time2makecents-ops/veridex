import { describe, expect, it } from "vitest";

import { cameraFailureNotice, nextStageAfterCameraFailure } from "./onboardingCamera";

describe("onboarding camera fallback", () => {
  it("continues to the pin stage when camera capture fails", () => {
    expect(nextStageAfterCameraFailure()).toBe("pin");
  });

  it("tells the user they can continue without a face photo", () => {
    expect(cameraFailureNotice(new Error("Permission denied"))).toContain("continue without a face photo");
    expect(cameraFailureNotice(new Error("Permission denied"))).toContain("Permission denied");
  });
});
