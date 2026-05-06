import React, { useState, useEffect } from "react";
import { useSessions } from "../../contexts/SessionsContext";
import { useResponseSelection } from "../../contexts/ResponseSelectionContext";
import { apiFetch } from "../../api/client";
import type { Source } from "../../types/session";

/**
 * SourcesPanel displays sources specific to the currently selected response.
 * Sources are sorted by confidence (highest first) and include metadata like
 * relevance score, author, and page numbers.
 */
const SourcesPanel: React.FC = () => {
  const { currentSessionId, getSession, rightCollapsed, toggleRight } = useSessions();
  const { selectedResponseId } = useResponseSelection();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [sources, setSources] = useState<Source[]>([]);

  // Update sources when selected response changes
  useEffect(() => {
    if (!session || !selectedResponseId) {
      setSources([]);
      return;
    }

    // Find the selected message
    const selectedMessage = session.messages.find(m => m.id === selectedResponseId);
    console.log("SourcesPanel: selectedMessage", selectedMessage);
    console.log("SourcesPanel: selectedMessage.sources", selectedMessage?.sources);
    
    if (selectedMessage && selectedMessage.role === "assistant" && selectedMessage.sources) {
      // Sort by confidence (highest first)
      const sortedSources = [...selectedMessage.sources].sort((a, b) => b.confidence - a.confidence);
      setSources(sortedSources);
      console.log("SourcesPanel: Setting sources", sortedSources);
    } else {
      setSources([]);
      console.log("SourcesPanel: No sources found for message");
    }
  }, [session, selectedResponseId]);

  if (!session) {
    return (
      <>
        <header>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: "20px", fontWeight: 600, color: "var(--text-main)", letterSpacing: "0.02em", marginBottom: "4px" }}>Sources</div>
          <div className="muted">Cited sources for selected response.</div>
        </header>
        <main>
          <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)" }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ margin: "0 auto 16px", opacity: 0.3 }}>
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <div style={{ fontSize: "14px", fontWeight: 600, marginBottom: "8px" }}>No Active Session</div>
            <div style={{ fontSize: "13px" }}>Ask a question to see cited sources from your library.</div>
          </div>
        </main>
      </>
    );
  }

  if (!selectedResponseId) {
    return (
      <>
        <header>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: "20px", fontWeight: 600, color: "var(--text-main)", letterSpacing: "0.02em", marginBottom: "4px" }}>Sources</div>
          <div className="muted">Select a response to view sources.</div>
        </header>
        <main>
          <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)" }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ margin: "0 auto 16px", opacity: 0.3 }}>
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <div style={{ fontSize: "14px", fontWeight: 600, marginBottom: "8px" }}>No Response Selected</div>
            <div style={{ fontSize: "13px" }}>Click on an assistant response to view its sources.</div>
          </div>
        </main>
      </>
    );
  }

  if (sources.length === 0) {
    return (
      <>
        <header>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: "20px", fontWeight: 600, color: "var(--text-main)", letterSpacing: "0.02em", marginBottom: "4px" }}>Sources</div>
          <div className="muted">No sources for this response.</div>
        </header>
        <main>
          <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)" }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ margin: "0 auto 16px", opacity: 0.3 }}>
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <div style={{ fontSize: "14px", fontWeight: 600, marginBottom: "8px" }}>No Sources</div>
            <div style={{ fontSize: "13px" }}>This response has no source citations.</div>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: "20px", fontWeight: 600, color: "var(--text-main)", letterSpacing: "0.02em", marginBottom: "4px" }}>Sources</div>
          <div className="muted">Showing {sources.length} source{sources.length !== 1 ? 's' : ''} (sorted by relevance)</div>
        </div>
        <div>
          <button className="btn" onClick={toggleRight} title={rightCollapsed ? "Show sources" : "Hide sources"}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              {rightCollapsed ? <path d="M15 6l-6 6 6 6" stroke="#5b4632" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/> : <path d="M9 6l6 6-6 6" stroke="#5b4632" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>}
            </svg>
          </button>
        </div>
      </header>
      <main>
        <div style={{ marginTop: 8 }}>
          {sources.map((source, index) => (
            <div key={source.documentId} style={{ borderBottom: "1px solid var(--border-subtle)", marginBottom: "8px" }}>
              {/* Top section: metadata */}
              <div style={{ padding: 12, display: "flex", alignItems: "flex-start", gap: "12px" }}>
                <div style={{ 
                  minWidth: "32px", 
                  height: "32px", 
                  borderRadius: "50%", 
                  background: "var(--accent)", 
                  color: "white", 
                  display: "flex", 
                  alignItems: "center", 
                  justifyContent: "center", 
                  fontSize: "14px", 
                  fontWeight: 600,
                  flexShrink: 0
                }}>
                  {index + 1}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, marginBottom: "4px" }}>{source.title}</div>
                  <div className="muted" style={{ fontSize: 12, marginBottom: "6px" }}>
                    {source.author || "Unknown author"}{source.year ? ` (${source.year})` : ""}
                    {source.pageNumber ? ` • Page ${source.pageNumber}` : ""}
                  </div>
                  <div style={{ 
                    display: "inline-block", 
                    background: source.confidence >= 0.9 ? "#e8f5e9" : source.confidence >= 0.8 ? "#fff3e0" : "#fce4ec",
                    color: source.confidence >= 0.9 ? "#2e7d32" : source.confidence >= 0.8 ? "#e65100" : "#c2185b",
                    padding: "2px 8px", 
                    borderRadius: "12px", 
                    fontSize: "11px",
                    fontWeight: 600
                  }}>
                    {(source.confidence * 100).toFixed(0)}% relevance
                  </div>
                </div>
              </div>
              {/* Bottom section: action buttons */}
              <div style={{ padding: "8px 12px", borderTop: "1px solid var(--border-subtle)", background: "var(--bg-panel-alt, #fafafa)", display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <button
                  className="btn"
                  title="PDF"
                  style={{ fontFamily: "system-ui, sans-serif", fontSize: "9px" }}
                  onClick={async () => {
                    if (source.localPdfPath) {
                      const fp = String(source.localPdfPath);
                      console.log("Opening PDF:", fp);
                      try {
                        const resp = await apiFetch("/api/open_pdf", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ pdf_path: fp }),
                        });
                        const data = await resp.json();
                        if (data.error) {
                          alert(`Failed to open PDF: ${data.error}`);
                        }
                      } catch (e) {
                        console.error("Failed to open PDF:", e);
                        alert("Failed to open PDF. Check console for details.");
                      }
                    } else {
                      alert("No local PDF path available for this source");
                    }
                  }}
                >
                  PDF
                </button>

                <a className="btn" style={{ fontFamily: "system-ui, sans-serif", fontSize: "9px", display: "flex", alignItems: "center", gap: "5px" }} href={`https://scholar.google.com/scholar?q=${encodeURIComponent(source.title)}`} target="_blank" rel="noreferrer">
                  <img src="https://www.google.com/s2/favicons?domain=scholar.google.com&sz=16" width="13" height="13" alt="" style={{ display: "block", flexShrink: 0 }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                  Google Scholar
                </a>
                
                <a className="btn" style={{ fontFamily: "system-ui, sans-serif", fontSize: "9px", display: "flex", alignItems: "center", gap: "5px" }} href={`https://www.google.com/search?tbm=bks&q=${encodeURIComponent(source.title)}`} target="_blank" rel="noreferrer">
                  <img src="https://www.google.com/s2/favicons?domain=books.google.com&sz=16" width="13" height="13" alt="" style={{ display: "block", flexShrink: 0 }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                  Google Books
                </a>

                <a 
                  className="btn"
                  style={{ fontFamily: "system-ui, sans-serif", fontSize: "9px", display: "flex", alignItems: "center", gap: "5px" }}
                  href={`https://www.semanticscholar.org/search?q=${encodeURIComponent(source.title)}&sort=Relevance`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img src="https://www.google.com/s2/favicons?domain=semanticscholar.org&sz=16" width="13" height="13" alt="" style={{ display: "block", flexShrink: 0 }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                  Semantic Scholar
                </a>
                
                {source.snippets && source.snippets.length > 0 && (
                  <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
                    {source.snippets.length} snippet{source.snippets.length !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </main>
    </>
  );
};

export default SourcesPanel;
