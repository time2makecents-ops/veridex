import { useEffect, useMemo, useState, type FormEvent } from "react";

import { getMemo, listMemos, sendMemo, type MemoRecord } from "@/lib/api";

import { roomById } from "./helpers";
import { buildMemoDispatchArgs, memoFromLabel, memoRoomOptions } from "./memoHelpers";

type MemoPanelProps = {
  activePersona: string;
  activeRoom: string;
  sessionId: string;
};

function roomTitle(roomId: string | undefined): string {
  if (!roomId) {
    return "";
  }
  return roomById(roomId)?.title || roomId;
}

function memoDate(value: string | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function MemoPanel({ activePersona, activeRoom, sessionId }: MemoPanelProps) {
  const roomOptions = useMemo(() => memoRoomOptions(activeRoom), [activeRoom]);
  const [toRoom, setToRoom] = useState(roomOptions[0]?.id || "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [memos, setMemos] = useState<MemoRecord[]>([]);
  const [selectedMemo, setSelectedMemo] = useState<MemoRecord | null>(null);
  const [loadingMemos, setLoadingMemos] = useState(false);
  const [sending, setSending] = useState(false);
  const [panelError, setPanelError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!roomOptions.some((room) => room.id === toRoom)) {
      setToRoom(roomOptions[0]?.id || "");
    }
  }, [roomOptions, toRoom]);

  async function refreshMemos(): Promise<MemoRecord[]> {
    setLoadingMemos(true);
    try {
      const rows = await listMemos(25);
      setMemos(rows);
      return rows;
    } finally {
      setLoadingMemos(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setPanelError("");
      try {
        const rows = await listMemos(25);
        if (!cancelled) {
          setMemos(rows);
        }
      } catch (err) {
        if (!cancelled) {
          setPanelError(err instanceof Error ? err.message : "Unable to load memos.");
        }
      }
    };
    if (sessionId) {
      void load();
    }
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  async function openMemo(memoId: string) {
    setPanelError("");
    setNotice("");
    try {
      setSelectedMemo(await getMemo(memoId));
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Unable to open memo.");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPanelError("");
    setNotice("");
    if (!toRoom) {
      setPanelError("Choose a destination room.");
      return;
    }
    if (!body.trim()) {
      setPanelError("Enter memo text before sending.");
      return;
    }

    setSending(true);
    try {
      const response = await sendMemo(buildMemoDispatchArgs({ toRoom, subject, body, sessionId }));
      const memoId = String(response.structuredContent?.memo_id || "");
      await refreshMemos();
      if (memoId) {
        setSelectedMemo(await getMemo(memoId));
      }
      setSubject("");
      setBody("");
      setNotice(`Memo sent to ${roomTitle(toRoom)}.`);
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : "Unable to send memo.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="dropdown-panel memo-panel">
      <div className="memo-layout">
        <form className="memo-compose" onSubmit={handleSubmit}>
          <div className="dropdown-group-title">Compose Memo</div>
          <label className="memo-field">
            <span>From</span>
            <input value={memoFromLabel(activeRoom, activePersona)} readOnly />
          </label>
          <label className="memo-field">
            <span>To</span>
            <select value={toRoom} onChange={(event) => setToRoom(event.target.value)}>
              {roomOptions.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.title} - {room.persona}
                </option>
              ))}
            </select>
          </label>
          <label className="memo-field">
            <span>Subject</span>
            <input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Optional" />
          </label>
          <label className="memo-field">
            <span>Memo</span>
            <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={6} placeholder="Write the internal memo..." />
          </label>
          <button type="submit" disabled={sending || !body.trim()}>
            {sending ? "Sending..." : "Send Memo"}
          </button>
          {notice ? <div className="session-action-notice">{notice}</div> : null}
          {panelError ? <div className="error">{panelError}</div> : null}
        </form>

        <div className="memo-inbox">
          <div className="dropdown-group-title">Recent Memos</div>
          <div className="memo-list">
            {loadingMemos ? <div className="muted">Loading memos...</div> : null}
            {!loadingMemos && !memos.length ? <div className="muted">No memos found.</div> : null}
            {memos.map((memo) => (
              <button
                key={memo.memo_id}
                type="button"
                className={`ghost memo-list-button ${selectedMemo?.memo_id === memo.memo_id ? "toolbar-button-active" : ""}`}
                onClick={() => void openMemo(memo.memo_id)}
              >
                <span>{memo.subject || "(no subject)"}</span>
                <span>
                  {roomTitle(memo.from_room)} to {roomTitle(memo.to_room)}
                </span>
                <span>{memo.reply_status === "replied" ? `Replied by ${memo.reply_persona || memo.to_persona || "room"}` : "Pending"}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {selectedMemo ? (
        <div className="memo-detail">
          <div className="memo-detail-header">
            <div>
              <div className="dropdown-group-title">Memo Detail</div>
              <strong>{selectedMemo.subject || "(no subject)"}</strong>
            </div>
            <span>{memoDate(selectedMemo.created_utc)}</span>
          </div>
          <div className="memo-meta">
            From {roomTitle(selectedMemo.from_room)} to {roomTitle(selectedMemo.to_room)}
            {selectedMemo.to_persona ? ` (${selectedMemo.to_persona})` : ""}
          </div>
          <div className="memo-body">{selectedMemo.body || ""}</div>
          {selectedMemo.reply_text ? (
            <div className="memo-reply">
              <div className="memo-meta">Response from {selectedMemo.reply_persona || selectedMemo.to_persona || roomTitle(selectedMemo.to_room)}</div>
              <div>{selectedMemo.reply_text}</div>
            </div>
          ) : (
            <div className="muted">No response recorded yet.</div>
          )}
        </div>
      ) : null}
    </div>
  );
}
