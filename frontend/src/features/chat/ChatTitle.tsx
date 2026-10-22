import React, { useEffect, useState } from "react";
import { useSessions } from "../../contexts/SessionsContext";

/** The session's title, centred above the conversation; click to rename. */
const ChatTitle: React.FC = () => {
  const { currentSessionId, getSession, updateSessionTitle } = useSessions();
  const session = currentSessionId ? getSession(currentSessionId) : null;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session?.title ?? "");

  useEffect(() => {
    setTitle(session?.title ?? "");
  }, [session]);

  function save() {
    if (currentSessionId) updateSessionTitle(currentSessionId, title.trim() || "Untitled session");
    setEditing(false);
  }

  return (
    <div className="chat-view__head">
      {editing ? (
        <form className="chat-title__edit" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <label htmlFor="session-title" className="sr-only">Session title</label>
          <input id="session-title" className="chat-title__input" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
          <button type="submit" className="btn">Save</button>
          <button type="button" className="btn" onClick={() => { setEditing(false); setTitle(session?.title ?? ""); }}>Cancel</button>
        </form>
      ) : session ? (
        <button type="button" className="chat-title" onClick={() => setEditing(true)} title="Rename this session">
          {session.title}
        </button>
      ) : (
        <span className="chat-title chat-title--quiet">New session</span>
      )}
    </div>
  );
};

export default ChatTitle;
