import type { FileRecord } from "@/lib/api";

type DocumentReaderProps = {
  readerFile: FileRecord | null;
  readerLoading: boolean;
  readerText: string;
  readerTitle: string;
  onClose: () => void;
  onDownload: (file: FileRecord) => void;
};

export function DocumentReader({ readerFile, readerLoading, readerText, readerTitle, onClose, onDownload }: DocumentReaderProps) {
  return (
    <section className="card document-reader-shell">
      <div className="terminal-panel-title">Document Reader</div>
      <div className="toolbar-row">
        <div className="reader-title">{readerTitle}</div>
        {readerFile ? (
          <button type="button" className="secondary" onClick={() => onDownload(readerFile)}>
            Download
          </button>
        ) : null}
        <button type="button" className="ghost toolbar-button" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="reader-window">
        {readerLoading ? <div className="muted">Loading document...</div> : <pre>{readerText || "Select a document."}</pre>}
      </div>
    </section>
  );
}
