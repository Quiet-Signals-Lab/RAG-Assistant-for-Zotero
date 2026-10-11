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
  /** Phrases ruled out ("not medical imaging"): passages that mention them are dropped. */
  exclude?: string[];
}

export interface SearchRequest {
  query: string;
  manual_filters?: ScopeFilters;
  use_metadata_filters?: boolean;
  item_ids?: string[];
  /** Items set aside: the source of "more like this", or rows the reader has already seen. */
  exclude_item_ids?: string[];
}

export interface SearchResponse {
  query: string;
  scope: {
    manual: ScopeFilters;
    extracted: ScopeFilters;
    extracted_ignored: boolean;
    /** What was searched for: the query without the limits read from it. */
    topic: string;
    /** Who read the limits: the clerk (a model), the library reader (no model), or nobody (reading off). */
    read_by: "model" | "library" | null;
    read_reason: string;
  };
  known_items: KnownItem[];
  items: DeskItem[];
  see_also_count: number;
  timing_ms: { read?: number; retrieve: number; total: number };
}

/** The clerk's work on a result list, streamed by POST /api/annotate (backend/clerk_jobs.py). */
export interface ClerkNote {
  /** One indicative sentence, checked against the item's passages. */
  note: string;
  page: number | null;
  support: number;
}

export type Relation = "broader" | "narrower" | "related";

export interface Suggestion {
  term: string;
  relation: Relation;
}

export interface Theme {
  label: string;
  item_ids: string[];
}

export type AnnotateEvent =
  | ({ type: "note"; item_id: string } & ClerkNote)
  | { type: "also_try"; suggestions: Suggestion[]; source: "model" | "fallback" }
  | { type: "themes"; groups: Theme[]; source: "model" | "fallback" }
  | { type: "done"; model: string; ms: number; counts: { model: number; fallback: number; reasons: Record<string, number> } };

/** GET /api/desk/model: the model the clerk would use and the desk's own measurements of it. */
export interface DeskModel {
  available: boolean;
  model: string;
  /** The model is a cloud service; the clerk uses it only when cloud_allowed. */
  cloud: boolean;
  cloud_allowed: boolean;
  measured: {
    label: string;
    measured: string;
    hardware: string;
    results: Record<string, Record<string, unknown>>;
  } | null;
  jobs: { read_query: boolean; notes: boolean; also_try: boolean; themes: boolean };
}

/** POST /api/desk/chain: an item's references and citing works from Semantic Scholar. */
export interface ChainEntry {
  title: string;
  year: number | null;
  authors: string[];
  doi: string | null;
  url: string;
  /** The reader's own copy in Zotero, matched by DOI or exact title. */
  owned_item_id: string | null;
  citation: Citation | null;
}

export interface ChainResponse {
  found: boolean;
  url?: string;
  references?: ChainEntry[];
  cited_by?: ChainEntry[];
}
