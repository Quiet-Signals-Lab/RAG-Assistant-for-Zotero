import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { Session, Snippet, Source, Message } from "../types/session";
import { useProfile } from "./ProfileContext";
import { apiFetch } from "../api/client";


type SessionsShape = {
  sessions: Record<string, Session>;
  currentSessionId: string | null;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  leftActiveTab: string;
  setLeftActiveTab: (tab: string) => void;
  createSession: (
    initialUserQuestion: string,
    initialAnswer?: string,
    responseSources?: Source[],
    initialSources?: Source[],
    initialSnippets?: Snippet[],
    customTitle?: string,
    userMessageId?: string,
    assistantMessageId?: string,
    reasoning?: string
  ) => { sessionId: string; assistantMessageId: string };
  /** An empty session scoped to these items, made current; the first question fills it. */
  startSession: (title: string, itemIds: string[]) => string;
  appendMessage: (sessionId: string, message: Message) => void;
  updateSessionTitle: (sessionId: string, newTitle: string) => void;
  addSnippet: (sessionId: string, snippet: Snippet) => void;
  upsertSource: (sessionId: string, source: Source) => void;
  setCurrentSession: (id: string | null) => void;
  deleteSession: (id: string) => void;
  toggleLeft: () => void;
  toggleRight: () => void;
  getSession: (id: string) => Session | null;
};

const SessionsContext = createContext<SessionsShape | null>(null);

function nowISO() {
  return new Date().toISOString();
}

