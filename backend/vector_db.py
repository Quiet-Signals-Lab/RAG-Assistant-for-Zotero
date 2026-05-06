#vector_db.py
import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Any, Iterable, Optional
from rank_bm25 import BM25Okapi
import pickle
import numpy as np

class ChromaClient:
    """
    Administers user interactions with the Chroma vector database for Zotero library items.
    Supports persistent per-library DB, bulk chunk addition, semantic querying, and sync with Zotero snapshot.
    
    IMPORTANT: This class expects pre-computed embeddings and does NOT use ChromaDB's 
    default embedding function. All embeddings must be generated using get_embedding() 
    from embed_utils.py to ensure consistent dimensional vectors.
    
    Each embedding model gets its own collection to prevent dimension mismatch errors.
    """

    def __init__(self, db_path: str, collection_name: str = "zotero_lib", embedding_model_id: str = "bge-base"):
        self.db_path = db_path
        self.embedding_model_id = embedding_model_id
        # Include embedding model in collection name to avoid dimension conflicts.
        # Replace ':' with '-' so cloud model IDs (e.g. "openai:text-embedding-3-small")
        # produce valid ChromaDB collection names.
        safe_model_id = embedding_model_id.replace(":", "-")
        self.collection_name = f"{collection_name}_{safe_model_id}"
        os.makedirs(self.db_path, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=self.db_path, settings=Settings())
        
        # Create collection WITHOUT an embedding function (we provide embeddings manually)
        # This prevents ChromaDB from using its default all-MiniLM-L6-v2 (384 dims)
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",  # Use cosine similarity for retrieval
                "embedding_model": embedding_model_id  # Track which model created this collection
            }
        )
        
        # BM25 index for sparse retrieval (loaded lazily)
        # Each embedding model has its own BM25 index
        self.bm25_index = None
        self.bm25_corpus = None
        self.bm25_ids = None
        self.bm25_path = os.path.join(self.db_path, f"bm25_index_{embedding_model_id}.pkl")

    def add_chunks(self,
        ids: List[str],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """
        Bulk-adds document chunks and their vectors to the Chroma collection.
        """
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def query_db(self,
        query: str,
        k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query the vector DB with a natural-language question.
        Optionally filter by metadata keys (e.g. item_id).
        
        CRITICAL: Manually embeds the query using get_embedding() to ensure
        consistent 768-dimensional embeddings. DO NOT use query_texts parameter
        as it would trigger ChromaDB's default embedding function.
        """
        from backend.embed_utils import get_embedding
        
        # Manually embed query to ensure consistent dimensions
        query_embedding = get_embedding(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],  # Use query_embeddings, not query_texts!
            n_results=k,
            where=where,
        )
        return results
    
    def query_bm25(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """Query using BM25 sparse retrieval.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of dicts with 'id', 'score', 'document', and 'metadata'
        """
        if self.bm25_index is None:
            self._load_bm25_index()
        
        if self.bm25_index is None:
            return []  # No BM25 index available
        
        # Tokenize query (simple whitespace tokenization)
        query_tokens = query.lower().split()
        
        # Get BM25 scores
        scores = self.bm25_index.get_scores(query_tokens)
        
        # Get top k indices
        top_indices = np.argsort(scores)[::-1][:k]
        
        # Retrieve documents from ChromaDB
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # Only include results with positive scores
                doc_id = self.bm25_ids[idx]
                # Get full document and metadata from ChromaDB
                chroma_result = self.collection.get(ids=[doc_id])
                if chroma_result['ids']:
                    results.append({
                        'id': doc_id,
                        'score': float(scores[idx]),
                        'document': chroma_result['documents'][0],
                        'metadata': chroma_result['metadatas'][0]
                    })
        
        return results
    
    def query_hybrid(self, query: str, k: int = 10, where: Optional[Dict[str, Any]] = None, embedding_model_id: str = "bge-base") -> Dict[str, Any]:
        """Hybrid search combining dense (semantic) and sparse (BM25) retrieval.
        
        Best practice from Reddit thread: Retrieve top-k from both methods,
        create a union, then re-rank using cross-encoder.
        
        Args:
            query: Search query
            k: Number of results from each method
            where: Optional metadata filter (may contain unsupported $contains)
            embedding_model_id: ID of the embedding model to use (default: "bge-base")
            
        Returns:
            Combined results dict with documents, metadatas, and distances
        """
        from backend.embed_utils import get_embedding
        from backend.metadata_utils import separate_where_clauses, apply_client_side_filters
        
        # Separate ChromaDB-compatible and client-side filters
        chroma_where, client_where = separate_where_clauses(where)
        
        # Embed query using the configured embedding model
        query_embedding = get_embedding(query, model_id=embedding_model_id)
        
        # Get dense retrieval results with ChromaDB-compatible filters only
        dense_results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],  # Use query_embeddings, not query_texts!
            n_results=k * 2 if client_where else k,  # Get more if we'll filter client-side
            where=chroma_where,  # Only ChromaDB-compatible filters
        )
        
        # Apply client-side filters ($contains) to dense results
        if client_where:
            dense_results = apply_client_side_filters(dense_results, client_where)
        
        # Get sparse retrieval results
        bm25_results = self.query_bm25(query, k=k)
        
        # Combine results (union of document IDs)
        seen_ids = set()
        combined_docs = []
        combined_metas = []
        combined_ids = []
        
        # Add dense results
        if dense_results['ids'] and dense_results['ids'][0]:
            for i, doc_id in enumerate(dense_results['ids'][0]):
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    combined_ids.append(doc_id)
                    combined_docs.append(dense_results['documents'][0][i])
                    combined_metas.append(dense_results['metadatas'][0][i])
        
        # Add BM25 results not already included, with client-side filtering if needed
        for result in bm25_results:
            if result['id'] not in seen_ids:
                # Apply client-side filter to BM25 results too
                if client_where and not self._matches_where_clause(result['metadata'], client_where):
                    continue
                seen_ids.add(result['id'])
                combined_ids.append(result['id'])
                combined_docs.append(result['document'])
                combined_metas.append(result['metadata'])
        
        # Format as ChromaDB-style result
        return {
            'ids': [combined_ids],
            'documents': [combined_docs],
            'metadatas': [combined_metas],
            'distances': [[0.0] * len(combined_ids)]  # Placeholder, will be re-ranked
        }
    
    def query_hybrid_rrf(
        self,
        query: str,
        k: int = 10,
        where: Optional[Dict[str, Any]] = None,
        embedding_model_id: str = "bge-base",
        rrf_k: int = 60,
    ) -> Dict[str, Any]:
        """
        Hybrid search with Reciprocal Rank Fusion (RRF).
        
        RRF provides better fusion than simple union by considering rank positions.
        Formula: score(d) = Σ 1/(k + rank_i(d)) for each ranking system i
        
        Args:
            query: Search query
            k: Number of results to return
            where: Optional metadata filter clause (may contain unsupported $contains)
            embedding_model_id: Embedding model ID
            rrf_k: RRF constant (typically 60, controls rank influence)
        
        Returns:
            Combined results dict with RRF-scored documents
        """
        from backend.embed_utils import get_embedding
        from backend.metadata_utils import separate_where_clauses, apply_client_side_filters
        
        # Separate ChromaDB-compatible and client-side filters
        chroma_where, client_where = separate_where_clauses(where)
        
        # Get dense (semantic) results with ChromaDB-compatible filters only
        query_embedding = get_embedding(query, model_id=embedding_model_id)
        dense_results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k * 3 if client_where else k * 2,  # Retrieve more for better fusion and filtering
            where=chroma_where,  # Only ChromaDB-compatible filters
        )
        
        # Apply client-side filters ($contains) to dense results
        if client_where:
            dense_results = apply_client_side_filters(dense_results, client_where)
        
        # Get sparse (BM25) results
        bm25_results = self.query_bm25(query, k=k * 3 if client_where else k * 2)
        
        # Apply metadata filter to BM25 results if specified
        if chroma_where:
            bm25_results = self._filter_bm25_results(bm25_results, chroma_where)
        
        # Apply client-side filters to BM25 results
        if client_where:
            bm25_results = [r for r in bm25_results if self._matches_where_clause(r['metadata'], client_where)]
        
        # Calculate RRF scores
        rrf_scores = {}
        
        # Add dense rankings
        if dense_results['ids'] and dense_results['ids'][0]:
            for rank, doc_id in enumerate(dense_results['ids'][0]):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (rrf_k + rank + 1)
        
        # Add BM25 rankings
        for rank, result in enumerate(bm25_results):
            doc_id = result['id']
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (rrf_k + rank + 1)
        
        # Sort by RRF score (descending)
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:k]
        
        # Retrieve full documents for top-k IDs
        if not sorted_ids:
            return {
                'ids': [[]],
                'documents': [[]],
                'metadatas': [[]],
                'distances': [[]]
            }
        
        final_results = self.collection.get(
            ids=sorted_ids,
            include=['documents', 'metadatas']
        )
        
        # Maintain RRF score order
        id_to_idx = {doc_id: i for i, doc_id in enumerate(final_results['ids'])}
        ordered_docs = []
        ordered_metas = []
        ordered_scores = []
        
        for doc_id in sorted_ids:
            idx = id_to_idx.get(doc_id)
            if idx is not None:
                ordered_docs.append(final_results['documents'][idx])
                ordered_metas.append(final_results['metadatas'][idx])
                ordered_scores.append(rrf_scores[doc_id])
        
        return {
            'ids': [sorted_ids],
            'documents': [ordered_docs],
            'metadatas': [ordered_metas],
            'distances': [[1 - score for score in ordered_scores]]  # Convert to distance
        }
    
    def _filter_bm25_results(self, results: List[Dict], where: Dict[str, Any]) -> List[Dict]:
        """Filter BM25 results by metadata constraints."""
        filtered = []
        
        for result in results:
            metadata = result.get('metadata', {})
            if self._matches_where_clause(metadata, where):
                filtered.append(result)
        
        return filtered
    
    def _matches_where_clause(self, metadata: Dict[str, Any], where: Dict[str, Any]) -> bool:
        """Check if metadata matches a where clause."""
        # Simple implementation - can be extended for complex clauses
        for key, condition in where.items():
            if key == "$and":
                # All conditions must match
                return all(self._matches_where_clause(metadata, c) for c in condition)
            elif key == "$or":
                # Any condition must match
                return any(self._matches_where_clause(metadata, c) for c in condition)
            elif key == "$not":
                # Condition must not match
                return not self._matches_where_clause(metadata, condition)
            elif isinstance(condition, dict):
                # Field condition (e.g., {"year": {"$gte": 2020}})
                field_value = metadata.get(key)
                if field_value is None:
                    return False
                
                for op, target in condition.items():
                    if op == "$eq":
                        if field_value != target:
                            return False
                    elif op == "$ne":
                        if field_value == target:
                            return False
                    elif op == "$gt":
                        if not (field_value > target):
                            return False
                    elif op == "$gte":
                        if not (field_value >= target):
                            return False
                    elif op == "$lt":
                        if not (field_value < target):
                            return False
                    elif op == "$lte":
                        if not (field_value <= target):
                            return False
                    elif op == "$contains":
                        if target not in str(field_value):
                            return False
                    elif op == "$in":
                        if field_value not in target:
                            return False
                    elif op == "$nin":
                        if field_value in target:
                            return False
            else:
                # Direct equality check
                if metadata.get(key) != condition:
                    return False
        
        return True
    
    def _load_bm25_index(self):
        """Load BM25 index from disk if it exists."""
        if os.path.exists(self.bm25_path):
            try:
                with open(self.bm25_path, 'rb') as f:
                    data = pickle.load(f)
                    self.bm25_index = data['index']
                    self.bm25_corpus = data['corpus']
                    self.bm25_ids = data['ids']
            except Exception as e:
                print(f"Error loading BM25 index: {e}")
                self.bm25_index = None
    
    def _save_bm25_index(self):
        """Save BM25 index to disk."""
        if self.bm25_index is not None:
            try:
                with open(self.bm25_path, 'wb') as f:
                    pickle.dump({
                        'index': self.bm25_index,
                        'corpus': self.bm25_corpus,
                        'ids': self.bm25_ids
                    }, f)
            except Exception as e:
                print(f"Error saving BM25 index: {e}")
    
    def build_bm25_index(self):
        """Build BM25 index from all documents in ChromaDB."""
        # Get all documents from ChromaDB
        total_count = self.collection.count()
        
        if total_count == 0:
            print("No documents in collection to index")
            return
        
        all_docs = self.collection.get(limit=total_count)
        
        if not all_docs['ids']:
            print("No documents in collection to index")
            return
        
        # Tokenize documents (simple whitespace tokenization)
        corpus = []
        for doc in all_docs['documents']:
            tokens = doc.lower().split()
            corpus.append(tokens)
        
        # Build BM25 index
        self.bm25_corpus = corpus
        self.bm25_ids = all_docs['ids']
        self.bm25_index = BM25Okapi(corpus)
        
        # Save index
        self._save_bm25_index()
        print(f"BM25 index built with {len(corpus)} documents")

    def sync_db(self,
        items: Iterable[Any],  
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        embed_fn=None,
    ) -> None:
        """
        Syncs the Chroma DB with the current ZoteroItem snapshot.
        Indexes and chunks text, embeds with supplied function, and stores metadata.
        """

        def chunk_text(t: str, size: int, overlap: int) -> List[str]:
            chunks = []
            start = 0
            n = len(t)
            while start < n:
                end = min(n, start + size)
                chunks.append(t[start:end])
                if end == n:
                    break
                start = end - overlap
            return chunks

        ids: List[str] = []
        docs: List[str] = []
        metas: List[Dict[str, Any]] = []
        embeddings: List[List[float]] = []

        for item in items:
            text = getattr(item, "metadata", {}).get("text") or item.get("text") if isinstance(item, dict) else None
            item_id = getattr(item, "metadata", {}).get("item_id") or item.get("item_id") if isinstance(item, dict) else None
            if not text or not item_id:
                continue
            chunks = chunk_text(text, chunk_size, chunk_overlap)
            meta_src = getattr(item, "metadata", {}) if hasattr(item, "metadata") else item
            ids_batch = []
            docs_batch = []
            metas_batch = []
            for idx, ch in enumerate(chunks):
                doc_id = f"{str(item_id)}:{str(idx)}"
                ids_batch.append(doc_id)
                docs_batch.append(ch)

                title = meta_src.get("title") or ""
                authors = meta_src.get("authors") or ""
                tags = meta_src.get("tags") or ""
                collections = meta_src.get("collections") or ""
                year = meta_src.get("date") or ""
                pdf_path = meta_src.get("pdf_path") or ""

                metas_batch.append({
                    "item_id": str(item_id),
                    "chunk_idx": int(idx),
                    "title": title,
                    "authors": authors,
                    "tags": tags,
                    "collections": collections,
                    "year": year,
                    "pdf_path": pdf_path,
                })
            ids += ids_batch
            docs += docs_batch
            metas += metas_batch
            # ----- Embed batch -----
            if embed_fn is not None and docs_batch:
                embeddings += self.embed_chunks(docs_batch, embed_fn)
        if ids:
            print("ID types:", set(type(i) for i in ids))
            self.add_chunks(
                ids=[str(i) for i in ids],
                documents=docs,
                metadatas=metas,
                embeddings=embeddings if embed_fn is not None else None
            )

    def get_or_create_db(self):
        """
        Ensures the collection exists and is initialized.
        IMPORTANT: Creates collection without embedding function (manual embeddings only).
        """
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    def count_items_matching_filters(
        self,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        tags: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
        item_types: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Count how many unique items and chunks match the given filters.
        
        This is used for the Scope panel to show an estimate of filtered items.
        
        Args:
            year_min: Minimum year filter
            year_max: Maximum year filter
            tags: List of tags to match
            collections: List of collections to match
            title: Title substring to match
            author: Author substring to match
            item_types: List of item types to match
        
        Returns:
            Dict with 'unique_items' and 'total_chunks' counts
        """
        from backend.metadata_utils import build_metadata_where_clause, separate_where_clauses
        
        # Build where clause
        where = build_metadata_where_clause(
            year_min=year_min,
            year_max=year_max,
            tags=tags,
            collections=collections,
            title=title,
            author=author,
            item_types=item_types,
        )
        
        if where is None:
            # No filters - count everything
            total_count = self.collection.count()
            all_results = self.collection.get(limit=total_count if total_count > 0 else 1, include=['metadatas'])
            unique_items = len({str(m.get('item_id')) for m in all_results.get('metadatas', [])})
            return {
                'unique_items': unique_items,
                'total_chunks': len(all_results.get('ids', []))
            }
        
        # Separate ChromaDB-compatible and client-side filters
        chroma_where, client_where = separate_where_clauses(where)
        
        # Get total count to ensure we fetch all documents
        total_count = self.collection.count()
        
        # Get all results matching ChromaDB filters (specify limit to get all)
        if chroma_where:
            results = self.collection.get(where=chroma_where, limit=total_count if total_count > 0 else 1, include=['metadatas'])
        else:
            # No ChromaDB filters, get everything
            results = self.collection.get(limit=total_count if total_count > 0 else 1, include=['metadatas'])
        
        # Apply client-side filtering if needed
        if client_where:
            metadatas = results.get('metadatas', [])
            filtered_metas = [m for m in metadatas if self._matches_where_clause(m, client_where)]
        else:
            filtered_metas = results.get('metadatas', [])
        
        # Count unique items
        unique_items = len({str(m.get('item_id')) for m in filtered_metas if m.get('item_id')})
        
        return {
            'unique_items': unique_items,
            'total_chunks': len(filtered_metas)
        }
    
    def get_indexed_item_ids(self) -> set:
        """
        Get all unique item IDs that are currently indexed in the database.
        
        Returns:
            Set of item_id strings (always converted to strings for consistency)
        """
        # Get total count first to ensure we fetch ALL documents
        # ChromaDB's get() has a default limit, so we must specify a sufficient limit
        total_count = self.collection.count()
        
        if total_count == 0:
            return set()
        
        # Get all documents with their metadata (specify limit to get ALL docs)
        all_data = self.collection.get(
            limit=total_count,
            include=['metadatas']
        )
        
        if not all_data['metadatas']:
            return set()
        
        # Extract unique item_ids from metadata
        # IMPORTANT: Always convert to string for consistent comparison with Zotero IDs
        item_ids = set()
        for metadata in all_data['metadatas']:
            if metadata and 'item_id' in metadata:
                item_ids.add(str(metadata['item_id']))
        
        return item_ids
    
    def item_exists(self, item_id: str) -> bool:
        """
        Check if an item is already indexed in the database.
        
        Args:
            item_id: The Zotero item ID to check
            
        Returns:
            True if item exists, False otherwise
        """
        # Query for any chunk with this item_id
        results = self.collection.get(
            where={"item_id": str(item_id)},
            limit=1
        )
        return len(results['ids']) > 0
    
    def get_item_metadata(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for an indexed item.
        
        Args:
            item_id: The Zotero item ID
            
        Returns:
            Metadata dict or None if not found
        """
        results = self.collection.get(
            where={"item_id": str(item_id)},
            limit=1
        )
        
        if results['metadatas']:
            return results['metadatas'][0]
        return None
    
    def delete_item(self, item_id: str) -> int:
        """
        Delete all chunks associated with an item from the database.
        
        Args:
            item_id: The Zotero item ID to delete
            
        Returns:
            Number of chunks deleted
        """
        # Get all chunk IDs for this item
        # Use high limit to ensure we get all chunks for this item
        total_count = self.collection.count()
        results = self.collection.get(
            where={"item_id": str(item_id)},
            limit=total_count if total_count > 0 else 1
        )
        
        if results['ids']:
            self.collection.delete(ids=results['ids'])
            return len(results['ids'])
        return 0

    def embed_chunks(self, chunks: List[str], embed_fn) -> List[List[float]]:
        """
        Passes a list of text chunks through the embedding function and returns their vectors.
        """
        embeddings = [embed_fn(chunk) for chunk in chunks]
        return embeddings
    
    def get_document_count(self) -> int:
        """
        Get total number of document chunks in the collection.
        
        Returns:
            Number of chunks indexed
        """
        return self.collection.count()
    
    def validate_embedding_dimension(self) -> Dict[str, Any]:
        """
        Validate that the database is configured correctly for the current embedding model.
        
        Returns:
            Dict with validation results including expected vs actual dimensions
        """
        from backend.embed_utils import get_embedding, get_embedding_dimension, get_current_model_id
        
        # Try to get a sample document to check dimensions
        sample = self.collection.get(limit=1)
        
        if not sample['ids']:
            return {
                "status": "empty",
                "message": "Database is empty. Re-indexing required.",
                "expected_dimension": get_embedding_dimension(),
                "model": get_current_model_id()
            }
        
        # Test embedding a simple query
        test_embedding = get_embedding("test query")
        
        return {
            "status": "ok",
            "message": "Database configuration is valid",
            "expected_dimension": get_embedding_dimension(),
            "actual_dimension": len(test_embedding),
            "model": get_current_model_id(),
            "document_count": len(sample['ids'])
        }
