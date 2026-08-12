"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { enterSingleUser } from "@/lib/api";
import { setStoredSessionId } from "@/lib/session";

export default function SingleUserEntryPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const openVeridex = async () => {
      setError("");
      try {
        const result = await enterSingleUser();
        const sessionId = String(result?.session_id || result?.structuredContent?.session_id || "");
        if (!sessionId) {
          throw new Error("The local account did not return a session.");
        }
        if (cancelled) return;
        setStoredSessionId(sessionId);
        router.replace("/chat");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to open Veridex.");
        }
      }
    };

    void openVeridex();
    return () => {
      cancelled = true;
    };
  }, [attempt, router]);

  return (
    <main className="terminal-root">
      <section className="terminal-frame">
        <div className="terminal-display">
          <div className="terminal-header">VERIDEX LOCAL WORKSPACE</div>
          <div className="terminal-log">
            <div className="terminal-line">Opening the local account</div>
            <div className="terminal-line">Restoring the last workspace and session</div>
            <div className="terminal-line terminal-emphasis">
              {error ? "Unable to continue." : "Please wait..."}
            </div>
            {error ? <div className="terminal-error">{error}</div> : null}
          </div>
          {error ? (
            <button className="primary" type="button" onClick={() => setAttempt((current) => current + 1)}>
              Retry
            </button>
          ) : null}
        </div>
      </section>
    </main>
  );
}