export const SessionsProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { activeProfileId, isLoading: profileLoading } = useProfile();
  const [sessions, setSessions] = useState<Record<string, Session>>({});
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [leftCollapsed, setLeftCollapsed] = useState<boolean>(false);
  const [rightCollapsed, setRightCollapsed] = useState<boolean>(false);
  const [leftActiveTab, setLeftActiveTab] = useState<string>(() => {
    return localStorage.getItem('leftActiveTab') || 'evidence';
  });
  const [isLoadingFromBackend, setIsLoadingFromBackend] = useState(false);

  const STORAGE_KEY = "zotero_llm_sessions_v1";

  // Persist active tab when it changes
  useEffect(() => {
    localStorage.setItem('leftActiveTab', leftActiveTab);
  }, [leftActiveTab]);

  // Load sessions from backend when profile becomes available
  useEffect(() => {
    if (profileLoading || !activeProfileId) {
      return;
    }

    const loadFromBackend = async () => {
      try {
        setIsLoadingFromBackend(true);
        console.log(`[SessionsContext] Loading sessions from backend for profile: ${activeProfileId}`);
        
        const response = await apiFetch(`/api/profiles/${activeProfileId}/sessions`);
        if (response.ok) {
          const data = await response.json();
          console.log(`[SessionsContext] Loaded sessions from backend:`, data);
          
          if (data.sessions) {
            setSessions(data.sessions);
          }
          if (data.currentSessionId && data.sessions && data.sessions[data.currentSessionId]) {
            setCurrentSessionId(data.currentSessionId);
          }
          if (typeof data.leftCollapsed === 'boolean') {
            setLeftCollapsed(data.leftCollapsed);
          }
          if (typeof data.rightCollapsed === 'boolean') {
            setRightCollapsed(data.rightCollapsed);
          }
        } else {
          console.warn('[SessionsContext] Failed to load sessions from backend, falling back to localStorage');
          loadFromLocalStorage();
        }
      } catch (err) {
        console.error('[SessionsContext] Error loading sessions from backend:', err);
        loadFromLocalStorage();
      } finally {
        setIsLoadingFromBackend(false);
      }
    };

    const loadFromLocalStorage = () => {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (parsed.sessions) setSessions(parsed.sessions);
        if (parsed.currentSessionId && parsed.sessions && parsed.sessions[parsed.currentSessionId]) {
          setCurrentSessionId(parsed.currentSessionId);
        }
        if (typeof parsed.leftCollapsed === "boolean") setLeftCollapsed(parsed.leftCollapsed);
        if (typeof parsed.rightCollapsed === "boolean") setRightCollapsed(parsed.rightCollapsed);
      } catch (e) {
        console.warn("Failed to load sessions from localStorage", e);
      }
    };

    loadFromBackend();
  }, [activeProfileId, profileLoading]);

  // Save to backend whenever sessions change (debounced)
  useEffect(() => {
    if (profileLoading || !activeProfileId || isLoadingFromBackend) {
      return;
    }

    const saveToBackend = async () => {
      try {
        const payload = { sessions, currentSessionId, leftCollapsed, rightCollapsed };
        console.log(`[SessionsContext] Saving sessions to backend for profile: ${activeProfileId}`);
        
        const response = await apiFetch(`/api/profiles/${activeProfileId}/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
          console.error('[SessionsContext] Failed to save sessions to backend');
        }
      } catch (err) {
        console.error('[SessionsContext] Error saving sessions to backend:', err);
      }
    };

    // Also save to localStorage as backup
    try {
      const payload = JSON.stringify({ sessions, currentSessionId, leftCollapsed, rightCollapsed });
      localStorage.setItem(STORAGE_KEY, payload);
    } catch (e) {
      console.warn("Failed to persist sessions to localStorage", e);
    }

    // Debounce backend saves to avoid too many requests
    const timeoutId = setTimeout(saveToBackend, 1000);
    return () => clearTimeout(timeoutId);
  }, [sessions, currentSessionId, leftCollapsed, rightCollapsed, activeProfileId, profileLoading, isLoadingFromBackend]);

  function createSession(
    initialUserQuestion: string, 
    initialAnswer = "", 
    responseSources: Source[] = [],
    initialSources: Source[] = [], 
    initialSnippets: Snippet[] = [], 
    customTitle?: string,
    userMessageId?: string,
    assistantMessageId?: string,
    reasoning?: string
  ): { sessionId: string; assistantMessageId: string } {
    const id = crypto.randomUUID();
    const createdAt = nowISO();
    const userMsgId = userMessageId ?? crypto.randomUUID();
    const assistantMsgId = assistantMessageId ?? crypto.randomUUID();
    const userMsg: Message = { 
      id: userMsgId, 
      role: "user", 
      content: initialUserQuestion, 
      createdAt 
    };
    const assistantMsg: Message = { 
      id: assistantMsgId, 
      role: "assistant", 
      content: initialAnswer, 
      createdAt,
      sources: responseSources,  // Attach sources to assistant message
      timestamp: Date.now(),
      reasoning  // Include reasoning if present
    };
    console.log("[SessionsContext] Creating assistant message with sources:", responseSources);
    console.log("[SessionsContext] Assistant message ID:", assistantMsgId);
    const title = customTitle || (initialUserQuestion || "New session").slice(0, 80);
    const s: Session = {
      id,
      title,
      createdAt,
      updatedAt: createdAt,
      messages: [userMsg, assistantMsg].filter(Boolean),
      snippets: initialSnippets || [],
      sources: initialSources || [],
    };
    setSessions((prev) => ({ ...prev, [id]: s }));
    setCurrentSessionId(id);
    return { sessionId: id, assistantMessageId: assistantMsgId };
  }

  function startSession(title: string, itemIds: string[]): string {
    const id = crypto.randomUUID();
    const createdAt = nowISO();
    setSessions((prev) => ({ ...prev, [id]: { id, title, createdAt, updatedAt: createdAt, messages: [], snippets: [], sources: [], itemIds } }));
    setCurrentSessionId(id);
    return id;
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

  function addSnippet(sessionId: string, snippet: Snippet) {
    setSessions((prev) => {
      const s = prev[sessionId];
      if (!s) return prev;
      const exists = s.snippets.find((x) => x.id === snippet.id);
      const updated = {
        ...s,
        snippets: exists ? s.snippets.map((x) => (x.id === snippet.id ? snippet : x)) : [...s.snippets, snippet],
        updatedAt: nowISO(),
      };
      return { ...prev, [sessionId]: updated };
    });
  }

  function upsertSource(sessionId: string, source: Source) {
    setSessions((prev) => {
      const s = prev[sessionId];
      if (!s) return prev;
      const exists = s.sources.find((x) => x.documentId === source.documentId);
      const updated = {
        ...s,
        sources: exists ? s.sources.map((x) => (x.documentId === source.documentId ? { ...x, ...source } : x)) : [...s.sources, source],
        updatedAt: nowISO(),
      };
      return { ...prev, [sessionId]: updated };
    });
  }

  function setCurrentSession(id: string | null) {
    setCurrentSessionId(id);
  }

  function toggleLeft() {
    setLeftCollapsed((p) => !p);
  }

  function toggleRight() {
    setRightCollapsed((p) => !p);
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
        leftCollapsed,
        rightCollapsed,
        leftActiveTab,
        setLeftActiveTab,
        createSession,
        startSession,
        appendMessage,
        updateSessionTitle,
        addSnippet,
        upsertSource,
        setCurrentSession,
        deleteSession,
        toggleLeft,
        toggleRight,
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
