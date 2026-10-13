# Technical Details

## System Architecture

The application implements a multi-stage retrieval pipeline designed for academic research workflows. The backend uses FastAPI with ChromaDB for vector storage, while the frontend is built with React and TypeScript. The desktop application uses Electron with auto-update capabilities.

## Retrieval Pipeline

**Query Processing.** For multi-turn conversations, the system rewrites follow-up questions into standalone queries before retrieval. This ensures that questions containing pronouns or contextual references can be properly matched against the document corpus without relying on conversation history.

**Hybrid Search.** The system combines dense vector search (using sentence transformer embeddings) with sparse BM25 keyword search. The keyword index is a SQLite FTS5 table stored next to the ChromaDB database, one per embedding model; the same file holds each passage's text and one metadata row per item, so scope filters and counts never walk chunks, and ChromaDB holds only vectors and per-chunk metadata (given the text as well, it indexed it twice more and that was most of its file). The two stores are updated as items are indexed or removed and reconciled if they ever disagree, so no in-memory index is built or loaded regardless of library size. Both result sets are merged using Reciprocal Rank Fusion, which scores each document based on its rankings from both retrieval methods. This approach captures both semantic similarity and exact keyword matches, improving recall for queries that contain specific terminology or proper nouns.

**Cross-Encoder Reranking.** After initial retrieval, candidates are reranked using a cross-encoder model that processes the query and each document together. This provides more accurate relevance scoring than the initial bi-encoder embeddings, which encode queries and documents independently.

**Diversity Controls.** The final selection enforces per-document limits to prevent a single highly-relevant paper from dominating the context window. The system uses two modes: focused queries (with active filters or results concentrated in few papers) allow up to 8 snippets per paper with 10 total snippets, while broad queries cap at 3 snippets per paper with 6 total snippets.

## Metadata Filtering

The system supports two-tier metadata filtering. The first tier uses an LLM to extract structured filters from natural language queries, automatically detecting constraints on year ranges, tags, collections, item types, authors, and titles. If auto-extracted filters return no results, the system retries without filters to avoid over-restriction from misinterpretation. The second tier allows manual filter specification through the user interface.

Filter processing uses a hybrid approach due to ChromaDB's operator limitations. Numeric and equality filters run during vector search, while substring operators for tags, collections, authors, and titles are applied client-side after retrieval.

## Conversation Management

The system maintains stateful conversation sessions with distinct handling for initial and follow-up turns. The first message in a session embeds retrieved evidence directly in the user message, while subsequent messages contain only the question itself, relying on conversation history for context. This prevents redundant context accumulation and manages token budgets more efficiently. Session messages are trimmed based on the active provider's context window, keeping the most recent exchanges while ensuring the conversation fits within model limits.

## Multi-Provider Support

The application integrates with eight LLM providers through a unified interface: Ollama and LM Studio for local inference, and OpenAI, Anthropic, Google, Mistral, Groq, and OpenRouter for cloud-based models. Cloud providers with dynamic model catalogs automatically discover available models during credential validation. Provider-specific error handling distinguishes between rate limits, authentication failures, and context length errors, providing targeted user feedback for each case.

## Embedding Models

Multiple embedding models are supported, each creating a separate ChromaDB collection to avoid dimension mismatch errors. Available models include BGE-base (768 dimensions, general-purpose), SPECTER (768 dimensions, optimized for scientific documents), MiniLM-L6 (384 dimensions, balanced speed and quality), and MiniLM-L3 (384 dimensions, fastest). The default model is BGE-base. Users can switch between models without re-indexing if the corresponding collection already exists.

## Document Processing

PDFs are read page by page with their layout (`backend/pdf.py`): hyphenated line breaks are joined and ligatures expanded, rotated stamps and boilerplate lines are dropped, and short lines that recur across pages (running headers, footers, page numbers) are removed. Headings are recognised from font size and weight, so every passage knows its section.

Chunking (`backend/chunking.py`) packs whole sentences within a section to about 1,100 characters (hard cap 1,600 for runs with no sentence breaks, such as tables), with no overlap; a chunk may cross a page break and records the page it starts on. Reference lists (by heading or by citation density) and number-only tables are not indexed. The embedding and the reranker see each passage with a context header naming the work, first author, year and section; the stored text, which the desk shows, does not. Each chunk stores item ID, item key, title, authors, year, tags, collections, item type, PDF path, page and section. Changing the pipeline does not break an existing index; a full reindex applies it to items indexed earlier.

The effect of a pipeline change is measured with `scripts/eval_retrieval.py` against a test set in the profile folder, before and after, on a copy of the index.

## Implementation Notes

The system implements provider-aware dynamic retrieval limits that automatically scale based on the active model's context window. Models with larger contexts retrieve more evidence: Gemini 1.5 Pro (2M tokens) retrieves 30-50 snippets, Claude Opus (200k tokens) retrieves 24-40 snippets, while local models without known context limits use conservative defaults (6-10 snippets). The scaling uses five tiers (1.0x, 2.0x, 3.0x, 4.0x, 5.0x) and preserves the broad/focused mode distinction for diversity control.

**Memory:** No operation loads the whole vector store into memory. Item inventories, filter counts, deletes and the metadata migration page through ChromaDB, and adds are split to the batch size the database reports, so libraries of millions of chunks index and query within a bounded footprint.

**Logging:** The backend writes to standard output through Python's logging module. The desktop app appends that output to `logs/backend.log` under its user data folder (`~/Library/Application Support/RAG Assistant` on macOS, `%APPDATA%\RAG Assistant` on Windows, `~/.config/rag-assistant` on Linux), keeping one previous generation once the file passes 10 MB. API failures are returned as HTTP 4xx/5xx responses with a `detail` message.

**Privacy:**
Indexing and retrieval happen on your device — your PDFs are indexed by your CPU on first launch and stored in a local database. With a local model (LM Studio or Ollama) the app runs fully offline. If you opt for a cloud provider, the only data shared is your query, the retrieved text chunks, and earlier responses from the same session — your full library never leaves your machine. To shield specific material entirely, you can exclude Zotero collections and tags from the index so they are never sent to a third party.
