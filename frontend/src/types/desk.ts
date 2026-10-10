/** Shapes returned by POST /api/search (backend/interface.py ZoteroChatbot.search). */

export type Band = "strong" | "good" | "weak" | "see_also";
export type Span = [number, number];

export interface Creator {
  first: string;
  last: string;
  role: string;
}

export interface Citation {
  item_id: string;
  item_key: string;
  item_type: string;
  group_id: number | null;
  pdf_key: string | null;
  creators: Creator[];
  title: string;
  short_title: string;
  date: string;
  year: number | null;
  container: string;
  volume: string;
  issue: string;
  pages: string;
  publisher: string;
  place: string;
  edition: string;
  report_number: string;
  thesis_type: string;
  doi: string;
  isbn: string;
  url: string;
}

export interface Passage {
  text: string;
  page: number | null;
  score: number;
  band: Band;
  highlights: Span[];
}

export interface Extract {
  text: string;
  page: number | null;
  highlights: Span[];
}

export interface DeskItem {
  item_id: string;
  rank: number;
  score: number;
  band: Band;
  title: string;
  authors: string;
  year: number | null;
  item_type: string;
  tags: string[];
  collections: string[];
  pdf_path: string;
  pages: number[];
  extract: Extract;
  passages: Passage[];
  /** Other Zotero items that are the same work (same title, year and authors). */
  duplicates: string[];
  citation: Citation | null;
}

export interface KnownItem {
  item_id: string;
  kind: "doi" | "isbn" | "arxiv" | "title" | "author_year";
  indexed: boolean;
  citation: Citation | null;
}

export interface ScopeFilters {
  year_min?: number;
  year_max?: number;
  tags?: string[];
  collections?: string[];
  item_types?: string[];
  author?: string;
  title?: string;
}

export interface SearchRequest {
  query: string;
  manual_filters?: ScopeFilters;
  use_metadata_filters?: boolean;
  item_ids?: string[];
}

export interface SearchResponse {
  query: string;
  scope: {
    manual: ScopeFilters;
    extracted: ScopeFilters;
    extracted_ignored: boolean;
  };
  known_items: KnownItem[];
  items: DeskItem[];
  see_also_count: number;
  timing_ms: { retrieve: number; total: number };
}
