import { useState, useCallback, useRef } from "react";
import { chat as chatApi } from "../api/chat";
import type { ChatMessage } from "../types/domain";
import type { ChatResponse } from "../types/api";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  async function sendMessage(
    content: string,
    sessionId?: string,
    searchOptions?: {
      use_metadata_filters?: boolean;
      manual_filters?: {
        year_min?: number;
        year_max?: number;
        tags?: string[];
        collections?: string[];
      };
      use_rrf?: boolean;
      max_sources?: number;
      item_ids?: string[];
    }
  ): Promise<
    | { userMessage: ChatMessage; assistantMessage: ChatMessage; response: ChatResponse }
    | null
  > {
    if (!content.trim() || loading) return null;
    setError(null);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: content.trim(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    // Create new abort controller for this request
    abortControllerRef.current = new AbortController();

    try {
      const res = await chatApi({ 
        query: content.trim(),
        session_id: sessionId,
        ...searchOptions,
      }, abortControllerRef.current.signal);
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.summary,
      };
      // Not added to messages: the view reloads from the session the answer is saved to,
      // which may no longer be the one on screen.
      return { userMessage, assistantMessage, response: res };
    } catch (e) {
      // Don't show error if request was intentionally aborted
      if (!(e instanceof DOMException && e.name === 'AbortError')) {
        setError(e instanceof Error ? e.message : "Failed to get answer");
      }
      return null;
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setLoading(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, loading, error, sendMessage, stopGeneration, loadThread: setMessages, clearMessages };
}
