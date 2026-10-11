import { apiFetch, request } from "./client";
import type { AnnotateEvent, ChainResponse, DeskModel, SearchRequest, SearchResponse } from "../types/desk";

/** Reference desk search. A model reads the query only if the desk settings allow it; see POST /api/search. */
export function search(body: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export type AnnotateItem = {
  item_id: string;
  title: string;
  tags: string[];
  band: string;
  passages: { page: number | null; text: string }[];
};

/**
 * The clerk's notes, next searches and themes for a result list, delivered as each
 * one finishes (newline-delimited JSON). Aborting the signal stops the work.
 */
export async function annotate(
  body: { query: string; items: AnnotateItem[] },
  onEvent: (event: AnnotateEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch("/api/annotate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as AnnotateEvent);
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AnnotateEvent);
}

export function deskModel(): Promise<DeskModel> {
  return request<DeskModel>("/api/desk/model");
}

/** References and citing works for one item; sends its DOI or title to Semantic Scholar. */
export function chain(itemId: string, signal?: AbortSignal): Promise<ChainResponse> {
  return request<ChainResponse>("/api/desk/chain", { method: "POST", body: JSON.stringify({ item_id: itemId }), signal });
}
