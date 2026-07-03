"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { getStoredSessionId } from "@/lib/session";

import {
  debugNoteContextKey,
  debugNoteScopeLabel,
  fetchDebugNote,
  normalizeDebugPagePath,
  prepareDebugNoteForEditing,
  saveDebugNote,
} from "./debugNotes";

type PageContext = {
  workspaceId: string;
  activeRoom: string;
  activePersona: string;
};

function currentPageContext(): PageContext {
  if (typeof document === "undefined") {
    return { workspaceId: "", activeRoom: "", activePersona: "" };
  }
  const element = document.querySelector<HTMLElement>("[data-workspace], [data-room], [data-persona]");
  return {
    workspaceId: String(element?.dataset.workspace || ""),
    activeRoom: String(element?.dataset.room || ""),
    activePersona: String(element?.dataset.persona || ""),
  };
}

export function DebugNotesWidget() {
  const pathname = usePathname();
  const pagePath = useMemo(() => normalizeDebugPagePath(pathname || "/"), [pathname]);
  const [pageContext, setPageContext] = useState<PageContext>(() => ({
    workspaceId: "",
    activeRoom: "",
    activePersona: "",
  }));
  const contextKey = useMemo(
    () => debugNoteContextKey(pagePath, pageContext.activeRoom, pageContext.activePersona),
    [pageContext.activePersona, pageContext.activeRoom, pagePath],
  );
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [updatedAt, setUpdatedAt] = useState("");
  const [scopeLabel, setScopeLabel] = useState(pagePath);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingSelectionRef = useRef<number | null>(null);

  async function loadNote() {
    setLoading(true);
    setStatus("");
    try {
      const record = await fetchDebugNote({
        pagePath,
        activeRoom: pageContext.activeRoom,
        activePersona: pageContext.activePersona,
      });
      const prepared = prepareDebugNoteForEditing(String(record.text || ""));
      pendingSelectionRef.current = prepared.selectionStart;
      setText(prepared.text);
      setUpdatedAt(String(record.updated_at || ""));
      setScopeLabel(debugNoteScopeLabel(record));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to load notes.");
    } finally {
      setLoading(false);
    }
  }

  async function saveNote() {
    setSaving(true);
    setStatus("");
    try {
      const record = await saveDebugNote({
        pagePath,
        text,
        sessionId: getStoredSessionId(),
        workspaceId: pageContext.workspaceId,
        activeRoom: pageContext.activeRoom,
        activePersona: pageContext.activePersona,
      });
      setUpdatedAt(String(record.updated_at || ""));
      setScopeLabel(debugNoteScopeLabel(record));
      setStatus("Saved");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to save notes.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    let lastKey = "";
    function refreshContext() {
      const next = currentPageContext();
      const nextKey = `${next.workspaceId}|${next.activeRoom}|${next.activePersona}`;
      if (nextKey === lastKey) {
        return;
      }
      lastKey = nextKey;
      setPageContext(next);
    }

    refreshContext();
    if (typeof MutationObserver === "undefined" || typeof document === "undefined") {
      return;
    }
    const observer = new MutationObserver(refreshContext);
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["data-workspace", "data-room", "data-persona"],
      childList: true,
      subtree: true,
    });
    return () => observer.disconnect();
  }, [pagePath]);

  useEffect(() => {
    if (!open) {
      return;
    }
    void loadNote();
  }, [contextKey, open, pagePath]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    const position = pendingSelectionRef.current ?? text.length;
    pendingSelectionRef.current = null;
    window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(position, position);
    });
  }, [open, text]);

  return (
    <div className={`debug-notes ${open ? "debug-notes-open" : ""}`}>
      <button
        type="button"
        className="debug-notes-button"
        aria-expanded={open}
        aria-controls="debug-notes-panel"
        onClick={() => setOpen((current) => !current)}
      >
        Notes
      </button>
      {open ? (
        <aside id="debug-notes-panel" className="debug-notes-panel" aria-label="Debug notes">
          <div className="debug-notes-header">
            <div>
              <div className="debug-notes-title">Debug notes</div>
              <div className="debug-notes-path">{scopeLabel}</div>
            </div>
            <button type="button" className="debug-notes-close" aria-label="Close debug notes" onClick={() => setOpen(false)}>
              x
            </button>
          </div>
          <textarea
            ref={textareaRef}
            className="debug-notes-textarea"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Add notes for this page, room, and assistant."
            rows={8}
          />
          <div className="debug-notes-actions">
            <button type="button" className="debug-notes-secondary" onClick={() => void loadNote()} disabled={loading || saving}>
              {loading ? "Loading" : "Refresh"}
            </button>
            <button type="button" className="debug-notes-primary" onClick={() => void saveNote()} disabled={loading || saving}>
              {saving ? "Saving" : "Save"}
            </button>
          </div>
          <div className="debug-notes-status">
            {status || (updatedAt ? `Saved ${updatedAt}` : "No saved note yet")}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
