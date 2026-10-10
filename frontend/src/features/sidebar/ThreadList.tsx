import React, { useState, useEffect } from "react";
import type { ChatMessage } from "../../types/domain";
import { useChatContext } from "../../contexts/ChatContext";

type Thread = {
  id: string;
  title?: string;
  messages: ChatMessage[];
  lastResponse?: any;
  createdAt: string;
};

const STORAGE_KEY = "zotero_llm_threads";

function readThreads(): Thread[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function writeThreads(ts: Thread[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ts));
  } catch {
    // ignore
  }
}

const ThreadList: React.FC = () => {
  const { messages, lastResponse, loadThread } = useChatContext();
  const [threads, setThreads] = useState<Thread[]>([]);

  useEffect(() => {
    setThreads(readThreads());
  }, []);

  function saveCurrent() {
    const id = crypto.randomUUID();
    const t: Thread = {
      id,
      title: messages.length ? messages[0].content.slice(0, 40) : "Conversation",
      messages,
      lastResponse: lastResponse as any,
      createdAt: new Date().toISOString(),
    };
    const next = [t, ...threads].slice(0, 25);
    setThreads(next);
    writeThreads(next);
  }

  function load(t: Thread) {
    loadThread({ id: t.id, title: t.title, messages: t.messages, lastResponse: t.lastResponse });
  }

  function remove(id: string) {
    const next = threads.filter((t) => t.id !== id);
    setThreads(next);
    writeThreads(next);
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="app-heading">Threads</div>
        <button className="btn" onClick={saveCurrent} disabled={!messages.length}>
          Save
        </button>
      </div>
      <div style={{ marginTop: 8 }}>
        {threads.length === 0 && <div className="muted">No saved threads yet.</div>}
        <ul style={{ marginTop: 8 }}>
          {threads.map((t) => (
            <li key={t.id} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <div>
                  <strong>{t.title}</strong>
                  <div className="muted" style={{ fontSize: 12 }}>{new Date(t.createdAt).toLocaleString()}</div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn" onClick={() => load(t)}>Load</button>
                  <button className="btn" onClick={() => remove(t.id)}>Delete</button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default ThreadList;
