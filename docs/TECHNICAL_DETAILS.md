# Technical Details

## System Architecture

The application implements a multi-stage retrieval pipeline designed for academic research workflows. The backend uses FastAPI with ChromaDB for vector storage, while the frontend is built with React and TypeScript. The desktop application uses Electron with auto-update capabilities.

## Retrieval Pipeline

**Query Processing.** For multi-turn conversations, the system rewrites follow-up questions into standalone queries before retrieval. This ensures that questions containing pronouns or contextual references can be properly matched against the document corpus without relying on conversation history.

**Hybrid Search.** The system combines dense vector search (using sentence transformer embeddings) with sparse BM25 keyword search. Both result sets are merged using Reciprocal Rank Fusion, which scores each document based on its rankings from both retrieval methods. This approach captures both semantic similarity and exact keyword matches, improving recall for queries that contain specific terminology or proper nouns.

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

PDFs are extracted with page-level granularity, preserving page numbers throughout the chunking process. Text is split into approximately 800-character chunks with 200-character overlap, using sentence boundaries to avoid mid-sentence cuts. Each chunk stores metadata including item ID, title, authors, year, tags, collections, item type, PDF path, and page number, enabling both filtering and citation generation.

## Implementation Notes

The system implements provider-aware dynamic retrieval limits that automatically scale based on the active model's context window. Models with larger contexts retrieve more evidence: Gemini 1.5 Pro (2M tokens) retrieves 30-50 snippets, Claude Opus (200k tokens) retrieves 24-40 snippets, while local models without known context limits use conservative defaults (6-10 snippets). The scaling uses five tiers (1.0x, 2.0x, 3.0x, 4.0x, 5.0x) and preserves the broad/focused mode distinction for diversity control.

**Privacy:**
Indexing and retrieval happen on your device — your PDFs are indexed by your CPU on first launch and stored in a local database. With a local model (LM Studio or Ollama) the app runs fully offline. If you opt for a cloud provider, the only data shared is your query, the retrieved text chunks, and earlier responses from the same session — your full library never leaves your machine. To shield specific material entirely, you can exclude Zotero collections and tags from the index so they are never sent to a third party.
