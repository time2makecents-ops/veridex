"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { onboard } from "@/lib/api";
import { setStoredSessionId } from "@/lib/session";
import { cameraFailureNotice, nextStageAfterCameraFailure, type OnboardingStage } from "./onboardingCamera";

export default function OnboardPage() {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cameraReadyRef = useRef(false);
  const [fullName, setFullName] = useState("");
  const [userName, setUserName] = useState("");
  const [pinCode, setPinCode] = useState("");
  const [stage, setStage] = useState<OnboardingStage>("intro");
  const [countdown, setCountdown] = useState<number | null>(null);
  const [facePhotoData, setFacePhotoData] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [cameraReady, setCameraReady] = useState(false);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    if (stage !== "camera") {
      return;
    }

    const video = videoRef.current;
    const stream = streamRef.current;
    if (!video || !stream) {
      return;
    }

    let cancelled = false;
    const attach = async () => {
      setCameraReady(false);
      cameraReadyRef.current = false;
      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;
      video.autoplay = true;
      try {
        await video.play();
        if (cancelled) return;
        cameraReadyRef.current = true;
        setCameraReady(true);
      } catch {
        if (!cancelled) {
          setCameraError("Camera preview could not start.");
        }
      }
    };

    void attach();

    return () => {
      cancelled = true;
    };
  }, [stage]);

  async function startCamera() {
    setCameraError("");
    setCameraReady(false);
    cameraReadyRef.current = false;
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: "user" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });
    streamRef.current = stream;
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  async function waitForRenderedFrame(video: HTMLVideoElement) {
    if (typeof video.requestVideoFrameCallback === "function") {
      await new Promise<void>((resolve) => {
        video.requestVideoFrameCallback(() => resolve());
      });
      return;
    }

    for (let i = 0; i < 20; i += 1) {
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0 && video.videoHeight > 0) {
        return;
      }
      // Wait for a real painted frame on browsers that do not support requestVideoFrameCallback.
      // eslint-disable-next-line no-await-in-loop
      await new Promise((resolve) => window.setTimeout(resolve, 50));
    }
  }

  async function captureFace() {
    const video = videoRef.current;
    if (!video) {
      throw new Error("Camera not ready.");
    }
    await waitForRenderedFrame(video);
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Unable to capture image.");
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85);
  }

  async function beginCameraStep() {
    setError("");
    try {
      await startCamera();
      setStage("camera");
      for (let i = 0; i < 10 && !cameraReadyRef.current; i += 1) {
        // Wait briefly for the live preview to paint.
        // This avoids grabbing a black first frame on slower phones.
        // eslint-disable-next-line no-await-in-loop
        await new Promise((resolve) => window.setTimeout(resolve, 100));
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250));
      for (let remaining = 3; remaining >= 1; remaining -= 1) {
        setCountdown(remaining);
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      const photo = await captureFace();
      setFacePhotoData(photo);
      stopCamera();
      setStage("pin");
      setCountdown(null);
    } catch (err) {
      setCameraError(cameraFailureNotice(err));
      setFacePhotoData("");
      setStage(nextStageAfterCameraFailure());
      setCountdown(null);
      stopCamera();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (stage === "intro") {
      setError("");
      if (!fullName.trim() || !userName.trim()) {
        setError("Please enter your full name and user name first.");
        return;
      }
      await beginCameraStep();
      return;
    }

    setError("");
    setLoading(true);
    try {
      const response = await onboard(fullName, userName, pinCode, facePhotoData || undefined);
      const sessionId = String(response.session_id || response.structuredContent?.session_id || "");
      if (!sessionId) {
        throw new Error("Missing session ID from server.");
      }
      setStoredSessionId(sessionId);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to onboard.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="screen">
      <section className="card stack">
        <div>
          <p className="muted" style={{ textTransform: "uppercase", letterSpacing: "0.12em", fontSize: "0.78rem" }}>
            Lobby Reception
          </p>
          <h1 className="title">Welcome to Veridex Headquarters</h1>
          <p className="muted">Visitor access confirmed. Please enter your full name and user name.</p>
        </div>

        <form className="stack" onSubmit={handleSubmit}>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name" autoComplete="name" />
          {stage === "intro" ? (
            <input value={userName} onChange={(e) => setUserName(e.target.value)} placeholder="User name" autoComplete="username" />
          ) : null}

          {stage === "camera" ? (
            <div className="card stack" style={{ padding: 14, background: "#0f1720", color: "white" }}>
              <div
                style={{
                  position: "relative",
                  borderRadius: 18,
                  overflow: "hidden",
                  aspectRatio: "3 / 4",
                  background: "#000",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                  <video
                  ref={videoRef}
                  playsInline
                  muted
                  autoPlay
                  onLoadedMetadata={() => setCameraReady(true)}
                  onCanPlay={() => setCameraReady(true)}
                  onPlaying={() => setCameraReady(true)}
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                    transform: "scaleX(-1)",
                    background: "#000",
                    opacity: cameraReady ? 1 : 0.65,
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "grid",
                    placeItems: "center",
                    background: "linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.42))",
                    pointerEvents: "none",
                  }}
                >
                  <div style={{ textAlign: "center", color: "white" }}>
                    <div style={{ fontSize: "0.72rem", letterSpacing: "0.12em", textTransform: "uppercase" }}>
                      Keep your face in full view of the terminal screen.
                    </div>
                    <div style={{ fontSize: "5rem", fontWeight: 900, lineHeight: 1, marginTop: 10, fontVariantNumeric: "tabular-nums" }}>
                      {countdown ?? 3}
                    </div>
                    {!cameraReady ? (
                      <div style={{ marginTop: 10, fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", opacity: 0.8 }}>
                        Camera warming up
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
              <p className="muted" style={{ color: "rgba(255,255,255,0.8)", margin: 0 }}>
                Running facial recognition.
              </p>
            </div>
            ) : null}

          {stage === "pin" ? (
            <>
              <div className="card" style={{ padding: 14, background: "#fdf8ef" }}>
                <p className="muted" style={{ margin: 0 }}>
                  Thank you {userName || "visitor"}.
                  <br />
                  On the keypad, create a 4 digit pin code. This code will allow you to enter the building at all hours.
                  Keep this number private.
                </p>
              </div>
              <input
                value={pinCode}
                onChange={(e) => setPinCode(e.target.value.replace(/\D/g, "").slice(0, 4))}
                placeholder="4-digit code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
              />
            </>
          ) : null}

          {cameraError ? <div className="error">{cameraError}</div> : null}
          {error ? <div className="error">{error}</div> : null}
          <button className="primary" type="submit" disabled={loading || stage === "camera"}>
            {stage === "intro" ? "Continue to Camera" : stage === "camera" ? "Hold still" : loading ? "Submitting..." : "Submit"}
          </button>
        </form>
      </section>
    </main>
  );
}
