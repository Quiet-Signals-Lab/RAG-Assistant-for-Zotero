export interface Citation {
  id: string;
  title: string;
  authors?: string;
  year?: number;
  pdf_path?: string;
}

export interface Snippet {
  id: string;
  citation_id?: number;
  item_id?: string;
  snippet: string; // The actual text chunk from the document
  text?: string; // Alias for backward compatibility
  title: string;
  authors?: string;
  year?: string | number;
  page?: number | string;
  zoteroKey?: string;
  pdf_path?: string;
  confidence?: number; // Relevance score (0-1)
  context?: string; // Full paragraph containing the snippet
}

export interface ChatResponse {
  summary: string;
  citations: Citation[];
  snippets: Snippet[];
  generated_title?: string;
  reasoning?: string; // Optional AI reasoning steps (e.g., from <think> tags)
}

export interface ChatRequest {
  query: string;
  session_id?: string;
  use_metadata_filters?: boolean;
  manual_filters?: {
    year_min?: number;
    year_max?: number;
    tags?: string[];
    collections?: string[];
    title?: string;
    author?: string;
    item_types?: string[];
  };
  use_rrf?: boolean;
  max_sources?: number;
}
