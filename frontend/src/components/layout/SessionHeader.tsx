import React, { useEffect, useState } from "react";
import { useSessions } from "../../contexts/SessionsContext";

const SessionHeader: React.FC = () => {
  const { currentSessionId, getSession, updateSessionTitle } = useSessions();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session?.title ?? "");

  useEffect(() => {
    setTitle(session?.title ?? "");
    if (session) document.title = session.title || "RAG Assistant for Zotero";
  }, [session]);

  function save() {
    if (!currentSessionId) return;
    updateSessionTitle(currentSessionId, title.trim() || "Untitled session");
    setEditing(false);
  }

  if (!session) {
    return (
      <div style={{ padding: "12px 16px" }}>
        <div className="app-heading">RAG Assistant for Zotero</div>
        <div className="muted">Start a new session by asking a question.</div>
      </div>
    );
  }

  return (
    <div style={{ padding: "12px 16px", display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {editing ? (
          <div style={{ display: "flex", gap: 8 }}>
            <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ fontSize: 18, padding: 6 }} />
            <button className="btn" onClick={save}>Save</button>
            <button className="btn" onClick={() => { setEditing(false); setTitle(session.title); }}>Cancel</button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <div style={{ fontFamily: "var(--font-serif)", fontSize: 18 }}>{session.title}</div>
            <button className="btn" onClick={() => setEditing(true)}>Edit</button>
          </div>
        )}
        <div className="muted" style={{ marginTop: 6 }}>{new Date(session.updatedAt).toLocaleString()}</div>
      </div>
    </div>
  );
};

export default SessionHeader;
