import React, { useEffect, useState } from "react";
import { useSessions } from "../../contexts/SessionsContext";
import { useResponseSelection } from "../../contexts/ResponseSelectionContext";
import { openLocalPdf } from "../../utils/zotero";
import type { Source } from "../../types/session";

/**
 * The sources cited in the selected answer, as bibliography rows in citation
 * order. Legacy chat has no real relevance score for a source, so none is shown.
 */
const SourcesPanel: React.FC = () => {
  const { currentSessionId, getSession } = useSessions();
  const { selectedResponseId } = useResponseSelection();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [sources, setSources] = useState<Source[]>([]);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const message = session && selectedResponseId ? session.messages.find((m) => m.id === selectedResponseId) : null;
    setSources(message?.role === "assistant" && message.sources ? message.sources : []);
    setFailure(null);
  }, [session, selectedResponseId]);

  const state = !session
    ? "Ask a question to see the sources an answer cites."
    : !selectedResponseId
      ? "Choose an answer in the conversation to see its sources."
      : sources.length === 0
        ? "This answer cites no sources."
        : null;

  async function open(source: Source) {
    setFailure(null);
    try {
      if (!source.localPdfPath) throw new Error("This source has no PDF on this computer.");
      await openLocalPdf(String(source.localPdfPath));
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "Could not open the PDF.");
    }
  }

  return (
    <div className="side-panel side-panel--flush">
      <div className="panel-head">
        <span className="panel-head__title">Sources{sources.length ? ` · ${sources.length}` : ""}</span>
        {sources.length > 0 && <span className="panel-head__hint">in citation order</span>}
      </div>

      {state && <p className="side-panel__empty">{state}</p>}
      {failure && <p className="desk-notice desk-notice--error">{failure}</p>}

      {sources.length > 0 && (
        <ol className="cited">
          {sources.map((source, index) => {
            const query = encodeURIComponent(source.title);
            return (
              <li key={source.documentId} className="cited__row">
                <span className="cited__number">[{index + 1}]</span>
                <div className="cited__body">
                  <p className="cited__title">{source.title}</p>
                  <p className="cited__meta">
                    {source.author || "Unknown author"}
                    {source.year ? ` (${source.year})` : ""}
                    {source.snippets?.length ? ` · ${source.snippets.length} passage${source.snippets.length === 1 ? "" : "s"}` : ""}
                    {source.pageNumber ? ` · p. ${source.pageNumber}` : ""}
                  </p>
                  <div className="cited__actions">
                    {source.localPdfPath && (
                      <button type="button" className="btn" onClick={() => open(source)}>Open PDF</button>
                    )}
                    <a className="cited__link" href={`https://scholar.google.com/scholar?q=${query}`} target="_blank" rel="noreferrer">Google Scholar</a>
                    <a className="cited__link" href={`https://www.semanticscholar.org/search?q=${query}&sort=Relevance`} target="_blank" rel="noreferrer">Semantic Scholar</a>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
};

export default SourcesPanel;
