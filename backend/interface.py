# interface.py

from backend.zotero_dbase import ZoteroLibrary
from backend.zoteroitem import ZoteroItem
from backend.pdf import PDF
from backend.chunking import chunk_blocks, context_header
from backend.vector_db import ChromaClient
from backend.embed_utils import get_embeddings_batch, get_embedding_dimension, rerank_passages
from backend.model_providers import ProviderManager, Message
from backend.model_providers.base import (
    ResponseValidator, 
    ProviderRateLimitError, 
    ProviderAuthenticationError,
    ProviderContextError,
    ProviderError
)
from backend.conversation_store import ConversationStore
from backend.academic_prompts import AcademicPrompts, AcademicGenerationParams
from backend.query_condenser import QueryCondenser
from backend.clerk import Clerk
import os
import re
from datetime import date
from collections import OrderedDict
from typing import Dict, Optional
import threading
import time
import logging

logger = logging.getLogger(__name__)


# Failures that come from the machine, not the PDF: when these repeat, every
# remaining item would fail the same way, so indexing stops and says why.
_SYSTEMIC_FAILURES = ("Embedding generation failed", "Unexpected embedding dimension", "Failed to add to ChromaDB")
_STOP_AFTER_SYSTEMIC = 5


def _failure_summary(reasons, total):
    """The error for a run where nothing was indexed: the commonest real reason, not a guess."""
    from collections import Counter
    kinds = Counter(r.split(": ", 1)[-1].split(" - ")[0] for r in reasons)
    kind, n = kinds.most_common(1)[0]
    example = next(r.split(": ", 1)[-1] for r in reasons if r.split(": ", 1)[-1].startswith(kind))
    return f"All {total} items failed to index. Most common reason ({n} of {len(reasons)}): {example[:300]}"


class _SkipItem(Exception):
    """Raised inside _index_one with the reason an item could not be indexed."""

