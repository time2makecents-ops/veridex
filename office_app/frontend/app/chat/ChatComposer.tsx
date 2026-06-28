import type { FormEvent, KeyboardEvent, RefObject } from "react";

type ChatComposerProps = {
  activePersona: string;
  draft: string;
  draftRef: RefObject<HTMLTextAreaElement>;
  loading: boolean;
  onDraftChange: (value: string) => void;
  onFileActionsToggle: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function ChatComposer({
  activePersona,
  draft,
  draftRef,
  loading,
  onDraftChange,
  onFileActionsToggle,
  onKeyDown,
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
          placeholder={`Message ${activePersona}...`}
          rows={3}
        />
        <button className="primary" type="submit" disabled={loading || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
