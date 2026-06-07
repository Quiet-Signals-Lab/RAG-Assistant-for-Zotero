# interface.py

from backend.zotero_dbase import ZoteroLibrary
from backend.zoteroitem import ZoteroItem
from backend.pdf import PDF
from backend.vector_db import ChromaClient
from backend.embed_utils import get_embedding, get_embeddings_batch, rerank_passages
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
import os
import re
from collections import OrderedDict
from typing import Dict, Optional
import threading
import time
import logging

# Initialize logger for this module
logger = logging.getLogger(__name__)

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
        
        # Indexing state for reporting progress via /index_status
        self.is_indexing = False
        # Cancellation flag for background indexing
        self._cancel_indexing = False
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

        Returns:
            Context length in tokens, or None if not available
        """
        try:
            provider = self.provider_manager.get_active_provider()
            model_id = self.provider_manager.get_active_model()
            creds = self.provider_manager.get_credentials(self.provider_manager.active_provider_id)

            # Get available models from provider
            models = provider.list_models(creds)

            # Find the active model
            model_info = next(
                (m for m in models if m.id == model_id),
                None
            )

            return model_info.context_length if model_info else None
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

    def _index_library_worker(self):
        try:
            start_time = time.time()
            self.index_progress["start_time"] = start_time
            
            # Validate database access before starting
            try:
                raw_items = self.zlib.search_parent_items_with_pdfs()
            except Exception as e:
                error_str = str(e)
                if "database is locked" in error_str.lower():
                    error_msg = "Database is locked — please close Zotero completely before syncing."
                else:
                    error_msg = f"Failed to access Zotero database: {error_str}"
                print(f"FATAL ERROR: {error_msg}")
                self.index_progress["error"] = error_msg
                return
            
            self.index_progress["total_items"] = len(raw_items)
            self.index_progress["processed_items"] = 0
            
            if len(raw_items) == 0:
                self.index_progress["error"] = "No items with PDFs found in Zotero library"
                print("WARNING: No items with PDFs found")
                return
            
            items = [ZoteroItem(filepath=it['pdf_path'], metadata=it) for it in raw_items]

            # Extract text for each item using PDF logic with page numbers
            for item in items:
                if self._cancel_indexing:
                    break
                if not (item.filepath and os.path.exists(item.filepath)):
                    skip_reason = f"Item {item.metadata.get('item_id')}: PDF not found at {item.filepath}"
                    print(f"SKIPPED: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue
                pdf = PDF(item.filepath)
                # Use page-aware extraction
                try:
                    pages_data = pdf.extract_text_with_pages()
                    item.metadata['pages_data'] = pages_data
                    text = "\\n\\n".join([p['text'] for p in pages_data])
                    item.metadata['text'] = text if text else ""
                    if not text:
                        print(f"WARNING: Item {item.metadata.get('item_id')} PDF extracted but no text found")
                except Exception as e:
                    skip_reason = f"Item {item.metadata.get('item_id')}: PDF extraction failed - {str(e)}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    item.metadata['pages_data'] = []

            # Vectorize each item's text (chunk/embedding logic with page tracking)
            for item in items:
                if self._cancel_indexing:
                    break
                pages_data = item.metadata.get('pages_data') or []
                if not pages_data:
                    # Item was already marked as failed in PDF extraction phase
                    # Skip silently without incrementing progress again
                    continue
                
                # Chunk with page awareness
                chunks_with_pages = self.chunk_text_with_pages(pages_data)
                if not chunks_with_pages:
                    skip_reason = f"Item {item.metadata.get('item_id')}: No chunks created from pages data"
                    print(f"SKIPPED: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue
                
                chunks = [c['text'] for c in chunks_with_pages]
                try:
                    vectors = get_embeddings_batch(chunks, self.embedding_model_id)
                except Exception as e:
                    skip_reason = f"Item {item.metadata.get('item_id')}: Embedding generation failed - {str(e)}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue

                # Validate embedding dimensions
                from backend.embed_utils import get_embedding_dimension
                expected_dim = get_embedding_dimension(self.embedding_model_id)
                if vectors and len(vectors[0]) != expected_dim:
                    skip_reason = f"Item {item.metadata.get('item_id')}: Unexpected embedding dimension {len(vectors[0])}, expected {expected_dim}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue

                # Generate unique chunk IDs
                item_id = str(item.metadata.get('item_id'))
                chunk_ids = [f"{item_id}:{i}" for i in range(len(chunks))]

                # Sanitize metadata per chunk to primitives, no None
                meta_src = item.metadata
                title = meta_src.get("title") or ""
                authors = meta_src.get("authors") or ""
                tags = meta_src.get("tags") or ""
                collections = meta_src.get("collections") or ""
                item_type = meta_src.get("item_type") or ""
                
                # Parse year as integer (supports format like "2020-01-15" or just "2020")
                year_str = meta_src.get("date") or ""
                year = 0  # Default to 0 instead of None (ChromaDB doesn't accept None)
                if year_str:
                    match = re.search(r'\b(19|20)\d{2}\b', year_str)
                    if match:
                        year = int(match.group(0))
                
                pdf_path = meta_src.get("pdf_path") or ""

                metas = []
                for i, chunk_info in enumerate(chunks_with_pages):
                    metas.append({
                        "item_id": item_id,
                        "chunk_idx": int(i),
                        "title": title,
                        "authors": authors,
                        "tags": tags,
                        "collections": collections,
                        "item_type": item_type,
                        "year": year,  # Integer (0 if unknown)
                        "pdf_path": pdf_path,
                        "page": chunk_info.get('page', 0),  # Use 0 if page is None
                    })

                try:
                    self.chroma.add_chunks(
                        ids=chunk_ids,
                        documents=chunks,
                        metadatas=metas,
                        embeddings=vectors
                    )
                    print(f"SUCCESS: Indexed item {item_id} with {len(chunks)} chunks")
                except Exception as e:
                    skip_reason = f"Item {item_id}: Failed to add to ChromaDB - {str(e)}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                
                # Update progress after processing this item
                self.index_progress["processed_items"] += 1
                
                # Calculate time estimates
                elapsed = time.time() - self.index_progress["start_time"]
                self.index_progress["elapsed_seconds"] = int(elapsed)
                
                processed = self.index_progress["processed_items"]
                total = self.index_progress["total_items"]
                if processed > 0 and total > 0:
                    avg_time_per_item = elapsed / processed
                    remaining_items = total - processed
                    self.index_progress["eta_seconds"] = int(avg_time_per_item * remaining_items)
                
                # small sleep to allow cancellation to be checked promptly in CPU-bound loops
                time.sleep(0)
            
            # Build BM25 index after adding all chunks
            successful_items = self.index_progress["processed_items"] - len(self.index_progress.get("skip_reasons", []))
            if successful_items > 0:
                print(f"Building BM25 index for sparse retrieval after indexing {successful_items} items...")
                self.chroma.build_bm25_index()
            
            # Print summary
            print(f"\\n=== Full Indexing Summary ===")
            print(f"Total items attempted: {self.index_progress['total_items']}")
            print(f"Successfully indexed: {successful_items}")
            print(f"Skipped/Failed: {len(self.index_progress.get('skip_reasons', []))}")
            
            # Check if ALL items failed
            if successful_items == 0 and self.index_progress['total_items'] > 0:
                error_msg = f"All {self.index_progress['total_items']} items failed to index. Common causes: PDFs not found (check storage path), network drive issues, or file permissions."
                print(f"FATAL ERROR: {error_msg}")
                self.index_progress["error"] = error_msg
            
            if self.index_progress.get('skip_reasons'):
                print(f"\\nSkip reasons:")
                for reason in self.index_progress['skip_reasons'][:10]:  # Show first 10
                    print(f"  - {reason}")
                if len(self.index_progress['skip_reasons']) > 10:
                    print(f"  ... and {len(self.index_progress['skip_reasons']) - 10} more")
            print(f"=============================\\n")
        except Exception as e:
            # Catch any unexpected exceptions at thread level
            import traceback
            error_msg = f"Indexing crashed: {str(e)}"
            traceback_str = traceback.format_exc()
            print(f"FATAL ERROR: {error_msg}")
            print(f"Traceback:\\n{traceback_str}")
            self.index_progress["error"] = error_msg
        finally:
            self.is_indexing = False
            self._cancel_indexing = False

    def _index_library_incremental_worker(self):
        """Index only new items that aren't already in the database."""
        try:
            start_time = time.time()
            self.index_progress["start_time"] = start_time
            
            # Validate database access before starting
            try:
                raw_items = self.zlib.search_parent_items_with_pdfs()
            except Exception as e:
                error_str = str(e)
                if "database is locked" in error_str.lower():
                    error_msg = "Database is locked — please close Zotero completely before syncing."
                else:
                    error_msg = f"Failed to access Zotero database: {error_str}"
                print(f"FATAL ERROR: {error_msg}")
                self.index_progress["error"] = error_msg
                return
            
            all_item_ids = {str(it['item_id']) for it in raw_items}
            
            # Get already indexed item IDs
            indexed_ids = self.chroma.get_indexed_item_ids()
            
            # Find new items
            new_item_ids = all_item_ids - indexed_ids
            
            # Filter to only new items
            new_items_data = [it for it in raw_items if str(it['item_id']) in new_item_ids]
            
            self.index_progress["total_items"] = len(new_items_data)
            self.index_progress["processed_items"] = 0
            self.index_progress["skipped_items"] = len(indexed_ids)
            
            if len(new_items_data) == 0:
                print("No new items to index.")
                return
            
            print(f"Found {len(new_items_data)} new items to index (skipping {len(indexed_ids)} already indexed)")
            
            items = [ZoteroItem(filepath=it['pdf_path'], metadata=it) for it in new_items_data]

            # Extract text for each new item
            for item in items:
                if self._cancel_indexing:
                    break
                if not (item.filepath and os.path.exists(item.filepath)):
                    skip_reason = f"Item {item.metadata.get('item_id')}: PDF not found at {item.filepath}"
                    print(f"SKIPPED: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue
                pdf = PDF(item.filepath)
                try:
                    pages_data = pdf.extract_text_with_pages()
                    item.metadata['pages_data'] = pages_data
                    text = "\n\n".join([p['text'] for p in pages_data])
                    item.metadata['text'] = text if text else ""
                    if not text:
                        print(f"WARNING: Item {item.metadata.get('item_id')} PDF extracted but no text found")
                except Exception as e:
                    skip_reason = f"Item {item.metadata.get('item_id')}: PDF extraction failed - {str(e)}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    item.metadata['pages_data'] = []

            # Vectorize each new item
            for item in items:
                if self._cancel_indexing:
                    break
                pages_data = item.metadata.get('pages_data') or []
                if not pages_data:
                    # Item was already marked as failed in PDF extraction phase
                    # Skip silently without incrementing progress again
                    continue
                
                chunks_with_pages = self.chunk_text_with_pages(pages_data)
                if not chunks_with_pages:
                    self.index_progress["processed_items"] += 1
                    continue
                
                chunks = [c['text'] for c in chunks_with_pages]
                try:
                    vectors = get_embeddings_batch(chunks, self.embedding_model_id)
                except Exception as e:
                    skip_reason = f"Item {item.metadata.get('item_id')}: Embedding generation failed - {str(e)}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue

                from backend.embed_utils import get_embedding_dimension
                expected_dim = get_embedding_dimension(self.embedding_model_id)
                if vectors and len(vectors[0]) != expected_dim:
                    skip_reason = f"Item {item.metadata.get('item_id')}: Unexpected embedding dimension {len(vectors[0])}, expected {expected_dim}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                    self.index_progress["processed_items"] += 1
                    continue

                item_id = str(item.metadata.get('item_id'))
                chunk_ids = [f"{item_id}:{i}" for i in range(len(chunks))]

                meta_src = item.metadata
                title = meta_src.get("title") or ""
                authors = meta_src.get("authors") or ""
                tags = meta_src.get("tags") or ""
                collections = meta_src.get("collections") or ""
                item_type = meta_src.get("item_type") or ""
                
                # Parse year as integer (supports format like "2020-01-15" or just "2020")
                year_str = meta_src.get("date") or ""
                year = 0  # Default to 0 instead of None (ChromaDB doesn't accept None)
                if year_str:
                    match = re.search(r'\b(19|20)\d{2}\b', year_str)
                    if match:
                        year = int(match.group(0))
                
                pdf_path = meta_src.get("pdf_path") or ""

                metas = []
                for i, chunk_info in enumerate(chunks_with_pages):
                    metas.append({
                        "item_id": item_id,
                        "chunk_idx": int(i),
                        "title": title,
                        "authors": authors,
                        "tags": tags,
                        "collections": collections,
                        "item_type": item_type,
                        "year": year,  # Integer (0 if unknown)
                        "pdf_path": pdf_path,
                        "page": chunk_info.get('page', 0),  # Use 0 if page is None
                    })

                try:
                    self.chroma.add_chunks(
                        ids=chunk_ids,
                        documents=chunks,
                        metadatas=metas,
                        embeddings=vectors
                    )
                    print(f"SUCCESS: Indexed item {item_id} with {len(chunks)} chunks")
                except Exception as e:
                    skip_reason = f"Item {item_id}: Failed to add to ChromaDB - {str(e)}"
                    print(f"ERROR: {skip_reason}")
                    self.index_progress["skip_reasons"].append(skip_reason)
                
                # Update progress after processing this item (success or failure)
                self.index_progress["processed_items"] += 1
                
                # Calculate time estimates
                elapsed = time.time() - self.index_progress["start_time"]
                self.index_progress["elapsed_seconds"] = int(elapsed)
                
                processed = self.index_progress["processed_items"]
                total = self.index_progress["total_items"]
                if processed > 0 and total > 0:
                    avg_time_per_item = elapsed / processed
                    remaining_items = total - processed
                    self.index_progress["eta_seconds"] = int(avg_time_per_item * remaining_items)
                
                time.sleep(0)
            
            # Rebuild BM25 index after adding new chunks
            successful_items = self.index_progress["processed_items"] - len(self.index_progress.get("skip_reasons", []))
            if successful_items > 0:
                print(f"Rebuilding BM25 index after indexing {successful_items} items...")
                self.chroma.build_bm25_index()
            
            # Print summary
            print(f"\n=== Indexing Summary ===")
            print(f"Total items attempted: {self.index_progress['total_items']}")
            print(f"Successfully indexed: {successful_items}")
            print(f"Skipped/Failed: {len(self.index_progress.get('skip_reasons', []))}")
            
            # Check if ALL new items failed
            if successful_items == 0 and self.index_progress['total_items'] > 0:
                error_msg = f"All {self.index_progress['total_items']} new items failed to index. Common causes: PDFs not found (check storage path), network drive issues, or file permissions."
                print(f"FATAL ERROR: {error_msg}")
                self.index_progress["error"] = error_msg
            
            if self.index_progress.get('skip_reasons'):
                print(f"\nSkip reasons:")
                for reason in self.index_progress['skip_reasons'][:10]:  # Show first 10
                    print(f"  - {reason}")
                if len(self.index_progress['skip_reasons']) > 10:
                    print(f"  ... and {len(self.index_progress['skip_reasons']) - 10} more")
            print(f"========================\n")
        except Exception as e:
            # Catch any unexpected exceptions at thread level
            import traceback
            error_msg = f"Indexing crashed: {str(e)}"
            traceback_str = traceback.format_exc()
            print(f"FATAL ERROR: {error_msg}")
            print(f"Traceback:\n{traceback_str}")
            self.index_progress["error"] = error_msg
        finally:
            self.is_indexing = False
            self._cancel_indexing = False
    
    def start_indexing(self, incremental: bool = True):
        """Start indexing in a background thread. No-op if already indexing.
        
        Args:
            incremental: If True, only index new items. If False, reindex everything.
        """
        if self.is_indexing:
            return
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
        
        # Choose worker based on mode
        worker = self._index_library_incremental_worker if incremental else self._index_library_worker
        t = threading.Thread(target=worker, daemon=True)
        self._index_thread = t
        t.start()

    def cancel_indexing(self):
        """Signal cancellation for the running indexing job."""
        if not self.is_indexing:
            return
        self._cancel_indexing = True

    def chunk_text(self, text, chunk_size=800, overlap=200):
        """Improved chunking with semantic boundary awareness.
        
        Best practices for academic documents:
        - Larger chunks (600-1000 tokens) preserve context better for research papers
        - Higher overlap (150-250 tokens) ensures key concepts aren't split
        - Try to break at sentence boundaries when possible
        """
        if not text:
            return []
        
        # Split into sentences first (naive approach)
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # If adding this sentence keeps us under chunk_size, add it
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence + " "
            else:
                # Save current chunk if it's not empty
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # Start new chunk
                # Include overlap from previous chunk
                if chunks and overlap > 0:
                    prev_words = current_chunk.split()
                    overlap_words = prev_words[-overlap//5:]  # rough word-based overlap
                    current_chunk = " ".join(overlap_words) + " " + sentence + " "
                else:
                    current_chunk = sentence + " "
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def chunk_text_with_pages(self, pages_data, chunk_size=800, overlap=200):
        """Chunk text while preserving page number information.
        
        Args:
            pages_data: List of dicts with 'page_num' and 'text' keys
            chunk_size: Target chunk size in characters
            overlap: Overlap between chunks in characters
            
        Returns:
            List of dicts with 'text' and 'page' keys
        """
        import re
        
        chunks_with_pages = []
        
        for page_data in pages_data:
            page_num = page_data['page_num']
            text = page_data['text']
            
            if not text.strip():
                continue
            
            # Split into sentences
            sentences = re.split(r'(?<=[.!?])\s+', text)
            
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= chunk_size:
                    current_chunk += sentence + " "
                else:
                    # Save current chunk
                    if current_chunk.strip():
                        chunks_with_pages.append({
                            'text': current_chunk.strip(),
                            'page': page_num
                        })
                    
                    # Start new chunk with overlap
                    if overlap > 0 and current_chunk:
                        prev_words = current_chunk.split()
                        overlap_words = prev_words[-overlap//5:]
                        current_chunk = " ".join(overlap_words) + " " + sentence + " "
                    else:
                        current_chunk = sentence + " "
            
            # Add final chunk from this page
            if current_chunk.strip():
                chunks_with_pages.append({
                    'text': current_chunk.strip(),
                    'page': page_num
                })
        
        return chunks_with_pages

    def build_search_prompt(self, user_query: str) -> str:
        """Build an enhanced search query using query expansion.
        
        Best practice: Transform natural questions into search-optimized queries
        that better match academic content.
        """
        base = user_query.strip()
        # Keep the original query for semantic matching
        # The embedding model will handle the expansion naturally
        return base

    def build_answer_prompt(self, question: str, snippets: list[dict]) -> str:
        """
        Build an optimized prompt for academic question answering.
        
        Uses 2025 best practices for citation-aware RAG prompting.
        Delegates to AcademicPrompts module for consistent formatting.
        """
        return AcademicPrompts.build_answer_prompt(
            question=question,
            snippets=snippets,
            include_reasoning=True  # Enable chain-of-thought for complex questions
        )

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
            use_rrf: Whether to use RRF hybrid search (default True)
            
        Returns:
            Dictionary with summary, citations, and snippets
        """
        # STEP 1: Load conversation history
        conversation_history = []
        is_new_session = False
        user_turns = 0
        
        print("\n" + "="*80)
        print(f"CHAT TURN START: query='{query[:80]}...'")
        print("="*80)
        
        if session_id:
            conversation_history = self.conversation_store.get_messages(
                session_id, 
                provider_id=self.provider_manager.active_provider_id
            )
            user_turns = len([m for m in conversation_history if m.role == "user"])
            is_new_session = (user_turns == 0)
            print(f"Session {session_id}: user_turns={user_turns}, is_new={is_new_session}")
            print(f"History has {len(conversation_history)} messages total")
        
        # STEP 2: CONDENSE query if it's a follow-up
        # This is the critical step missing from your original implementation!
        retrieval_query = query  # Default to original
        
        if session_id and self.query_condenser.should_condense(query, conversation_history):
            print("\nCONDENSATION: Detected follow-up question")
            retrieval_query = self.query_condenser.condense_query(
                query=query,
                conversation_history=conversation_history,
                max_history_chars=1500
            )
            print(f"   Original query: '{query}'")
            print(f"   Condensed query: '{retrieval_query}'")
        else:
            print(f"\nCONDENSATION: Skipped (is_new_session={is_new_session}, turns={user_turns})")
            print(f"   Using original query: '{query}'")
        
        # STEP 3: RETRIEVE using the standalone/condensed query
        # Build metadata filter if enabled
        metadata_where = None
        if use_metadata_filters or manual_filters:
            from backend.metadata_extractor import extract_metadata_filters
            from backend.metadata_utils import build_metadata_where_clause, merge_where_clauses
            
            # Extract from query if enabled
            if use_metadata_filters:
                extracted = extract_metadata_filters(retrieval_query, self.provider_manager)
                if extracted["has_filters"]:
                    metadata_where = build_metadata_where_clause(
                        year_min=extracted.get("year_min"),
                        year_max=extracted.get("year_max"),
                        tags=extracted.get("tags"),
                        collections=extracted.get("collections"),
                        title=extracted.get("title"),
                        author=extracted.get("author"),
                        item_types=extracted.get("item_types"),
                    )
                    print(f"\nMETADATA FILTERS (extracted): {extracted}")
            
            # Apply manual filters if provided
            if manual_filters:
                manual_where = build_metadata_where_clause(
                    year_min=manual_filters.get("year_min"),
                    year_max=manual_filters.get("year_max"),
                    tags=manual_filters.get("tags"),
                    collections=manual_filters.get("collections"),
                    title=manual_filters.get("title"),
                    author=manual_filters.get("author"),
                    item_types=manual_filters.get("item_types"),
                )
                metadata_where = merge_where_clauses(metadata_where, manual_where)
                print(f"\nMETADATA FILTERS (manual): {manual_filters}")
        
        # Combine with item_id filter
        item_id_where = {"item_id": {"$in": filter_item_ids}} if filter_item_ids else None
        from backend.metadata_utils import merge_where_clauses
        db_filter = merge_where_clauses(item_id_where, metadata_where)
        
        if db_filter:
            print(f"\nFINAL WHERE CLAUSE: {db_filter}")
        
        # Use hybrid search (dense + sparse) for best results
        search_prompt = self.build_search_prompt(retrieval_query)  # Use condensed query!

        # Get dynamic retrieval limits based on model's context window
        is_focused_query_prelim = db_filter is not None
        limits = self.get_retrieval_limits(is_focused=is_focused_query_prelim, max_sources_override=max_sources)
        retrieval_k = limits["retrieval_k"]
        rerank_top_k = limits["rerank_top_k"]

        if use_rrf:
            # Use RRF hybrid search for better fusion
            results = self.chroma.query_hybrid_rrf(
                query=search_prompt,
                k=retrieval_k,
                where=db_filter,
                embedding_model_id=self.embedding_model_id,
            ) or {}
        else:
            # Use traditional hybrid search
            results = self.chroma.query_hybrid(
                query=search_prompt,
                k=retrieval_k,
                where=db_filter,
                embedding_model_id=self.embedding_model_id
            ) or {}

        docs_outer = results.get("documents", [[]])
        metas_outer = results.get("metadatas", [[]])
        docs = docs_outer[0] if docs_outer else []
        metas = metas_outer[0] if metas_outer else []

        # Fallback: if auto-extracted filter produced zero results, retry without it.
        # Manual filters are intentional, so we don't fall back for those.
        if not docs and db_filter is not None and use_metadata_filters and not manual_filters:
            print(f"\nFALLBACK: auto-extracted filter returned 0 results — retrying unfiltered")
            fallback_fn = self.chroma.query_hybrid_rrf if use_rrf else self.chroma.query_hybrid
            fallback_results = fallback_fn(
                query=search_prompt,
                k=15,
                where=None,
                embedding_model_id=self.embedding_model_id,
            ) or {}
            docs = (fallback_results.get("documents", [[]])[0]) or []
            metas = (fallback_results.get("metadatas", [[]])[0]) or []

        # RE-RANK using cross-encoder for better relevance
        if docs:
            ranked = rerank_passages(retrieval_query, docs, top_k=rerank_top_k)  # Use condensed query for ranking!
            docs = [docs[idx] for idx, score in ranked]
            metas = [metas[idx] for idx, score in ranked]

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

        # Build snippets and citation map with page numbers
        snippets = []
        citation_map = OrderedDict()
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

            if key not in citation_map:
                citation_map[key] = len(citation_map) + 1

            cid = citation_map[key]
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

        # Build citations list
        citation_to_authors = {}
        for s in snippets:
            key = (s["title"], s["year"], s["pdf_path"])
            if key not in citation_to_authors:
                citation_to_authors[key] = s["authors"]
        
        citations = [
            {
                "id": cid,
                "title": title,
                "year": year,
                "authors": citation_to_authors.get((title, year, pdf_path), ""),
                "pdf_path": pdf_path,
            }
            for (title, year, pdf_path), cid in citation_map.items()
        ]

        # STEP 4: BUILD MESSAGES
        # Critical: For follow-ups, append ONLY the question (no embedded RAG context)
        # The conversation history already contains the system prompt and prior context
        
        print(f"\nMESSAGE CONSTRUCTION: is_new_session={is_new_session}, snippets={len(snippets)}")
        
        if session_id:
            # Determine message type based on turn number and snippet availability
            if is_new_session:
                # First turn: include full RAG context in user message
                if snippets:
                    user_message = self._build_first_turn_message(query, snippets)
                    print(f"   Building FIRST turn message with {len(snippets)} snippets embedded")
                    print(f"   Message length: {len(user_message)} chars")
                else:
                    user_message = query
                    print("   Building FIRST turn message (no snippets)")
            else:
                # Follow-up turn: inject fresh evidence so the model can satisfy
                # its grounding instruction ("use only the provided context").
                # Without evidence here, the model receives no context but the
                # system prompt says "use only provided context" — on GPT-4o
                # this causes it to generate a new question instead of an answer
                # (root cause of issue #35).
                #
                # Use build_hybrid_user_message (not build_rag_user_message):
                # the hybrid variant frames the content as supplementary evidence
                # for a follow-up, not as a fresh first-turn RAG query.
                if snippets:
                    user_message = AcademicPrompts.build_hybrid_user_message(query, snippets)
                    print(f"   Building FOLLOW-UP turn #{user_turns + 1} with {len(snippets)} snippets embedded")
                    print(f"   Message length: {len(user_message)} chars")
                else:
                    user_message = AcademicPrompts.build_plain_user_message(query)
                    print(f"   Building FOLLOW-UP turn #{user_turns + 1} (no snippets, answering from history)")
                    print(f"   Message length: {len(user_message)} chars")
            
            # Append user message to history
            self.conversation_store.append_message(session_id, "user", user_message)
            
            # Get updated history and trim for context window
            full_history = self.conversation_store.get_messages(
                session_id,
                provider_id=self.provider_manager.active_provider_id
            )
            print(f"\nFULL HISTORY before trim: {len(full_history)} messages")
            for i, msg in enumerate(full_history):
                preview = msg.content[:100].replace('\n', ' ')
                print(f"   [{i}] {msg.role:10s}: {preview}...")
            
            messages = self.conversation_store.trim_messages_for_context(
                full_history, 
                max_messages=20,  # Last 10 turns
                max_chars=self._get_context_char_budget()
            )
            
            # Log the actual messages being sent to LLM
            print(f"\nMESSAGES TO LLM: {len(messages)} messages")
            for i, msg in enumerate(messages):
                content_preview = msg.content[:150].replace('\n', ' ') + ('...' if len(msg.content) > 150 else '')
                print(f"   [{i}] {msg.role:10s}: {content_preview}")
        else:
            # Fallback: single-turn conversation (backward compatibility)
            print("   Building SINGLE-TURN message (no session)")
            prompt = self.build_answer_prompt(query, snippets)
            messages = [Message(role="user", content=prompt)]
        
        # STEP 5: GENERATE answer using LLM
        gen_params = AcademicGenerationParams.get_params("standard")
        
        print(f"\nLLM GENERATION: Calling provider with temp={gen_params['temperature']}")
        
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
            import re
            think_pattern = r'<think>(.*?)</think>'
            think_matches = re.findall(think_pattern, raw_content, re.DOTALL)
            
            if think_matches:
                # Extract the thinking content
                reasoning_content = '\n\n'.join(think_matches).strip()
                # Remove the <think> tags from the main response
                summary = re.sub(think_pattern, '', raw_content, flags=re.DOTALL).strip()
                print(f"\nEXTRACTED REASONING: ({len(reasoning_content)} chars)")
                print(f"   First 200 chars: {reasoning_content[:200].replace(chr(10), ' ')}...")
            else:
                summary = raw_content
            
            print(f"\nLLM RESPONSE received ({len(summary)} chars)")
            print(f"   First 200 chars: {summary[:200].replace(chr(10), ' ')}...")
            
            # Validate response for common failure patterns
            is_valid, issues = ResponseValidator.validate_chat_response(
                response, 
                self.provider_manager.active_provider_id
            )
            
            if not is_valid:
                logger.warning(
                    f"Provider {self.provider_manager.active_provider_id} failed validation: {issues}"
                )
                print(f"\nWARNING: Response validation failed with {len(issues)} issues:")
                for issue in issues:
                    print(f"   - {issue}")
                
                # Log specific patterns for debugging
                if "Meta-response detected" in issues:
                    logger.warning(
                        f"Meta-response detected for provider {self.provider_manager.active_provider_id}. "
                        "Instructions may have been embedded in user message."
                    )
                    print("    This indicates instructions were embedded in the user message.")
                    print("    The model acknowledged instructions instead of answering.")
                
                if "Raw citations detected" in issues:
                    logger.warning(
                        f"Raw citations detected for provider {self.provider_manager.active_provider_id}. "
                        "Web search may have been activated instead of using provided context."
                    )
                    print("    Perplexity returned search results instead of answer.")
                    print("    This may indicate web search mode was activated instead of using provided context.")
                    print("    Consider switching to a different model provider for RAG over private documents.")
            
            # Save assistant response to conversation history
            if session_id:
                self.conversation_store.append_message(session_id, "assistant", summary)
        except ProviderRateLimitError as e:
            # Specific handling for rate limit errors
            print(f"\n{'='*80}")
            print(f"RATE LIMIT ERROR")
            print(f"{'='*80}")
            print(f"Provider: {self.provider_manager.active_provider_id}")
            print(f"Error message: {str(e)}")
            print(f"{'='*80}\n")
            
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
            print(f"\n{'='*80}")
            print(f"AUTHENTICATION ERROR")
            print(f"{'='*80}")
            print(f"Provider: {self.provider_manager.active_provider_id}")
            print(f"Error message: {str(e)}")
            print(f"{'='*80}\n")
            
            provider_name = self.provider_manager.active_provider_id.title()
            summary = (
                f"{provider_name} Authentication Failed\n\n"
                f"Your API key appears to be invalid or has expired. "
                f"Please check your API key in Settings and ensure it's correct."
            )
        except ProviderContextError as e:
            # Specific handling for context length errors
            print(f"\n{'='*80}")
            print(f"CONTEXT LENGTH ERROR")
            print(f"{'='*80}")
            print(f"Provider: {self.provider_manager.active_provider_id}")
            print(f"Model: {self.provider_manager.get_active_model()}")
            print(f"Error message: {str(e)}")
            print(f"{'='*80}\n")
            
            model_name = self.provider_manager.get_active_model()
            summary = (
                f"Context Too Long\n\n"
                f"The conversation history and retrieved documents exceed the maximum context length "
                f"for {model_name}. Try starting a new chat session or selecting a model with a larger "
                f"context window."
            )
        except Exception as e:
            print(f"\n{'='*80}")
            print(f"LLM GENERATION ERROR")
            print(f"{'='*80}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            print(f"{'='*80}\n")
            
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

        # STEP 6: Generate session title for new sessions
        generated_title = None
        if session_id and is_new_session:
            generated_title = self.generate_session_title(query, summary)
            print(f"Generated session title: {generated_title}")

        print("\n" + "="*80)
        print(f"CHAT TURN COMPLETE")
        print(f"   Citations: {len(citations)}, Snippets: {len(snippets)}")
        print(f"   Reasoning: {'Yes' if reasoning_content else 'No'}")
        print("="*80 + "\n")

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
    
    def _build_first_turn_message(self, question: str, snippets: list[dict]) -> str:
        """Build first turn message with embedded RAG context."""
        if not snippets:
            return question
        
        # Build compact context
        context_blocks = []
        for s in snippets:
            cid = s.get("citation_id", "?")
            title = s.get("title", "Untitled")
            year = s.get("year", "")
            authors = s.get("authors", "Unknown")
            text = s.get("snippet", "")
            page = s.get("page")
            
            bib = f"{authors} ({year})" if year else authors
            page_info = f", p. {page}" if page else ""
            context_blocks.append(f"[{cid}] {title}{page_info}\n{bib}\n{text}")
        
        context = "\n\n".join(context_blocks)
        
        return f"""{question}

---
**Evidence from library:**

{context}"""
    
    def _build_new_evidence_note(self, snippets: list[dict]) -> str:
        """Build a note about new evidence for follow-up turns."""
        if not snippets:
            return ""
        
        # Compact format: just show what's new
        items = []
        for s in snippets[:4]:  # Top 4 snippets only
            cid = s.get("citation_id", "?")
            title = s.get("title", "Untitled")
            year = s.get("year", "")
            text = s.get("snippet", "")[:200]  # Truncate
            items.append(f"[{cid}] {title} ({year}): {text}...")
        
        return f"""Additional evidence retrieved:

{chr(10).join(items)}"""
    
    def build_contextual_user_message(self, question: str, snippets: list[dict]) -> str:
        """
        Build a user message that combines the question with RAG context.
        
        Uses 2025 best practices for embedding context in conversational flow.
        Delegates to AcademicPrompts module for consistent formatting.
        
        Args:
            question: The user's raw question
            snippets: Retrieved snippets from the library
            
        Returns:
            Formatted message with question and context
        """
        return AcademicPrompts.build_contextual_user_message(
            question=question,
            snippets=snippets
        )
    
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
            print(f"Generating title for question: {user_question[:100]}")
            
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
            print(f"Raw title from LLM: '{title}'")
            # Remove quotes if present
            title = title.strip('"').strip("'")
            # Limit length
            if len(title) > 80:
                title = title[:77] + "..."
            
            print(f"Cleaned title: '{title}'")
            return title if title else user_question[:50]
        except Exception as e:
            print(f"Title generation error: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to first few words of question
            return user_question[:50]


