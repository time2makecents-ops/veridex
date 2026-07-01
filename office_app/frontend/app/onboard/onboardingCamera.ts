export type OnboardingStage = "intro" | "camera" | "pin";

export function nextStageAfterCameraFailure(): OnboardingStage {
  return "pin";
}

export function cameraFailureNotice(error: unknown): string {
  const detail = error instanceof Error && error.message.trim() ? error.message.trim() : "Camera is unavailable.";
  return `${detail} You can continue without a face photo.`;
}
