import type { ChatResponse } from "../../types/api";
import type { Source } from "../../types/session";

/**
 * A response's citations as the answer's sources, each with its passages.
 * documentId is the backend's number, the [N] the answer's text uses: it holds
 * across a session, so a turn's sources need not run 1, 2, 3.
 */
export function sourcesFromResponse({ citations, snippets }: Pick<ChatResponse, "citations" | "snippets">): Source[] {
  const retrievalTimestamp = Date.now();
  return citations.map((citation, index) => ({
    documentId: String(citation.id),
    title: citation.title,
    author: citation.authors || "Unknown",
    year: citation.year || undefined,
    confidence: Math.max(0.5, Math.min(1.0, 0.95 - index * 0.05)), // earlier = higher
    retrievalTimestamp,
    localPdfPath: citation.pdf_path || undefined,
    authors: citation.authors,
    snippets: snippets
      .filter((s) => s.citation_id === citation.id)
      .map((s, i) => ({
        id: crypto.randomUUID(),
        text: s.snippet,
        context: s.snippet,
        confidence: Math.max(0.5, 0.95 - i * 0.03),
        pageNumber: s.page ?? undefined,
      })),
  }));
}
