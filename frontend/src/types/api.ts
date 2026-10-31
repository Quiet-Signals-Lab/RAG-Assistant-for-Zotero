export interface Citation {
  id: number; // the [N] in the answer's text
  title: string;
  authors?: string;
  year?: string | number;
  pdf_path?: string;
}

export interface Snippet {
  citation_id: number;
  snippet: string; // The actual text chunk from the document
  title: string;
  authors?: string;
  year?: string | number;
  page?: number | null;
  pdf_path?: string;
}

export interface ChatResponse {
  summary: string;
  citations: Citation[];
  snippets: Snippet[];
  generated_title?: string | null;
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
  item_ids?: string[];
}
