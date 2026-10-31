export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  reasoning?: string; // Optional AI reasoning content
}
