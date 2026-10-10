import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSessions } from "../../contexts/SessionsContext";
import { useChatContext } from "../../contexts/ChatContext";

const IconPanel = ({ children }: { children: React.ReactNode }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    {children}
  </svg>
);

const TopNav: React.FC = () => {
  const navigate = useNavigate();
  const { sessions, currentSessionId, getSession, updateSessionTitle, leftCollapsed, rightCollapsed, toggleLeft, toggleRight, setCurrentSession, deleteSession } = useSessions();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session?.title ?? "RAG Assistant for Zotero");
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setTitle(session?.title ?? "RAG Assistant for Zotero");
  }, [session]);

  function save() {
    if (!currentSessionId) return setEditing(false);
    updateSessionTitle(currentSessionId, title.trim() || "Untitled session");
    setEditing(false);
  }

  const chat = useChatContext();

  function handleCreateNew() {
    // Clear current session so the next message will create a new one
    setCurrentSession(null);
    chat.clearMessages();
    setMenuOpen(false);
  }

  function handleDeleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (confirm("Delete this session? This cannot be undone.")) {
      deleteSession(id);
    }
  }

  const sessionsList = Object.values(sessions).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));

  return (
    <nav className="top-nav">
      <div className="top-nav__left">
        <button className="btn" onClick={toggleLeft} title={leftCollapsed ? "Show snippets" : "Hide snippets"}>
          <IconPanel>
            {leftCollapsed ? <path d="M9 18l6-6-6-6" stroke="#5b4632" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/> : <path d="M15 18l-6-6 6-6" stroke="#5b4632" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>}
          </IconPanel>
        </button>
        <div style={{ width: 8 }} />
        <button 
          className="btn" 
          onClick={() => {
            if (!session || session.messages.length === 0) {
              alert('No chat to copy');
              return;
            }
            const chatText = session.messages.map(m => 
              `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`
            ).join('\n\n');
            navigator.clipboard.writeText(chatText).then(() => {
              alert('Chat copied to clipboard!');
            }).catch(err => {
              console.error('Failed to copy:', err);
              alert('Failed to copy chat');
            });
          }}
          disabled={!session || session.messages.length === 0}
          title="Copy entire chat to clipboard"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <rect x="8" y="2" width="8" height="4" rx="1" ry="1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <div style={{ width: 8 }} />
        <div style={{ position: 'relative' }}>
          <button className="btn" onClick={() => setMenuOpen((s) => !s)} title="Sessions">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: "4px" }}>
              <path d="M3 9h18M3 15h18M9 3v18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Sessions {sessionsList.length > 0 && `(${sessionsList.length})`}
          </button>
          {menuOpen && (
            <>
              <div style={{ position: 'fixed', inset: 0, zIndex: 79 }} onClick={() => setMenuOpen(false)} />
              <div className="sessions-menu" style={{ 
                position: 'absolute', 
                top: '40px', 
                left: 0, 
                background: 'var(--bg-panel)', 
                border: '1px solid var(--border-subtle)', 
                borderRadius: 8, 
                padding: 0,
                boxShadow: '0 4px 16px rgba(0,0,0,0.15)', 
                minWidth: 360, 
                maxWidth: 480,
                zIndex: 80 
              }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>Sessions</div>
                  <button className="btn btn--primary" onClick={handleCreateNew} style={{ padding: '4px 12px', fontSize: '12px' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: "4px" }}>
                      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                    </svg>
                    New
                  </button>
                </div>
                <div style={{ maxHeight: 400, overflow: 'auto' }}>
                  {sessionsList.length === 0 && (
                    <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--text-muted)' }}>
                      <div style={{ fontSize: '13px' }}>No sessions yet.</div>
                      <div style={{ fontSize: '12px', marginTop: '4px' }}>Start a new conversation to create one.</div>
                    </div>
                  )}
                  {sessionsList.map((s) => (
                    <div 
                      key={s.id} 
                      style={{ 
                        padding: '12px 16px',
                        borderBottom: '1px solid var(--border-subtle)',
                        background: s.id === currentSessionId ? 'rgba(214, 178, 106, 0.1)' : 'transparent',
                        cursor: 'pointer',
                        transition: 'background 0.15s ease'
                      }}
                      onClick={() => { setCurrentSession(s.id); setMenuOpen(false); }}
                      onMouseEnter={(e) => { if (s.id !== currentSessionId) e.currentTarget.style.background = 'rgba(0,0,0,0.02)'; }}
                      onMouseLeave={(e) => { if (s.id !== currentSessionId) e.currentTarget.style.background = 'transparent'; }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 500, fontSize: '13px', marginBottom: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {s.title}
                          </div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {new Date(s.updatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · {s.messages.length} messages
                          </div>
                        </div>
                        <button 
                          className="btn" 
                          onClick={(e) => handleDeleteSession(s.id, e)}
                          style={{ padding: '4px 8px', fontSize: '11px', opacity: 0.7 }}
                          title="Delete session"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="top-nav__center">
        {editing ? (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input className="top-nav__title-input" value={title} onChange={(e) => setTitle(e.target.value)} />
            <button className="btn" onClick={save}>Save</button>
            <button className="btn" onClick={() => { setEditing(false); setTitle(session?.title ?? ""); }}>Cancel</button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <div className="top-nav__title" onDoubleClick={() => setEditing(true)}>{session?.title ?? "RAG Assistant for Zotero"}</div>
            {session && <button className="btn" onClick={() => setEditing(true)} title="Edit session title">Edit</button>}
          </div>
        )}
      </div>

      <div className="top-nav__right">
        <button className="btn" onClick={() => navigate('/settings')} title="Settings">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <div style={{ width: 8 }} />
        <button className="btn" onClick={toggleRight} title={rightCollapsed ? "Show sources" : "Hide sources"}>
          <IconPanel>
            {rightCollapsed ? <path d="M15 6l-6 6 6 6" stroke="#5b4632" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/> : <path d="M9 6l6 6-6 6" stroke="#5b4632" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>}
          </IconPanel>
        </button>
      </div>
    </nav>
  );
};

export default TopNav;
