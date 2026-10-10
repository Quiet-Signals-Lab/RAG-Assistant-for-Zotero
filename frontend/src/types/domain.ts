import type { Citation, ChatResponse } from "./api";

export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  citations?: Citation[];
  reasoning?: string; // Optional AI reasoning content
}

export interface ConversationState {
  messages: ChatMessage[];
  lastResponse: ChatResponse | null;
}
