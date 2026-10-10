import React, { useEffect, useState } from "react";
import { useSessions } from "../../contexts/SessionsContext";
import { useResponseSelection } from "../../contexts/ResponseSelectionContext";
import type { Source, Snippet } from "../../types/session";
import { Highlighted } from "../desk/parts";

/**
 * SnippetsPanel displays the passages behind the selected answer, grouped by
 * source, with the quoted text highlighted inside its paragraph.
 */
const SnippetsPanel: React.FC = () => {
  const { currentSessionId, getSession } = useSessions();
  const { selectedResponseId } = useResponseSelection();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [groupedSnippets, setGroupedSnippets] = useState<Map<string, { source: Source, snippets: Snippet[], citationIndex: number }>>(new Map());

  // Update snippets when selected response changes
  useEffect(() => {
    if (!session || !selectedResponseId) {
      setGroupedSnippets(new Map());
      return;
    }

    // Find the selected message
    const selectedMessage = session.messages.find(m => m.id === selectedResponseId);
    if (selectedMessage && selectedMessage.role === "assistant" && selectedMessage.sources) {
      // Group snippets by source, preserving citation index
      const grouped = new Map<string, { source: Source, snippets: Snippet[], citationIndex: number }>();
      
      selectedMessage.sources.forEach((source, index) => {
        if (source.snippets && source.snippets.length > 0) {
          // Sort snippets by confidence (highest first)
          const sortedSnippets = [...source.snippets].sort((a, b) => b.confidence - a.confidence);
          grouped.set(source.documentId, { source, snippets: sortedSnippets, citationIndex: index + 1 });
        }
      });
      
      setGroupedSnippets(grouped);
    } else {
      setGroupedSnippets(new Map());
    }
  }, [session, selectedResponseId]);

  const state = !session
    ? "Ask a question to see the passages the answer was written from."
    : !selectedResponseId
      ? "Choose an answer in the conversation to see its passages."
      : groupedSnippets.size === 0
        ? "This answer cites no passages from your library."
        : null;

  return (
    <div className="side-panel">
      <div className="panel-head">
        <span className="panel-head__title">Evidence</span>
        {groupedSnippets.size > 0 && (
          <span className="panel-head__hint">
            {groupedSnippets.size} source{groupedSnippets.size !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {state ? (
        <p className="side-panel__empty">{state}</p>
      ) : (
        Array.from(groupedSnippets.values()).map(({ source, snippets, citationIndex }) => (
          <section key={source.documentId} className="evidence-source">
            <h3 className="evidence-source__title">
              <span className="evidence-source__cite">[{citationIndex}]</span> {source.title}
            </h3>
            <p className="evidence-source__meta">
              {source.author}
              {source.year ? ` (${source.year})` : ""}
            </p>
            <ol className="passages">
              {snippets.map((snippet) => {
                const text = snippet.context || snippet.text;
                return (
                  <li key={snippet.id} className="passage">
                    <p className="passage__text">
                      <Highlighted text={text} spans={quoteSpan(snippet.text, text)} />
                    </p>
                    <div className="passage__meta">
                      {snippet.pageNumber ? <span>p. {snippet.pageNumber}</span> : <span>page unknown</span>}
                      {snippet.section && <span>{snippet.section}</span>}
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        ))
      )}
    </div>
  );
};

/** Where the quoted passage sits inside its paragraph, for highlighting. */
function quoteSpan(quote: string, context: string): [number, number][] {
  if (!quote || quote === context) return [];
  const at = context.toLowerCase().indexOf(quote.toLowerCase());
  return at === -1 ? [] : [[at, at + quote.length]];
}

export default SnippetsPanel;
