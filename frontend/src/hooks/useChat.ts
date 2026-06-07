import { useState, useCallback, useRef } from "react";
import { chat as chatApi } from "../api/chat";
import type { ChatMessage } from "../types/domain";
import type { ChatResponse } from "../types/api";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
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
        citations: res.citations,
        reasoning: res.reasoning, // Include reasoning if present
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setLastResponse(res);
      return { userMessage, assistantMessage, response: res };
    } catch (e: any) {
      // Don't show error if request was intentionally aborted
      if (e.name !== 'AbortError') {
        setError(e.message ?? "Failed to get answer");
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

  const loadThread = useCallback((thread: { id: string; title?: string; messages: ChatMessage[]; lastResponse?: ChatResponse }) => {
    if (!thread) return;
    setMessages(thread.messages || []);
    if (thread.lastResponse) setLastResponse(thread.lastResponse);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setLastResponse(null);
    setError(null);
  }, []);

  return { messages, loading, error, lastResponse, sendMessage, stopGeneration, loadThread, clearMessages };
}
