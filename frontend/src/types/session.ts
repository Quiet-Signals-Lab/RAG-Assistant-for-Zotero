export type Snippet = {
  id: string;
  text: string;
  context: string;
  confidence: number;
  pageNumber?: number;
  section?: string;
  characterOffset?: number;
};

export type Source = {
  documentId: string;
  title: string;
  author: string;
  year?: string | number;
  confidence: number;
  pageNumber?: number;
  section?: string;
  retrievalTimestamp: number;
  snippets: Snippet[];
  // Legacy fields for backward compatibility
  zoteroKey?: string;
  localPdfPath?: string;
  authors?: string; // Backward compatibility with full authors list
};

// Legacy type alias for backward compatibility
export type SourceRef = Source;

export type Message = { 
  id: string; 
  role: "user" | "assistant"; 
  content: string; 
  createdAt: string;
  sources?: Source[];  // Response-scoped sources
  timestamp?: number;  // When response was generated
  reasoning?: string;  // Optional AI reasoning steps
};

export type Session = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: Message[];
  snippets: Snippet[];
  sources: SourceRef[];
  /** Zotero item ids the chat answers from, when opened from search. */
  itemIds?: string[];
};
