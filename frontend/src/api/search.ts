import { request } from "./client";
import type { SearchRequest, SearchResponse } from "../types/desk";

/** Reference desk search. No model is called; see POST /api/search. */
export function search(body: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}
