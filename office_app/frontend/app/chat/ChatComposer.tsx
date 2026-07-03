import type { FormEvent, KeyboardEvent, RefObject } from "react";

import { effectiveNancyMode, isNancyButtonHighlighted } from "./shortcutHelpers";

type ChatComposerProps = {
  activePersona: string;
  activeRoom: string;
  draft: string;
  draftRef: RefObject<HTMLTextAreaElement>;
  loading: boolean;
  memoMenuOpen: boolean;
  nancyMode: boolean;
  onDraftChange: (value: string) => void;
  onFileActionsToggle: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onMemoToggle: () => void;
  onNancyToggle: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function ChatComposer({
  activePersona,
  activeRoom,
  draft,
  draftRef,
  loading,
  memoMenuOpen,
  nancyMode,
  onDraftChange,
  onFileActionsToggle,
  onKeyDown,
  onMemoToggle,
  onNancyToggle,
  onSubmit,
}: ChatComposerProps) {
  return (
    <div className="composer-actions">
      <button type="button" className="ghost composer-plus" onClick={onFileActionsToggle} aria-label="Open file actions">
        +
      </button>
      <form className="composer lobby-composer" onSubmit={onSubmit}>
        <textarea
          ref={draftRef}
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={effectiveNancyMode(activeRoom, nancyMode) ? "Tell Nancy what to do..." : `Message ${activePersona}...`}
          rows={3}
        />
        <button className="primary" type="submit" disabled={loading || !draft.trim()}>
          Send
        </button>
        <button type="button" className={`ghost composer-inline-button ${memoMenuOpen ? "toolbar-button-active" : ""}`} onClick={onMemoToggle}>
          Memo
        </button>
        <button
          type="button"
          className={`ghost composer-inline-button ${isNancyButtonHighlighted(activeRoom, nancyMode) ? "toolbar-button-active" : ""}`}
          onClick={onNancyToggle}
        >
          Nancy
        </button>
      </form>
    </div>
  );
}