class ZoteroChatbot:
    def __init__(
        self, 
        db_path, 
        chroma_path,
        active_provider_id="ollama",
        active_model=None,
        credentials=None,
        embedding_model_id="bge-base",
        storage_path=None
    ):
        self.zlib = ZoteroLibrary(db_path, storage_path=storage_path)
        self.embedding_model_id = embedding_model_id
        # Pass embedding model ID to ChromaClient so it creates model-specific collections
        self.chroma = ChromaClient(chroma_path, embedding_model_id=embedding_model_id)
        
        # Initialize provider manager for LLM interactions
        self.provider_manager = ProviderManager(
            active_provider_id=active_provider_id,
            active_model=active_model,
            credentials=credentials or {}
        )
        
        # Initialize conversation store for stateful chat
        self.conversation_store = ConversationStore()
        
        # Initialize query condenser for follow-up question handling
        self.query_condenser = QueryCondenser(self.provider_manager)

        # The reference desk's small-model jobs (backend/clerk.py)
        self.clerk = Clerk(self.provider_manager)
        self._vocab = None
        self._vocab_at = 0.0
        
        # Indexing state for reporting progress via /index_status
        self.is_indexing = False
        # Cancellation flag for background indexing
        self._cancel_indexing = False
        # Exclusion rules to skip during indexing (set per-run by start_indexing)
        self.excluded_collections = []
        self.excluded_tags = []
        self.excluded_item_types = []
        # Optional: simple progress counter (chunks processed)
        self.index_progress = {
            "processed_items": 0,
            "total_items": 0,
            "start_time": None,
            "elapsed_seconds": 0,
            "skip_reasons": [],  # Track why items are skipped
            "eta_seconds": None,
            "error": None,  # Fatal error that stopped indexing
        }
        self._index_thread = None
    
    def update_provider_settings(
        self,
        active_provider_id=None,
        active_model=None,
        credentials=None
    ):
        """Update the provider settings for this chatbot instance."""
        if active_provider_id:
            self.provider_manager.set_active_provider(active_provider_id, active_model)
        elif active_model:
            self.provider_manager.active_model = active_model
        
        if credentials:
            for provider_id, creds in credentials.items():
                self.provider_manager.set_credentials(provider_id, creds)

    def get_active_model_context_length(self) -> Optional[int]:
        """
        Get the context window size of the currently active model.

        Asked of the provider once per model: this runs two or three times per
        chat turn, and for a cloud provider each ask was a network call.

        Returns:
            Context length in tokens, or None if not available
        """
        try:
            provider = self.provider_manager.get_active_provider()
            model_id = self.provider_manager.get_active_model()
            key = (self.provider_manager.active_provider_id, model_id)
            known = self.__dict__.setdefault("_context_lengths", {})
            if key not in known:
                creds = self.provider_manager.get_credentials(self.provider_manager.active_provider_id)
                model_info = next((m for m in provider.list_models(creds) if m.id == model_id), None)
                known[key] = model_info.context_length if model_info else None
            return known[key]
        except Exception as e:
            # Log but don't fail - fall back to conservative defaults
            logger.debug(f"Could not determine model context length: {e}")
            return None

    def _get_context_char_budget(self) -> int:
        """
        Compute the character budget to pass to trim_messages_for_context.

        Uses 60 % of the active model's context window (reserving 40 % for the
        response and retrieval-prompt overhead).  Assumes ~4 chars per token as
        a conservative estimate for academic text.

        Returns a ceiling of 400 000 chars so we never send absurdly large
        payloads to models with very large windows.  There is intentionally
        NO floor: for small-context models (≤8k tokens) the computed budget
        accurately reflects their limits.  Callers must accept that on ≤8k
        models the system prompt + first-turn evidence alone may already
        exceed the budget; that is a known limitation documented in the README.
        """
        ctx_tokens = self.get_active_model_context_length()
        if ctx_tokens is None:
            # Unknown model — use a conservative 24 000 char (~6k token) default
            return 24_000
        budget = int(ctx_tokens * 4 * 0.60)  # 60 % of window, 4 chars/token
        return min(budget, 400_000)

    def get_retrieval_limits(self, is_focused: bool = False, max_sources_override: int = 0) -> Dict[str, int]:
        """
        Calculate appropriate retrieval limits based on active model's context window.

        Args:
            is_focused: Whether this is a focused query (filters active or ≤2 papers)
            max_sources_override: When > 0, overrides the computed max_total_snippets cap.
                The other parameters (retrieval_k, rerank_top_k, max_snippets_per_paper)
                are derived proportionally so the pipeline can actually reach the target.

        Returns:
            Dict with retrieval_k, rerank_top_k, max_snippets_per_paper, max_total_snippets
        """
        context_length = self.get_active_model_context_length()

        # Define scaling tiers based on context window
        # Format: (max_context, base_multiplier)
        tiers = [
            (1000000, 5.0),   # XLarge: 1M+ tokens (Gemini 1.5 Pro)
            (200000, 4.0),    # Large: 200k tokens (Claude Opus)
            (100000, 3.0),    # Medium: 100k tokens (GPT-4 Turbo)
            (32000, 2.0),     # Small-Med: 32k tokens (GPT-4)
            (0, 1.0),         # Default: Unknown/small context
        ]

        # Find appropriate tier
        multiplier = 1.0
        if context_length:
            for threshold, mult in tiers:
                if context_length >= threshold:
                    multiplier = mult
                    break

        # Base limits (conservative for small-context models)
        if is_focused:
            base = {
                "retrieval_k": 25,
                "rerank_top_k": 15,
                "max_snippets_per_paper": 8,
                "max_total_snippets": 10,
            }
        else:
            base = {
                "retrieval_k": 15,
                "rerank_top_k": 10,
                "max_snippets_per_paper": 3,
                "max_total_snippets": 6,
            }

        # Scale limits by multiplier
        scaled = {
            "retrieval_k": int(base["retrieval_k"] * multiplier),
            "rerank_top_k": int(base["rerank_top_k"] * multiplier),
            "max_snippets_per_paper": int(base["max_snippets_per_paper"] * multiplier),
            "max_total_snippets": int(base["max_total_snippets"] * multiplier),
        }

        # Apply user override: replace max_total_snippets and derive the other
        # parameters proportionally so the pipeline can actually reach the target.
        if max_sources_override > 0:
            override = max_sources_override
            scaled["max_total_snippets"] = override
            # Diversity cap: at least 2, roughly 1/3 of total (same ratio as base)
            scaled["max_snippets_per_paper"] = max(2, override // 3)
            # Fetch enough candidates to satisfy the override after reranking
            scaled["retrieval_k"] = max(scaled["retrieval_k"], override * 2)
            scaled["rerank_top_k"] = max(scaled["rerank_top_k"], override + 5)

        # Log for debugging
        provider_id = self.provider_manager.active_provider_id
        model_id = self.provider_manager.get_active_model()
        override_note = f", override={max_sources_override}" if max_sources_override > 0 else ""
        logger.info(
            f"Retrieval limits for {provider_id}/{model_id} "
            f"(context: {context_length or 'unknown'}{override_note}): {scaled}"
        )

        return scaled

    @staticmethod
    def _exclusion_sets(collections, tags, item_types):
        """Build cleaned exclude sets from raw setting lists."""
        def _clean(values):
            return {v.strip() for v in (values or []) if v and v.strip()}
        return _clean(collections), _clean(tags), _clean(item_types)

    @staticmethod
    def _item_is_excluded(it, excl_colls, excl_tags, excl_types):
        """True if an item matches any exclusion rule on any axis."""
        # ponytail: Zotero collections/tags are stored comma-joined (GROUP_CONCAT),
        # matching how they're written to Chroma metadata. Names containing commas
        # are not distinguishable here (existing limitation).
        def _split(v):
            return [x.strip() for x in (v or "").split(",") if x.strip()]
        item_type = (it['item_type'] or "").strip()
        return (any(c in excl_colls for c in _split(it['collections']))
                or any(t in excl_tags for t in _split(it['tags']))
                or (item_type and item_type in excl_types))

    def _apply_exclusions(self, raw_items):
        """Drop items matching any exclusion rule and purge any that were already
        indexed. Returns the items that should be indexed.

        An item is excluded if *any* of its collections or tags is in the
        exclude set, or its item type is excluded — even when it is also filed
        in a kept collection.
        """
        excl = self._exclusion_sets(self.excluded_collections, self.excluded_tags, self.excluded_item_types)
        if not any(excl):
            return raw_items

        kept, excluded_ids = [], []
        for it in raw_items:
            if self._item_is_excluded(it, *excl):
                excluded_ids.append(str(it['item_id']))
            else:
                kept.append(it)

        self.index_progress["excluded_items"] = len(excluded_ids)
        if excluded_ids:
            indexed = self.chroma.get_indexed_item_ids()
            purged = sum(self.chroma.delete_item(iid) for iid in excluded_ids if iid in indexed)
            msg = f"Exclusions: skipping {len(excluded_ids)} item(s) matching exclusion rules"
            if purged:
                msg += f", purged {purged} previously-indexed chunk(s)"
            logger.debug(msg)
        return kept

    def purge_excluded_items(self, excluded_collections=None, excluded_tags=None, excluded_item_types=None):
        """Delete already-indexed items matching the given exclusion rules from
        the vector store, so exclusions take effect without a reindex.

        Returns {"purged_items": int, "purged_chunks": int}.
        """
        excl = self._exclusion_sets(excluded_collections, excluded_tags, excluded_item_types)
        if not any(excl):
            return {"purged_items": 0, "purged_chunks": 0}

        raw_items = self.zlib.search_parent_items_with_pdfs()
        indexed = self.chroma.get_indexed_item_ids()
        purged_items = purged_chunks = 0
        for it in raw_items:
            iid = str(it['item_id'])
            if iid in indexed and self._item_is_excluded(it, *excl):
                purged_chunks += self.chroma.delete_item(iid)
                purged_items += 1
        if purged_items:
            logger.info(f"Exclusions: purged {purged_items} item(s) / {purged_chunks} chunk(s) from the index")
        return {"purged_items": purged_items, "purged_chunks": purged_chunks}

    @staticmethod
    def _year_of(meta) -> int:
        """0 means unknown."""
        match = re.search(r'\b(19|20)\d{2}\b', meta.get("date") or "")
        return int(match.group(0)) if match else 0

    def _chunk_metadata(self, item, chunks):
        """Per-chunk metadata: primitives only, no None (ChromaDB rejects it)."""
        meta_src = item.metadata
        base = {
            "item_id": str(meta_src.get('item_id')),
            "item_key": meta_src.get("key") or "",
            "title": meta_src.get("title") or "",
            "authors": meta_src.get("authors") or "",
            "tags": meta_src.get("tags") or "",
            "collections": meta_src.get("collections") or "",
            "item_type": meta_src.get("item_type") or "",
            "year": self._year_of(meta_src),
            "pdf_path": meta_src.get("pdf_path") or "",
        }
        return [
            {**base, "chunk_idx": int(i), "page": chunk["page"] or 0, "section": chunk["section"][:80]}
            for i, chunk in enumerate(chunks)
        ]

    def _index_one(self, item) -> int:
        """Extract, chunk, embed and store one Zotero item. Returns the chunk
        count, or raises _SkipItem with the reason it could not be indexed."""
        item_id = str(item['item_id'])
        if not (item.filepath and os.path.exists(item.filepath)):
            raise _SkipItem(f"PDF not found at {item.filepath}")
        try:
            blocks = PDF(item.filepath).extract_blocks()
        except Exception as e:
            raise _SkipItem(f"PDF extraction failed - {e}")
        if not blocks:
            raise _SkipItem("PDF has no extractable text (scanned image without OCR?)")
        meta = item.metadata
        # Reference lists and number-only garble are never useful as passages, so they are not indexed.
        chunks = [c for c in chunk_blocks(blocks, meta.get("title") or "") if c["kind"] == "body"]
        if not chunks:
            raise _SkipItem("No chunks created from pages data")
        texts = [c["text"] for c in chunks]
        # The vector sees which work and section the passage is from; the stored text does not.
        headed = [context_header(meta.get("title"), meta.get("authors"), self._year_of(meta), c["section"]) + c["text"]
                  for c in chunks]
        try:
            vectors = get_embeddings_batch(headed, self.embedding_model_id)
        except Exception as e:
            raise _SkipItem(f"Embedding generation failed - {e}")
        expected_dim = get_embedding_dimension(self.embedding_model_id)
        if vectors and len(vectors[0]) != expected_dim:
            raise _SkipItem(f"Unexpected embedding dimension {len(vectors[0])}, expected {expected_dim}")
        try:
            self.chroma.add_chunks(
                ids=[f"{item_id}:{i}" for i in range(len(chunks))],
                documents=texts,
                metadatas=self._chunk_metadata(item, chunks),
                embeddings=vectors,
            )
        except Exception as e:
            raise _SkipItem(f"Failed to add to ChromaDB - {e}")
        return len(chunks)

    def _index_library_worker(self, incremental: bool):
        """Background indexing. Every item is counted exactly once in
        processed_items, whether it was indexed or skipped, so progress
        always reaches total_items."""
        progress = self.index_progress
        try:
            progress["start_time"] = time.time()
            try:
                raw_items = self.zlib.search_parent_items_with_pdfs()
            except Exception as e:
                msg = str(e)
                progress["error"] = (
                    "Database is locked — please close Zotero completely before syncing."
                    if "database is locked" in msg.lower()
                    else f"Failed to access Zotero database: {msg}"
                )
                logger.error(progress["error"])
                return

            raw_items = self._apply_exclusions(raw_items)
            if incremental:
                indexed_ids = self.chroma.get_indexed_item_ids()
                progress["skipped_items"] = len(indexed_ids)
                raw_items = [it for it in raw_items if str(it['item_id']) not in indexed_ids]

            progress["total_items"] = len(raw_items)
            progress["processed_items"] = 0
            if not raw_items:
                if incremental:
                    logger.info("No new items to index.")
                else:
                    progress["error"] = "No items with PDFs found in Zotero library"
                    logger.warning(progress["error"])
                return
            logger.info("Indexing %d items (%s mode)", len(raw_items), progress.get("mode"))

            streak, stopped = 0, None
            for item in raw_items:
                if self._cancel_indexing:
                    break
                item_id = str(item['item_id'])
                try:
                    if not incremental:
                        # A full reindex replaces the item, so chunks from an older
                        # chunking of the same PDF must not survive.
                        self.chroma.delete_item(item_id)
                    n = self._index_one(item)
                    logger.info("Indexed item %s with %d chunks", item_id, n)
                    streak = 0
                except _SkipItem as skip:
                    reason = f"Item {item_id}: {skip}"
                    logger.warning("Skipped %s", reason)
                    progress["skip_reasons"].append(reason)
                    streak = streak + 1 if str(skip).startswith(_SYSTEMIC_FAILURES) else 0
                    if streak >= _STOP_AFTER_SYSTEMIC:
                        stopped = (f"Indexing stopped: {streak} items in a row failed the same way, so the rest "
                                   f"would too. Your PDFs are not the problem. Last error: {str(skip)[:300]}")
                progress["processed_items"] += 1
                elapsed = time.time() - progress["start_time"]
                progress["elapsed_seconds"] = int(elapsed)
                done, total = progress["processed_items"], progress["total_items"]
                progress["eta_seconds"] = int(elapsed / done * (total - done))
                if stopped:
                    break

            successful = progress["processed_items"] - len(progress["skip_reasons"])
            if successful > 0:
                self.chroma.build_bm25_index()

            logger.info("=== Indexing summary (%s) ===", progress.get("mode"))
            logger.info("Total items attempted: %d", progress["total_items"])
            logger.info("Successfully indexed: %d", successful)
            logger.info("Skipped/Failed: %d", len(progress["skip_reasons"]))
            if stopped:
                progress["error"] = stopped
                logger.error(stopped)
            elif successful == 0 and progress["skip_reasons"]:
                progress["error"] = _failure_summary(progress["skip_reasons"], progress["total_items"])
                logger.error(progress["error"])
            for reason in progress["skip_reasons"][:10]:
                logger.info("  - %s", reason)
            if len(progress["skip_reasons"]) > 10:
                logger.info("  ... and %d more", len(progress["skip_reasons"]) - 10)
        except Exception as e:
            # Name the failing frame in the user-visible error: crash reports that
            # only carry str(e) (e.g. issue #79) can't be located without it.
            import traceback
            tb_last = traceback.extract_tb(e.__traceback__)[-1] if e.__traceback__ else None
            where = f" [{os.path.basename(tb_last.filename)}:{tb_last.lineno}]" if tb_last else ""
            progress["error"] = f"Indexing crashed: {e}{where}"
            logger.exception(progress["error"])
        finally:
            self.is_indexing = False
            self._cancel_indexing = False

    def start_indexing(self, incremental: bool = True, excluded_collections=None,
                       excluded_tags=None, excluded_item_types=None):
        """Start indexing in a background thread. No-op if already indexing.

        Args:
            incremental: If True, only index new items. If False, reindex everything.
            excluded_collections: Collection names whose items should be skipped.
            excluded_tags: Tag names whose items should be skipped.
            excluded_item_types: Zotero item types (e.g. "book") to skip.
                An item is skipped if it matches any rule on any of these axes.
        """
        if self.is_indexing:
            return
        self.excluded_collections = excluded_collections or []
        self.excluded_tags = excluded_tags or []
        self.excluded_item_types = excluded_item_types or []
        self.is_indexing = True
        self._cancel_indexing = False
        # Reset progress
        self.index_progress = {
            "processed_items": 0,
            "total_items": 0,
            "start_time": None,
            "elapsed_seconds": 0,
            "eta_seconds": None,
            "skipped_items": 0,
            "mode": "incremental" if incremental else "full",
            "skip_reasons": [],
            "error": None,  # Clear any previous errors
        }
        
        t = threading.Thread(target=self._index_library_worker, args=(incremental,), daemon=True)
        self._index_thread = t
        t.start()

    def cancel_indexing(self):
        """Signal cancellation for the running indexing job."""
        if not self.is_indexing:
            return
        self._cancel_indexing = True

    def build_search_prompt(self, user_query: str) -> str:
        """Build an enhanced search query using query expansion.
        
        Best practice: Transform natural questions into search-optimized queries
        that better match academic content.
        """
        base = user_query.strip()
        # Keep the original query for semantic matching
        # The embedding model will handle the expansion naturally
        return base


    def _build_filter(
        self,
        query,
        filter_item_ids=None,
        use_metadata_filters=False,
        manual_filters=None,
        provider_manager=None,
        extracted=None,
        exclude_item_ids=None,
    ):
        """Combine item ids, manual filters and filters read from the query into one where clause.

        `extracted` is a scope already read from the query (the desk reads it itself);
        `exclude_item_ids` leaves those items out.

        `provider_manager=None` keeps extraction to the regex pass, so no model runs.

        Returns (where, extracted, item_where): `extracted` is what was read from the
        query (None when nothing was) and `item_where` is the item-id scope alone, the
        place to fall back to when an extracted filter matches nothing.
        """
        from backend.metadata_extractor import extract_metadata_filters
        from backend.metadata_utils import build_metadata_where_clause, merge_where_clauses

        def clause(f):
            return build_metadata_where_clause(
                year_min=f.get("year_min"),
                year_max=f.get("year_max"),
                tags=f.get("tags"),
                collections=f.get("collections"),
                title=f.get("title"),
                author=f.get("author"),
                item_types=f.get("item_types"),
            )

        metadata_where = None
        if extracted:
            metadata_where = clause(extracted)
        elif use_metadata_filters:
            found = extract_metadata_filters(query, provider_manager)
            if found["has_filters"]:
                extracted = found
                metadata_where = clause(found)
                logger.debug(f"METADATA FILTERS (extracted): {found}")
        if manual_filters:
            metadata_where = merge_where_clauses(metadata_where, clause(manual_filters))
            logger.debug(f"METADATA FILTERS (manual): {manual_filters}")

        item_where = {"item_id": {"$in": list(filter_item_ids)}} if filter_item_ids else None
        if exclude_item_ids:
            item_where = merge_where_clauses(item_where, {"item_id": {"$nin": list(exclude_item_ids)}})
        return merge_where_clauses(item_where, metadata_where), extracted or None, item_where

    def _search_and_rerank(self, query, where, k, rerank_top_k, fallback_where=None):
        """Hybrid search (RRF) under `where`, then cross-encoder rerank.

        When the search finds nothing and `fallback_where` differs from `where`, it
        retries once under `fallback_where`. Pass `fallback_where=where` for no fallback.

        Returns (docs, metas, scores, fell_back), with `scores` the reranker's raw
        logits in the same order as `docs`.
        """
        search = self.chroma.query_hybrid_rrf
        search_prompt = self.build_search_prompt(query)

        def run(w):
            results = search(query=search_prompt, k=k, where=w, embedding_model_id=self.embedding_model_id) or {}
            return (results.get("documents") or [[]])[0] or [], (results.get("metadatas") or [[]])[0] or []

        docs, metas = run(where)
        fell_back = False
        if not docs and fallback_where != where:
            logger.debug("FALLBACK: extracted filter returned 0 results, retrying without it")
            docs, metas = run(fallback_where)
            fell_back = True

        scores = []
        if docs:
            # The reranker judges the passage with its work and section named, as the embedder did.
            headed = [context_header(m.get("title"), m.get("authors"), m.get("year"), m.get("section", "")) + d
                      for d, m in zip(docs, metas)]
            ranked = rerank_passages(query, headed, top_k=rerank_top_k)
            docs = [docs[i] for i, _ in ranked]
            metas = [metas[i] for i, _ in ranked]
            scores = [float(score) for _, score in ranked]
        return docs, metas, scores, fell_back

    # Reference desk retrieval is sized for reading, not for a model's context window.
    # Chunks are ~1,100 chars with no overlap, so an item has few of them and a strong
    # match fills fewer slots; 100/60 measured +0.014 nDCG@10 over 60/40 at the same latency.
    DESK_RETRIEVAL_K = 100
    DESK_RERANK_K = 60
    DESK_MAX_ITEMS = 30
    DESK_MAX_KNOWN_ITEMS = 3

    def search(
        self,
        query,
        manual_filters=None,
        use_metadata_filters=True,
        filter_item_ids=None,
        exclude_item_ids=None,
        read_with_model=False,
        read_timeout=None,
    ):
        """Reference desk search: a ranked bibliography with its evidence.

        The request is read into topic and scope: by the clerk's model when
        `read_with_model` and a model is available, otherwise by matching the
        library's vocabulary. The search runs on the topic, the scope becomes
        filters, and scope that matches nothing is dropped and reported, so the
        UI never shows a chip that is silently not applied.
        """
        from backend import clerk_jobs, desk

        started = time.perf_counter()
        query = (query or "").strip()
        manual_filters = manual_filters or {}

        reading, read_by, read_reason = None, None, ""
        data = clerk_jobs.read_query_input(query, self._vocabulary(), date.today())
        if use_metadata_filters:
            if read_with_model:
                result = self.clerk.run(clerk_jobs.READ_QUERY, data, timeout=read_timeout)
                reading, read_reason = result.value, result.reason
                read_by = "model" if result.source == "model" else "library"
            else:
                reading, read_by = data["library_reading"], "library"
        else:
            # Filters off (the reader removed a chip): the scope phrases still leave the search
            # text, since left in they cost the best passage most of its reranker score.
            reading = {"topic": data["library_reading"].get("topic")}
        read_done = time.perf_counter()

        extracted = desk.extracted_scope(reading)
        exclude = list(extracted.pop("exclude", [])) + list(manual_filters.get("exclude") or [])
        topic = (reading or {}).get("topic") or query

        where, extracted_or_none, _ = self._build_filter(
            topic, filter_item_ids=filter_item_ids, manual_filters=manual_filters,
            extracted=extracted, exclude_item_ids=exclude_item_ids,
        )
        base_where = where
        if extracted:
            base_where, _, _ = self._build_filter(
                topic, filter_item_ids=filter_item_ids, manual_filters=manual_filters,
                exclude_item_ids=exclude_item_ids,
            )
        docs, metas, scores, fell_back = self._search_and_rerank(
            topic, where=where, k=self.DESK_RETRIEVAL_K,
            rerank_top_k=self.DESK_RERANK_K, fallback_where=base_where,
        )
        if exclude:
            kept = [i for i, (doc, meta) in enumerate(zip(docs, metas))
                    if not desk.excluded(f"{(meta or {}).get('title', '')} {doc}", exclude)]
            docs, metas, scores = [docs[i] for i in kept], [metas[i] for i in kept], [scores[i] for i in kept]
        retrieved = time.perf_counter()

        items = desk.build_bibliography(docs, metas, scores, topic, max_items=self.DESK_MAX_ITEMS)
        try:
            known = self._known_items(query)
        except Exception as e:
            logger.warning("Known-item lookup failed: %s", e)
            known = []
        # An item set aside (the source of "more like this") is not pinned back on top.
        known = [k for k in known if str(k["item_id"]) not in set(map(str, exclude_item_ids or []))]
        try:
            citations = self.zlib.get_bibliographic([it["item_id"] for it in items] + [k["item_id"] for k in known])
        except Exception as e:
            logger.warning("Could not read citations from the Zotero database: %s", e)
            citations = {}
        for entry in items + known:
            entry["citation"] = citations.get(entry["item_id"])

        shown = dict(extracted)
        if reading and reading.get("exclude"):
            shown["exclude"] = reading["exclude"]
        return {
            "query": query,
            "scope": {
                "manual": manual_filters,
                "extracted": shown,
                "extracted_ignored": bool(extracted) and fell_back,
                "topic": topic,
                "read_by": read_by,
                "read_reason": read_reason,
            },
            "known_items": known,
            "items": items,
            "see_also_count": sum(1 for it in items if it["band"] == desk.SEE_ALSO),
            "timing_ms": {
                "read": round((read_done - started) * 1000),
                "retrieve": round((retrieved - read_done) * 1000),
                "total": round((time.perf_counter() - started) * 1000),
            },
        }

    VOCAB_TTL = 600  # seconds; tags and collections change rarely during a session

    def _vocabulary(self):
        """The library's names a request can refer to: authors, tags, collections, item types."""
        if self._vocab is not None and time.time() - self._vocab_at < self.VOCAB_TTL:
            return self._vocab
        try:
            vocab = {
                "authors": self.zlib.get_creator_last_names(),
                "tags": self.zlib.get_all_tags(),
                "collections": [c["name"] for c in self.zlib.get_all_collections()],
                "item_types": [t["name"] for t in self.zlib.get_all_item_types()],
                "common_tags": self.zlib.get_common_tags(),
            }
        except Exception as e:
            logger.warning("Could not read the library's vocabulary: %s", e)
            vocab = {"authors": [], "tags": [], "collections": [], "item_types": [], "common_tags": set()}
        self._vocab, self._vocab_at = vocab, time.time()
        return vocab

    def annotate(self, query, items, also_try=True, themes=True, workers=2):
        """The clerk's work on a result list, yielded as each piece finishes.

        Events: {"type": "also_try"} and {"type": "themes"} in order of completion,
        then {"type": "done"} with counts. Closing the generator cancels work that
        has not started. The per-item note (clerk_jobs.NOTE) is not run since
        2026-10-13: one model call and an entailment check per result cost more
        than the notes were worth; the row keeps its extract.
        """
        import concurrent.futures
        from backend import clerk_jobs
        from backend.embed_utils import get_embeddings_batch

        started = time.perf_counter()
        counts = {"model": 0, "fallback": 0, "reasons": {}}
        listed = [it for it in items if it.get("band") != "see_also"]

        def also_try_task():
            # From the listed rows only: on a list of weak "see also" matches the suggestions
            # were those items' tags ("climate change" for medieval agriculture).
            data = clerk_jobs.also_try_input(query, listed, common=self._vocabulary()["common_tags"])
            if not data["candidates"]:
                return None, None
            result = self.clerk.run(clerk_jobs.ALSO_TRY, data)
            return result, {"type": "also_try", "suggestions": result.value, "source": result.source}

        def themes_task():
            groups = clerk_jobs.cluster_items(listed, embed=lambda texts: get_embeddings_batch(texts, self.embedding_model_id))
            if not groups:
                return None, None
            result = self.clerk.run(clerk_jobs.THEMES, {"groups": groups})
            return result, {
                "type": "themes",
                "source": result.source,
                "groups": [{"label": result.value.get(g["id"]), "item_ids": g["item_ids"]} for g in groups],
            }

        tasks = ([also_try_task] if also_try else []) + ([themes_task] if themes else [])

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="annotate")
        futures = [pool.submit(task) for task in tasks]
        try:
            for future in concurrent.futures.as_completed(futures):
                try:
                    result, event = future.result()
                except Exception as e:  # one failed job (an embedding error, say) must not end the others
                    logger.warning("Annotate job failed: %s", e)
                    counts["reasons"]["error"] = counts["reasons"].get("error", 0) + 1
                    continue
                if result is not None:
                    counts[result.source] += 1
                    if result.reason:
                        kind = result.reason.split(":")[0]
                        counts["reasons"][kind] = counts["reasons"].get(kind, 0) + 1
                        # The first full reason of each kind, so "why the fallback" can be answered.
                        counts.setdefault("detail", {}).setdefault(kind, result.reason)
                if event is not None:
                    yield event
        finally:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)

        yield {"type": "done", "counts": counts, "model": self.clerk.model(), "ms": round((time.perf_counter() - started) * 1000)}

    def citation_chain(self, item_id):
        """An item's references and the works citing it (Semantic Scholar), the reader's own copies marked.

        None when the item is not in the library; {"found": False} when Semantic
        Scholar does not know it. Network errors propagate for the endpoint to explain.
        """
        from backend import desk
        from backend.external_api_utils import fetch_citation_chain

        citation = self.zlib.get_bibliographic([item_id]).get(str(item_id))
        if not citation:
            return None
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", citation.get("doi") or "", flags=re.I).strip()
        chain = fetch_citation_chain(doi=doi or None, title=None if doi else citation.get("title"))
        if chain is None:
            return {"found": False}
        dois, titles = self.zlib.get_doi_and_title_index()
        for relation in ("references", "cited_by"):
            chain[relation] = desk.mark_owned(chain[relation], dois, titles)
        owned = {e["owned_item_id"] for r in ("references", "cited_by") for e in chain[r] if e["owned_item_id"]}
        citations = self.zlib.get_bibliographic(owned) if owned else {}
        for relation in ("references", "cited_by"):
            for entry in chain[relation]:
                entry["citation"] = citations.get(entry["owned_item_id"]) if entry["owned_item_id"] else None
        return {"found": True, **chain}

    def _known_items(self, query):
        """Items the query names directly: DOI, ISBN, arXiv id, a title, or author and year."""
        from backend import desk

        hint = desk.detect_known_item(query)
        if not hint:
            return []
        z = self.zlib
        kind = hint["kind"]
        if kind == "doi":
            ids = [i for i, _ in z.find_items_by_field(("DOI", "url", "extra"), hint["doi"])]
        elif kind == "isbn":
            ids = [i for i, _ in z.find_items_by_field(("ISBN",), hint["isbn"], normalise=True)]
        elif kind == "arxiv":
            ids = [i for i, _ in z.find_items_by_field(("url", "extra", "DOI", "archiveID"), hint["arxiv"])]
        elif kind == "author_year":
            ids = z.find_items_by_creator_year(hint["authors"][0], hint["year"])
            others = [name.lower() for name in hint["authors"][1:]]
            if others and ids:
                creators = {i: c.get("creators", []) for i, c in z.get_bibliographic(ids).items()}
                ids = [
                    i for i in ids
                    if all(any(c["last"].lower().startswith(o) for c in creators.get(i, [])) for o in others)
                ]
        else:
            words = sorted(desk.title_words(hint["title"]), key=len, reverse=True)
            if not words or len(words[0]) < 4:
                return []
            threshold = 0.5 if hint.get("quoted") else desk.TITLE_MATCH_MIN
            scored = {}
            for item_id, title in z.find_items_by_field(("title", "shortTitle"), words[0], limit=200):
                score = desk.title_match_score(hint["title"], title)
                if score >= threshold:
                    scored[item_id] = max(score, scored.get(item_id, 0.0))
            ids = sorted(scored, key=scored.get, reverse=True)

        seen = []
        for item_id in ids:
            if item_id not in seen:
                seen.append(item_id)
        return [
            {"item_id": item_id, "kind": kind, "indexed": bool(self.chroma.item_exists(item_id))}
            for item_id in seen[: self.DESK_MAX_KNOWN_ITEMS]
        ]

    def chat(
        self,
        query,
        filter_item_ids=None,
        session_id=None,
        use_metadata_filters=False,
        manual_filters=None,
        use_rrf=True,
        max_sources=0,
    ):
        """
        Process a chat query with stateful conversation history using Perplexity-style architecture.
        
        Architecture:
        1. Load conversation history (if session exists)
        2. CONDENSE: Convert follow-up questions to standalone queries
        3. RETRIEVE: Use standalone query for vector search (with optional metadata filtering)
        4. GENERATE: Build messages and call LLM
        
        Args:
            query: User's question (may be a follow-up with pronouns/context references)
            filter_item_ids: Optional list of Zotero item IDs to filter search
            session_id: Optional session ID for conversation continuity
            use_metadata_filters: Whether to extract metadata filters from query
            manual_filters: Manual metadata filters dict with keys:
                - year_min: int
                - year_max: int
                - tags: list of strings
                - collections: list of strings
            use_rrf: Accepted for older clients; retrieval is always RRF hybrid search.
            
        Returns:
            Dictionary with summary, citations, and snippets
        """
        # STEP 1: Load conversation history
        conversation_history = []
        is_new_session = False
        user_turns = 0
        
        logger.debug("\n" + "="*80)
        logger.debug(f"CHAT TURN START: query='{query[:80]}...'")
        logger.debug("="*80)
        
        if session_id:
            conversation_history = self.conversation_store.get_messages(
                session_id, 
                provider_id=self.provider_manager.active_provider_id
            )
            user_turns = len([m for m in conversation_history if m.role == "user"])
            is_new_session = (user_turns == 0)
            logger.debug(f"Session {session_id}: user_turns={user_turns}, is_new={is_new_session}")
            logger.debug(f"History has {len(conversation_history)} messages total")
        
        # STEP 2: CONDENSE query if it's a follow-up
        retrieval_query = query  # Default to original
        is_follow_up = bool(session_id) and self.query_condenser.should_condense(query, conversation_history)

        if is_follow_up:
            logger.debug("\nCONDENSATION: Detected follow-up question")
            retrieval_query = self.query_condenser.condense_query(
                query=query,
                conversation_history=conversation_history,
                max_history_chars=1500
            )
            logger.debug(f"   Original query: '{query}'")
            logger.debug(f"   Condensed query: '{retrieval_query}'")
        else:
            logger.debug(f"\nCONDENSATION: Skipped (is_new_session={is_new_session}, turns={user_turns})")
            logger.debug(f"   Using original query: '{query}'")
        
        # STEP 3: RETRIEVE using the standalone/condensed query
        db_filter, _extracted, item_where = self._build_filter(
            retrieval_query,
            filter_item_ids=filter_item_ids,
            use_metadata_filters=use_metadata_filters,
            manual_filters=manual_filters,
            provider_manager=self.provider_manager,
        )
        if db_filter:
            logger.debug(f"\nFINAL WHERE CLAUSE: {db_filter}")

        # Get dynamic retrieval limits based on model's context window
        is_focused_query_prelim = db_filter is not None
        limits = self.get_retrieval_limits(is_focused=is_focused_query_prelim, max_sources_override=max_sources)

        # Manual filters are intentional, so only an auto-extracted filter falls back.
        fallback_where = item_where if (use_metadata_filters and not manual_filters) else db_filter
        # "Which of these is earliest" is about the sources discussed so far, not the whole
        # library: a follow-up that refers back searches those first, and the library only
        # when they hold nothing on it.
        prior_ids = [s["item_id"] for s in self.conversation_store.cited_sources(session_id) if s.get("item_id")] if is_follow_up and not filter_item_ids else []
        where = db_filter
        if prior_ids:
            from backend.metadata_utils import merge_where_clauses
            where = merge_where_clauses({"item_id": {"$in": prior_ids}}, db_filter)
        docs, metas, _scores, fell_back = self._search_and_rerank(
            retrieval_query,
            where=where,
            k=limits["retrieval_k"],
            rerank_top_k=limits["rerank_top_k"],
            fallback_where=fallback_where,
        )
        among_prior = bool(prior_ids) and not fell_back

        # Detect focused queries and relax caps so deep single-document questions
        # get enough context. Two signals trigger focused mode:
        #   1. An active filter (user explicitly narrowed the library) — always go deeper
        #   2. Results naturally concentrated in ≤2 papers (semantically focused query)
        unique_papers = {meta.get("title") for meta in metas if meta.get("title")}
        is_focused_query = db_filter is not None or len(unique_papers) <= 2

        # Recalculate limits if focus mode changed (rare but possible)
        if is_focused_query != is_focused_query_prelim:
            limits = self.get_retrieval_limits(is_focused=is_focused_query, max_sources_override=max_sources)

        max_snippets_per_paper = limits["max_snippets_per_paper"]
        max_total_snippets = limits["max_total_snippets"]

        # Build snippets; citation numbers hold for the whole session so [N] names one source throughout.
        snippets = []
        turn_numbers = OrderedDict()  # without a session, numbers live for this turn only

        def cite(key, meta):
            if session_id:
                return self.conversation_store.cite(session_id, key, meta)
            if key not in turn_numbers:
                turn_numbers[key] = {"id": len(turn_numbers) + 1, **meta}
            return turn_numbers[key]["id"]

        paper_snippet_count = {}

        for doc, meta in zip(docs, metas):
            title = meta.get("title") or "Untitled"
            year = meta.get("year") or ""
            authors = meta.get("authors") or ""
            pdf_path = meta.get("pdf_path") or ""
            page = meta.get("page")
            key = (title, year, pdf_path)

            paper_id = f"{title}_{year}"
            if paper_snippet_count.get(paper_id, 0) >= max_snippets_per_paper:
                continue

            paper_snippet_count[paper_id] = paper_snippet_count.get(paper_id, 0) + 1

            cid = cite(key, {"title": title, "year": year, "authors": authors, "pdf_path": pdf_path, "item_id": str(meta.get("item_id") or "")})
            snippet_text = (doc or "")[:800]
            snippets.append({
                "citation_id": cid,
                "snippet": snippet_text,
                "title": title,
                "year": year,
                "authors": authors,
                "pdf_path": pdf_path,
                "page": page,
            })

            if len(snippets) >= max_total_snippets:
                break

        all_sources = self.conversation_store.cited_sources(session_id) if session_id else list(turn_numbers.values())
        turn_ids = {s["citation_id"] for s in snippets}

        # STEP 4: BUILD MESSAGES. Every turn gets the same shape: question, this turn's
        # passages, a key to earlier-cited sources, and where the passages came from.
        if filter_item_ids:
            n = len(filter_item_ids)
            scope = "the one item you chose" if n == 1 else f"the {n} items you chose"
        elif among_prior:
            scope = "the sources discussed so far in this conversation"
        elif manual_filters or (use_metadata_filters and _extracted):
            scope = "the part of your library matching your filters"
        else:
            scope = "your whole library"
        user_message = AcademicPrompts.build_turn_message(
            query, snippets, scope, earlier_sources=[s for s in all_sources if s["id"] not in turn_ids]
        )
        logger.debug(f"\nMESSAGE CONSTRUCTION: is_new_session={is_new_session}, snippets={len(snippets)}, scope={scope}")

        if session_id:
            # Append user message to history
            self.conversation_store.append_message(session_id, "user", user_message)
            
            # Get updated history and trim for context window
            full_history = self.conversation_store.get_messages(
                session_id,
                provider_id=self.provider_manager.active_provider_id
            )
            logger.debug(f"\nFULL HISTORY before trim: {len(full_history)} messages")
            for i, msg in enumerate(full_history):
                preview = msg.content[:100].replace('\n', ' ')
                logger.debug(f"   [{i}] {msg.role:10s}: {preview}...")
            
            messages = self.conversation_store.trim_messages_for_context(
                full_history, 
                max_messages=20,  # Last 10 turns
                max_chars=self._get_context_char_budget()
            )
            
            # Log the actual messages being sent to LLM
            logger.debug(f"\nMESSAGES TO LLM: {len(messages)} messages")
            for i, msg in enumerate(messages):
                content_preview = msg.content[:150].replace('\n', ' ') + ('...' if len(msg.content) > 150 else '')
                logger.debug(f"   [{i}] {msg.role:10s}: {content_preview}")
        else:
            messages = [Message(role="system", content=AcademicPrompts.get_system_prompt()), Message(role="user", content=user_message)]
        
        # STEP 5: GENERATE answer using LLM
        gen_params = AcademicGenerationParams.get_params("standard")
        
        logger.debug(f"\nLLM GENERATION: Calling provider with temp={gen_params['temperature']}")
        
        reasoning_content = None
        
        try:
            response = self.provider_manager.chat(
                messages=messages,
                temperature=gen_params["temperature"],
                max_tokens=gen_params["max_tokens"],
                top_p=gen_params["top_p"],
                top_k=gen_params["top_k"],
                repeat_penalty=gen_params["repeat_penalty"]
            )
            raw_content = response.content
            
            # Extract <think>...</think> content if present
            think_pattern = r'<think>(.*?)</think>'
            think_matches = re.findall(think_pattern, raw_content, re.DOTALL)
            
            if think_matches:
                # Extract the thinking content
                reasoning_content = '\n\n'.join(think_matches).strip()
                # Remove the <think> tags from the main response
                summary = re.sub(think_pattern, '', raw_content, flags=re.DOTALL).strip()
                logger.debug(f"\nEXTRACTED REASONING: ({len(reasoning_content)} chars)")
                logger.debug(f"   First 200 chars: {reasoning_content[:200].replace(chr(10), ' ')}...")
            else:
                summary = raw_content
            
            logger.debug(f"\nLLM RESPONSE received ({len(summary)} chars)")
            logger.debug(f"   First 200 chars: {summary[:200].replace(chr(10), ' ')}...")
            
            # Validate response for common failure patterns
            is_valid, issues = ResponseValidator.validate_chat_response(
                response, 
                self.provider_manager.active_provider_id
            )
            
            if not is_valid:
                logger.warning(
                    f"Provider {self.provider_manager.active_provider_id} failed validation: {issues}"
                )
                logger.debug(f"\nWARNING: Response validation failed with {len(issues)} issues:")
                for issue in issues:
                    logger.debug(f"   - {issue}")
                
                # Log specific patterns for debugging
                if "Meta-response detected" in issues:
                    logger.warning(
                        f"Meta-response detected for provider {self.provider_manager.active_provider_id}. "
                        "Instructions may have been embedded in user message."
                    )
                    logger.debug("    This indicates instructions were embedded in the user message.")
                    logger.debug("    The model acknowledged instructions instead of answering.")
                
                if "Raw citations detected" in issues:
                    logger.warning(
                        f"Raw citations detected for provider {self.provider_manager.active_provider_id}. "
                        "Web search may have been activated instead of using provided context."
                    )
                    logger.debug("    Perplexity returned search results instead of answer.")
                    logger.debug("    This may indicate web search mode was activated instead of using provided context.")
                    logger.debug("    Consider switching to a different model provider for RAG over private documents.")
            
            # Save assistant response to conversation history
            if session_id:
                self.conversation_store.append_message(session_id, "assistant", summary)
        except ProviderRateLimitError as e:
            # Specific handling for rate limit errors
            logger.debug(f"\n{'='*80}")
            logger.debug(f"RATE LIMIT ERROR")
            logger.debug(f"{'='*80}")
            logger.debug(f"Provider: {self.provider_manager.active_provider_id}")
            logger.error(f"Error message: {str(e)}")
            logger.debug(f"{'='*80}\n")
            
            # Return user-friendly error message
            provider_name = self.provider_manager.active_provider_id.title()
            summary = (
                f"{provider_name} Rate Limit Exceeded\n\n"
                f"Your {provider_name} API account has exceeded its quota. "
                f"Please check your billing and plan details:\n\n"
                f"• OpenAI: https://platform.openai.com/account/billing\n"
                f"• Anthropic: https://console.anthropic.com/settings/plans\n"
                f"• Google: https://console.cloud.google.com/billing\n\n"
                f"You can switch to a different provider in Settings or add credits to your account."
            )
        except ProviderAuthenticationError as e:
            # Specific handling for authentication errors
            logger.debug(f"\n{'='*80}")
            logger.debug(f"AUTHENTICATION ERROR")
            logger.debug(f"{'='*80}")
            logger.debug(f"Provider: {self.provider_manager.active_provider_id}")
            logger.error(f"Error message: {str(e)}")
            logger.debug(f"{'='*80}\n")
            
            provider_name = self.provider_manager.active_provider_id.title()
            summary = (
                f"{provider_name} Authentication Failed\n\n"
                f"Your API key appears to be invalid or has expired. "
                f"Please check your API key in Settings and ensure it's correct."
            )
        except ProviderContextError as e:
            # Specific handling for context length errors
            logger.debug(f"\n{'='*80}")
            logger.debug(f"CONTEXT LENGTH ERROR")
            logger.debug(f"{'='*80}")
            logger.debug(f"Provider: {self.provider_manager.active_provider_id}")
            logger.debug(f"Model: {self.provider_manager.get_active_model()}")
            logger.error(f"Error message: {str(e)}")
            logger.debug(f"{'='*80}\n")
            
            model_name = self.provider_manager.get_active_model()
            summary = (
                f"Context Too Long\n\n"
                f"The conversation history and retrieved documents exceed the maximum context length "
                f"for {model_name}. Try starting a new chat session or selecting a model with a larger "
                f"context window."
            )
        except Exception as e:
            logger.debug(f"\n{'='*80}")
            logger.debug(f"LLM GENERATION ERROR")
            logger.debug(f"{'='*80}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            logger.debug(f"{'='*80}\n")
            
            # Return helpful error message instead of snippet fallback
            provider_name = self.provider_manager.active_provider_id.title()
            model_name = self.provider_manager.get_active_model()
            error_type = type(e).__name__
            summary = (
                f"Model Response Failed\n\n"
                f"The {provider_name} model ({model_name}) encountered an error and could not generate a response.\n\n"
                f"**Error Type**: {error_type}\n\n"
                f"**What to try**:\n"
                f"• Switch to a different model or provider in Settings\n"
                f"• Check your API key and account status\n"
                f"• Try rephrasing your question\n"
                f"• Start a new chat session if the conversation is very long\n\n"
                f"*Error details: {str(e)[:200]}*"
            )

        # The sources the answer can be checked against: this turn's passages, and any
        # earlier source the answer cites by number.
        summary = AcademicPrompts.normalise_citations(summary)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", summary)}
        citations = [src for src in all_sources if src["id"] in turn_ids or src["id"] in cited]

        # STEP 6: Generate session title for new sessions
        generated_title = None
        if session_id and is_new_session:
            generated_title = self.generate_session_title(query, summary)
            logger.debug(f"Generated session title: {generated_title}")

        logger.debug("\n" + "="*80)
        logger.debug(f"CHAT TURN COMPLETE")
        logger.debug(f"   Citations: {len(citations)}, Snippets: {len(snippets)}")
        logger.debug(f"   Reasoning: {'Yes' if reasoning_content else 'No'}")
        logger.debug("="*80 + "\n")

        result = {
            "summary": summary,
            "citations": citations,
            "snippets": snippets,
            "generated_title": generated_title,
        }
        
        # Add reasoning field only if present
        if reasoning_content:
            result["reasoning"] = reasoning_content
        
        return result
    
    def generate_session_title(self, user_question: str, assistant_response: str) -> str:
        """
        Generate a concise title for a chat session based on the first interaction.
        
        Uses optimized parameters for short, focused title generation.
        
        Args:
            user_question: The user's first question
            assistant_response: The assistant's first response
            
        Returns:
            A concise title (3-8 words) summarizing the session topic
        """
        try:
            logger.debug(f"Generating title for question: {user_question[:100]}")
            
            # Use academic prompt template for title generation
            prompt = AcademicPrompts.build_session_title_prompt(
                user_question=user_question,
                assistant_response=assistant_response
            )
            
            # Use title-specific generation parameters
            title_params = AcademicGenerationParams.get_params("title")
            
            messages = [Message(role="user", content=prompt)]
            response = self.provider_manager.chat(
                messages=messages,
                temperature=title_params["temperature"],      # 0.7 for creativity
                max_tokens=title_params["max_tokens"],        # 30 for brevity
                top_p=title_params["top_p"],
                top_k=title_params["top_k"],
                repeat_penalty=title_params["repeat_penalty"]
            )
            
            # Clean up the generated title
            title = response.content.strip()
            logger.debug(f"Raw title from LLM: '{title}'")
            # Remove quotes if present
            title = title.strip('"').strip("'")
            # Limit length
            if len(title) > 80:
                title = title[:77] + "..."
            
            logger.debug(f"Cleaned title: '{title}'")
            return title if title else user_question[:50]
        except Exception as e:
            logger.debug(f"Title generation error: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to first few words of question
            return user_question[:50]


