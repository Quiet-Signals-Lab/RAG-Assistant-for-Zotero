import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import type { Session, Source, Message } from "../types/session";
import { useProfile } from "./ProfileContext";
import { apiFetch, BACKEND_BACK } from "../api/client";


type SessionsShape = {
  sessions: Record<string, Session>;
  currentSessionId: string | null;
  /** The saved sessions could not be read, so nothing is being written. */
  loadFailed: boolean;
  createSession: (
    sessionId: string,
    initialUserQuestion: string,
    initialAnswer?: string,
    responseSources?: Source[],
    customTitle?: string,
    userMessageId?: string,
    assistantMessageId?: string,
    reasoning?: string
  ) => void;
  appendMessage: (sessionId: string, message: Message) => void;
  updateSessionTitle: (sessionId: string, newTitle: string) => void;
  setCurrentSession: (id: string | null) => void;
  deleteSession: (id: string) => void;
  getSession: (id: string) => Session | null;
};

const SessionsContext = createContext<SessionsShape | null>(null);

/** Per profile: a shared backup would pour one profile's sessions into another after a failed load. */
function backupKey(profileId: string) {
  return `zotero_llm_sessions_v1:${profileId}`;
}

function nowISO() {
  return new Date().toISOString();
}

export const SessionsProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { activeProfileId, isLoading: profileLoading } = useProfile();
  const [sessions, setSessions] = useState<Record<string, Session>>({});
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  // Starts true and stays true after a failed load: a failed read must never be followed by a write.
  const [isLoadingFromBackend, setIsLoadingFromBackend] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const saved = useRef<string | null>(null); // the save payload the backend already holds

  // Load sessions from backend when profile becomes available
  useEffect(() => {
    if (profileLoading || !activeProfileId) {
      return;
    }

    const loadFromBackend = async () => {
      try {
        setIsLoadingFromBackend(true);
        const response = await apiFetch(`/api/profiles/${activeProfileId}/sessions`);
        const data = await response.json();
        const loaded: Record<string, Session> = data.sessions ?? {};
        const current = data.currentSessionId && loaded[data.currentSessionId] ? data.currentSessionId : null;

        saved.current = JSON.stringify({ sessions: loaded, currentSessionId: current });
        // A retry keeps sessions started while the backend was away; the backend's copy of the rest wins.
        setSessions((prev) => (loadAttempt ? { ...prev, ...loaded } : loaded));
        setCurrentSessionId((prev) => (loadAttempt ? prev ?? current : current));
        setLoadFailed(false);
        setIsLoadingFromBackend(false);
      } catch (err) {
        console.error('[SessionsContext] Error loading sessions from backend:', err);
        loadFromLocalStorage();
        setLoadFailed(true);
      }
    };

    const loadFromLocalStorage = () => {
      try {
        const raw = localStorage.getItem(backupKey(activeProfileId));
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (parsed.sessions) setSessions(parsed.sessions);
        if (parsed.currentSessionId && parsed.sessions && parsed.sessions[parsed.currentSessionId]) {
          setCurrentSessionId(parsed.currentSessionId);
        }
      } catch (e) {
        console.warn("Failed to load sessions from localStorage", e);
      }
    };

    loadFromBackend();
  }, [activeProfileId, profileLoading, loadAttempt]);

  // A failed load tries again once the backend answers.
  useEffect(() => {
    if (!loadFailed) return;
    const retry = () => setLoadAttempt((n) => n + 1);
    window.addEventListener(BACKEND_BACK, retry);
    return () => window.removeEventListener(BACKEND_BACK, retry);
  }, [loadFailed]);

  // Save to backend whenever sessions change (debounced)
  useEffect(() => {
    if (profileLoading || !activeProfileId || isLoadingFromBackend) {
      return;
    }

    const payload = JSON.stringify({ sessions, currentSessionId });
    if (payload === saved.current) return;

    const saveToBackend = async () => {
      try {
        await apiFetch(`/api/profiles/${activeProfileId}/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload
        });
        saved.current = payload;
      } catch (err) {
        console.error('[SessionsContext] Error saving sessions to backend:', err);
      }
    };

    // Also save to localStorage as backup
    try {
      localStorage.setItem(backupKey(activeProfileId), payload);
    } catch (e) {
      console.warn("Failed to persist sessions to localStorage", e);
    }

    // Debounce backend saves to avoid too many requests
    const timeoutId = setTimeout(saveToBackend, 1000);
    return () => clearTimeout(timeoutId);
  }, [sessions, currentSessionId, activeProfileId, profileLoading, isLoadingFromBackend]);

  function createSession(
    sessionId: string,
    initialUserQuestion: string, 
    initialAnswer = "", 
    responseSources: Source[] = [],
    customTitle?: string,
    userMessageId?: string,
    assistantMessageId?: string,
    reasoning?: string
  ) {
    const createdAt = nowISO();
    const userMsg: Message = { 
      id: userMessageId ?? crypto.randomUUID(), 
      role: "user", 
      content: initialUserQuestion, 
      createdAt 
    };
    const assistantMsg: Message = { 
      id: assistantMessageId ?? crypto.randomUUID(), 
      role: "assistant", 
      content: initialAnswer, 
      createdAt,
      sources: responseSources,  // Attach sources to assistant message
      timestamp: Date.now(),
      reasoning  // Include reasoning if present
    };
    const title = customTitle || (initialUserQuestion || "New session").slice(0, 80);
    const s: Session = {
      id: sessionId,
      title,
      createdAt,
      updatedAt: createdAt,
      messages: [userMsg, assistantMsg],
    };
    setSessions((prev) => ({ ...prev, [sessionId]: s }));
    // Whoever opened another session while this answer was on its way stays there.
    setCurrentSessionId((current) => current ?? sessionId);
  }

  function appendMessage(sessionId: string, message: Message) {
    setSessions((prev) => {
      const s = prev[sessionId];
      if (!s) return prev;
      const updated = { ...s, messages: [...s.messages, message], updatedAt: nowISO() };
      return { ...prev, [sessionId]: updated };
    });
  }

  function updateSessionTitle(sessionId: string, newTitle: string) {
    setSessions((prev) => {
      const s = prev[sessionId];
      if (!s) return prev;
      const updated = { ...s, title: newTitle, updatedAt: nowISO() };
      return { ...prev, [sessionId]: updated };
    });
  }

  function setCurrentSession(id: string | null) {
    setCurrentSessionId(id);
  }

  const getSession = useCallback((id: string) => {
    return sessions[id] ?? null;
  }, [sessions]);

  function deleteSession(id: string) {
    setSessions((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    // If deleting current session, clear it
    if (currentSessionId === id) {
      setCurrentSessionId(null);
    }
  }

  return (
    <SessionsContext.Provider
      value={{
        sessions,
        currentSessionId,
        loadFailed,
        createSession,
        appendMessage,
        updateSessionTitle,
        setCurrentSession,
        deleteSession,
        getSession,
      }}
    >
      {children}
    </SessionsContext.Provider>
  );
};

export function useSessions() {
  const ctx = useContext(SessionsContext);
  if (!ctx) throw new Error("useSessions must be used within SessionsProvider");
  return ctx;
}

export default SessionsContext;
