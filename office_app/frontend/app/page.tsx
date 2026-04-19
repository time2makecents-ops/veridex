"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { enter } from "../lib/api";
import { setStoredSessionId } from "../lib/session";

const INTRO_LINES = [
  "scanning biometrics",
  "verifying access point",
  "terminal ready",
];

const VISITOR_MESSAGE = `Visitor detected.

"Please go directly to the Lobby and check in with the receptionist."

Access level: PENDING`;

const KEYPAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "CLR", "0", "CALL"];
const VISITOR_TEXT_DELAY_MS = 70;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function ExteriorTerminalPage() {
  const router = useRouter();
  const [pinCode, setPinCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<"scan" | "ready">("scan");
  const [visitorText, setVisitorText] = useState("");
  const [showVisitorMessage, setShowVisitorMessage] = useState(false);

  const visibleIntro = useMemo(() => INTRO_LINES.slice(0, phase === "scan" ? 2 : 3), [phase]);

  useEffect(() => {
    let cancelled = false;

    const runIntro = async () => {
      await sleep(800);
      if (cancelled) return;
      setPhase("ready");
    };

    void runIntro();

    return () => {
      cancelled = true;
    };
  }, []);

  const pressKey = (key: string) => {
    if (busy) return;
    setError("");

    if (key === "CLR") {
      setPinCode("");
      return;
    }

    if (key === "CALL") {
      void handleCall();
      return;
    }

    if (pinCode.length >= 4) return;
    setPinCode((current) => `${current}${key}`);
  };

  const printVisitorDialogue = async () => {
    setBusy(true);
    setError("");
    setShowVisitorMessage(true);
    setVisitorText("");
    setPinCode("");

    for (const character of VISITOR_MESSAGE) {
      // Type the dialog slowly like an old access terminal.
      // eslint-disable-next-line no-await-in-loop
      await sleep(VISITOR_TEXT_DELAY_MS);
      setVisitorText((current) => `${current}${character}`);
    }

    await sleep(700);
    router.push("/onboard");
    setBusy(false);
  };

  const handleCall = async () => {
    if (busy) return;

    if (pinCode.length === 0) {
      void printVisitorDialogue();
      return;
    }

    if (pinCode.length !== 4) {
      setError("Enter all 4 digits, or press CALL with no code for visitor access.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const result = await enter(pinCode);
      if (result?.session_id) {
        setStoredSessionId(result.session_id);
      }
      router.push("/chat");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Access denied.";
      setError(message);
      setPinCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="terminal-root">
      <section className="terminal-frame">
        <div className="terminal-display">
          <div className="terminal-header">VERIDEX EXTERIOR ACCESS TERMINAL</div>

          <div className="terminal-log">
            {showVisitorMessage ? (
              <div className="terminal-line terminal-visitor">
                {visitorText}
              </div>
            ) : (
              <>
                {visibleIntro.map((line) => (
                  <div key={line} className="terminal-line">
                    {line}
                  </div>
                ))}
                <div className="terminal-line terminal-emphasis">
                  Enter personal ID code, or press CALL if you are a visitor.
                </div>
                <div className="terminal-code">{pinCode || "----"}</div>
              </>
            )}
            {error ? <div className="terminal-error">{error}</div> : null}
          </div>

          <div className="terminal-keypad">
            {KEYPAD.map((key) => (
              <button
                key={key}
                type="button"
                className={`terminal-key ${key === "CALL" ? "terminal-call" : ""}`}
                onClick={() => pressKey(key)}
                disabled={busy}
              >
                {key}
              </button>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
