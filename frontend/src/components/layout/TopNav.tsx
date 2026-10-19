import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessions } from "../../contexts/SessionsContext";
import { useChatContext } from "../../contexts/ChatContext";
import { useSettings } from "../../contexts/SettingsContext";
import RoomHeader from "./RoomHeader";

const Icon: React.FC<React.PropsWithChildren> = ({ children }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

/** The chat's header: the room bar with session controls. */
const TopNav: React.FC = () => {
  const navigate = useNavigate();
  const { updateSettings } = useSettings();
  const { sessions, currentSessionId, getSession, updateSessionTitle, leftCollapsed, rightCollapsed, toggleLeft, toggleRight, setCurrentSession, deleteSession } = useSessions();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session?.title ?? "");
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const chat = useChatContext();

  useEffect(() => {
    setTitle(session?.title ?? "");
  }, [session]);

  function save() {
    if (currentSessionId) updateSessionTitle(currentSessionId, title.trim() || "Untitled session");
    setEditing(false);
  }

  function handleCreateNew() {
    setCurrentSession(null);
    chat.clearMessages();
    setMenuOpen(false);
  }

  function handleDeleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (confirm("Delete this session? This cannot be undone.")) deleteSession(id);
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
    <RoomHeader title="Chat" className="legacy-header">
      <div className="legacy-header__tools">
        <button className="icon-button" onClick={toggleLeft} aria-pressed={!leftCollapsed} aria-label={leftCollapsed ? "Show the side panel" : "Hide the side panel"} title={leftCollapsed ? "Show the side panel" : "Hide the side panel"}>
          <Icon><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M9 4v16" /></Icon>
        </button>
        <div className="sessions">
          <button className="btn" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen} aria-haspopup="true">
            Sessions <span className="mono sessions__count">{sessionsList.length}</span>
          </button>
          {menuOpen && (
            <>
              <div className="sessions__scrim" onClick={() => setMenuOpen(false)} />
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
                        <button className="sessions__open" role="menuitem" onClick={() => { setCurrentSession(s.id); setMenuOpen(false); }}>
                          <span className="sessions__title">{s.title}</span>
                          <span className="sessions__meta mono">
                            {new Date(s.updatedAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} · {s.messages.length} messages
                          </span>
                        </button>
                        <button className="sessions__delete" onClick={(e) => handleDeleteSession(s.id, e)} aria-label={`Delete “${s.title}”`}>
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>
        <button className="icon-button" onClick={copyChat} disabled={!session || session.messages.length === 0} aria-label="Copy the whole chat" title={copied ? "Copied" : "Copy the whole chat"}>
          {copied ? <Icon><path d="M20 6L9 17l-5-5" /></Icon> : <Icon><rect x="8" y="8" width="13" height="13" rx="1" /><path d="M16 8V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h4" /></Icon>}
        </button>
      </div>

      <div className="legacy-header__title">
        {editing ? (
          <form className="legacy-header__edit" onSubmit={(e) => { e.preventDefault(); save(); }}>
            <label htmlFor="session-title" className="sr-only">Session title</label>
            <input id="session-title" className="legacy-header__input" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
            <button type="submit" className="btn">Save</button>
            <button type="button" className="btn" onClick={() => { setEditing(false); setTitle(session?.title ?? ""); }}>Cancel</button>
          </form>
        ) : session ? (
          <button className="legacy-header__name" onClick={() => setEditing(true)} title="Rename this session">
            {session.title}
          </button>
        ) : (
          <span className="legacy-header__name legacy-header__name--quiet">New session</span>
        )}
      </div>

      <button className="btn" onClick={() => updateSettings({ interfaceMode: "desk" })} title="Switch to search">
        Switch to search
      </button>
      <button className="icon-button" aria-label="Settings" onClick={() => navigate("/settings")}>
        <Icon>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
        </Icon>
      </button>
      <button className="icon-button" onClick={toggleRight} aria-pressed={!rightCollapsed} aria-label={rightCollapsed ? "Show the sources" : "Hide the sources"} title={rightCollapsed ? "Show the sources" : "Hide the sources"}>
        <Icon><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M15 4v16" /></Icon>
      </button>
    </RoomHeader>
  );
};

export default TopNav;
