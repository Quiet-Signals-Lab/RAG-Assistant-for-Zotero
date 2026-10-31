import React, { createContext, useContext, useEffect } from "react";
import type { ChatMessage } from "../types/domain";
import { useChat as useChatHook } from "../hooks/useChat";
import { useSessions } from "./SessionsContext";
import { useDesk } from "../features/desk/DeskContext";
import { sourcesFromResponse } from "../features/chat/sources";
import { useResponseSelection } from "./ResponseSelectionContext";
import { useSearchSettings } from "./SearchSettingsContext";
import { useSettings } from "./SettingsContext";
import { useNotifications } from "../hooks/useNotifications";
import type { Message as SessionMessage } from "../types/session";

type ChatContextShape = {
  messages: ChatMessage[];
  loading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => void;
  clearMessages: () => void;
};

const ChatContext = createContext<ChatContextShape | null>(null);

/** The item ids attached in the context folder, or undefined when none are. */
export function attachedContextIds(context: { itemId: string; attached: boolean }[]): string[] | undefined {
  const ids = [...new Set(context.filter((c) => c.attached).map((c) => c.itemId))];
  return ids.length ? ids : undefined;
}

export const ChatProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const { messages, loading, error, sendMessage: rawSendMessage, stopGeneration, loadThread, clearMessages } = useChatHook();
  const desk = useDesk();
  const sessions = useSessions();
  const { setSelectedResponseId } = useResponseSelection();
  const { searchSettings } = useSearchSettings();
  const { settings } = useSettings();
  const { notifyResponse } = useNotifications();

  const currentId = sessions.currentSessionId;
  const stored = currentId ? sessions.getSession(currentId)?.messages : undefined;

  // Follows this session's messages only: a rename, or a change to another session,
  // must not drop a question still waiting for its answer.
  useEffect(() => {
    if (stored?.length) loadThread(stored);
    else clearMessages();
  }, [currentId, stored, loadThread, clearMessages]);

  async function sendMessage(content: string) {
    const session = currentId ? sessions.getSession(currentId) : null;
    // A new chat has its id before its first question, or the backend keeps no memory of that turn.
    const sessionId = currentId ?? crypto.randomUUID();
    
    // Build search options from search settings
    const searchOptions = {
      use_metadata_filters: searchSettings.searchEngineMode === 'metadata-aware' && searchSettings.filterMode === 'auto',
      manual_filters: searchSettings.searchEngineMode === 'metadata-aware' && searchSettings.filterMode === 'manual'
        ? {
            year_min: searchSettings.manualFilters.yearMin,
            year_max: searchSettings.manualFilters.yearMax,
            tags: searchSettings.manualFilters.tags,
            collections: searchSettings.manualFilters.collections,
            title: searchSettings.manualFilters.title,
            author: searchSettings.manualFilters.author,
            item_types: searchSettings.manualFilters.itemTypes,
          }
        : undefined,
      use_rrf: searchSettings.useRRF,
      max_sources: settings.maxSources || 0,
      // Attached context items scope the answer; a session opened on chosen items keeps its own scope otherwise.
      item_ids: attachedContextIds(desk.context) ?? session?.itemIds,
    };
    
    // send via the chat hook, which returns created messages and the response
    const result = await rawSendMessage(content, sessionId, searchOptions);
    if (!result) return;

    const { userMessage, assistantMessage, response } = result;
    const sources = sourcesFromResponse(response);

    if (!session) {
      // A title from the model only ever comes with the first answer.
      sessions.createSession(
        sessionId,
        userMessage.content,
        response.summary,
        sources,
        response.generated_title ?? undefined,
        userMessage.id,
        assistantMessage.id,
        response.reasoning
      );
    } else {
      const createdAt = new Date().toISOString();
      sessions.appendMessage(sessionId, { id: userMessage.id, role: "user", content: userMessage.content, createdAt });
      const answer: SessionMessage = {
        id: assistantMessage.id,
        role: "assistant",
        content: response.summary,
        createdAt,
        sources,
        timestamp: Date.now(),
        reasoning: response.reasoning,
      };
      sessions.appendMessage(sessionId, answer);
    }

    setSelectedResponseId(assistantMessage.id);

    // Notify user that response is ready
    notifyResponse(response.summary);
  }

  return (
    <ChatContext.Provider value={{ messages, loading, error, sendMessage, stopGeneration, clearMessages }}>
      {children}
    </ChatContext.Provider>
  );
};

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext must be used within ChatProvider");
  return ctx;
}

export default ChatContext;
