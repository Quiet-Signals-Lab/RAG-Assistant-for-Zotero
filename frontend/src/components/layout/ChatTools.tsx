import React, { useEffect, useState } from "react";
import { useSessions } from "../../contexts/SessionsContext";
import { useChatContext } from "../../contexts/ChatContext";

const Icon: React.FC<React.PropsWithChildren> = ({ children }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

/** RAG Chat's header tools: the sessions menu and copy. The title sits above the conversation. */
const ChatTools: React.FC = () => {
  const { sessions, currentSessionId, getSession, setCurrentSession, deleteSession } = useSessions();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const chat = useChatContext();

  // Escape closes the menu; the scrim and the button do too.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  function close() {
    setMenuOpen(false);
    setConfirming(null);
  }

  function handleCreateNew() {
    setCurrentSession(null);
    chat.clearMessages();
    close();
  }

  async function copyChat() {
    if (!session || session.messages.length === 0) return;
    const text = session.messages.map((m) => `${m.role === "user" ? "Question" : "Answer"}: ${m.content}`).join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }

  const sessionsList = Object.values(sessions).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));

  return (
    <div className="legacy-header__tools">
      <div className="sessions">
        <button className="btn" onClick={() => (menuOpen ? close() : setMenuOpen(true))} aria-expanded={menuOpen} aria-haspopup="true">
          Sessions <span className="mono sessions__count">{sessionsList.length}</span>
        </button>
        {menuOpen && (
          <>
            <div className="sessions__scrim" onClick={close} />
            <div className="sessions__menu" role="menu">
              <div className="panel-head sessions__head">
                <h2 className="panel-head__title">Sessions</h2>
                <button className="btn btn--primary" onClick={handleCreateNew}>New session</button>
              </div>
              {sessionsList.length === 0 ? (
                <p className="sessions__empty">No sessions yet. Ask a question to start one.</p>
              ) : (
                <ul className="sessions__list">
                  {sessionsList.map((s) => (
                    <li key={s.id} className={s.id === currentSessionId ? "sessions__row sessions__row--current" : "sessions__row"}>
                      <button className="sessions__open" role="menuitem" onClick={() => { setCurrentSession(s.id); close(); }}>
                        <span className="sessions__title">{s.title}</span>
                        <span className="sessions__meta mono">
                          {new Date(s.updatedAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} · {s.messages.length} messages
                        </span>
                      </button>
                      {confirming === s.id ? (
                        <span className="sessions__confirm">
                          <button type="button" className="btn btn--danger" onClick={() => { deleteSession(s.id); setConfirming(null); }}>Delete</button>
                          <button type="button" className="btn" onClick={() => setConfirming(null)}>Keep</button>
                        </span>
                      ) : (
                        <button className="sessions__delete" onClick={() => setConfirming(s.id)} aria-label={`Delete “${s.title}”`}>
                          ×
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
      <button className="icon-button" onClick={copyChat} disabled={!session || session.messages.length === 0} aria-label="Copy the whole conversation" title={copied ? "Copied" : "Copy the whole conversation"}>
        {copied ? <Icon><path d="M20 6L9 17l-5-5" /></Icon> : <Icon><rect x="8" y="8" width="13" height="13" rx="1" /><path d="M16 8V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h4" /></Icon>}
      </button>
    </div>
  );
};

export default ChatTools;
