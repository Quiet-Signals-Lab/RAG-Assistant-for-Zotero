#vector_db.py
import chromadb
from chromadb.config import Settings
import logging
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword tokenizer — handles both Latin and CJK scripts
# ---------------------------------------------------------------------------
# CJK scripts (Chinese, Japanese, Korean) have no whitespace between words.
# Inserting spaces around each CJK character before splitting makes the
# keyword index treat individual characters as tokens, which is the standard
# character-level approach used by many CJK IR systems.  No additional NLP
# dependency is required.
#
# Ranges covered:
#   U+2E80-U+2EFF  CJK Radicals Supplement
#   U+2F00-U+2FDF  Kangxi Radicals
#   U+3040-U+309F  Hiragana
#   U+30A0-U+30FF  Katakana
#   U+3100-U+312F  Bopomofo
#   U+3400-U+4DBF  CJK Extension A
#   U+4E00-U+9FFF  CJK Unified Ideographs (the main block)
#   U+F900-U+FAFF  CJK Compatibility Ideographs
#   U+FE30-U+FE4F  CJK Compatibility Forms
_CJK_RE = re.compile(
    r'[⺀-⻿⼀-⿟぀-ゟ゠-ヿ'
    r'㄀-ㄯ㐀-䶿一-鿿豈-﫿︰-﹏]'
)


def _tokenize_for_bm25(text: str) -> list:
    """Tokenize text for keyword indexing and querying.

    Latin/Western scripts: lowercased and split on whitespace.
    CJK scripts: a space is inserted before and after every CJK character so
    the whitespace split produces individual character tokens. Mixed text is
    handled correctly because only CJK characters are expanded.
    """
    text = unicodedata.normalize("NFKC", text).replace("­", "")  # ligatures (ﬁ) and soft hyphens
    return _CJK_RE.sub(r' \g<0> ', text.lower()).split()


def _fts_match_expression(query: str) -> Optional[str]:
    """Build an FTS5 MATCH expression that ORs every query token.

    Every token is quoted so FTS5 never interprets it as an operator
    (AND/OR/NOT, parentheses, column filters, prefix stars).
    """
    tokens = [t for t in _tokenize_for_bm25(query) if t.strip('"')]
    if not tokens:
        return None
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def _item_id_from_chunk_id(chunk_id: str) -> str:
    """Chunk IDs are '<item_id>:<chunk_idx>'; IDs without a colon are their own item."""
    return chunk_id.rsplit(":", 1)[0]


# Page sizes for walking the collection. Chroma's get() with offset is a
# SQL LIMIT/OFFSET, so fewer, larger pages are cheaper for ids-only reads.
_ID_PAGE = 50_000
_META_PAGE = 10_000


class ChromaClient:
    """
    Administers user interactions with the Chroma vector database for Zotero library items.
    Supports persistent per-library DB, bulk chunk addition, semantic querying, and
    hybrid (dense + keyword) retrieval.

    IMPORTANT: This class expects pre-computed embeddings and does NOT use ChromaDB's
    default embedding function. All embeddings must be generated using get_embedding()
    from embed_utils.py to ensure consistent dimensional vectors.

    Each embedding model gets its own collection to prevent dimension mismatch errors,
    and its own on-disk keyword index (SQLite FTS5) next to the Chroma database.

    Memory contract: no method loads the whole collection into memory. Every
    whole-collection operation pages through Chroma (issue #86).
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

        # Keyword index (SQLite FTS5) for sparse retrieval. Lives on disk, is
        # written incrementally by add_chunks/delete_item, and is reconciled
        # against Chroma by build_bm25_index(). Replaces the in-memory
        # rank_bm25 index + JSON corpus that could not fit large libraries.
        self.fts_path = os.path.join(self.db_path, f"fts_{safe_model_id}.sqlite3")
        self._legacy_bm25_path = os.path.join(self.db_path, f"bm25_index_{safe_model_id}.json")
        self._init_fts()

    # ------------------------------------------------------------------
    # Keyword index (FTS5)
    # ------------------------------------------------------------------

    @contextmanager
    def _fts(self) -> Iterator[sqlite3.Connection]:
        """One short-lived connection per call: safe across threads, and WAL
        mode lets a chat query read while the indexing thread writes."""
        conn = sqlite3.connect(self.fts_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_fts(self) -> None:
        try:
            with self._fts() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(body, tokenize='unicode61')"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS chunk_map ("
                    " id TEXT PRIMARY KEY, item_id TEXT NOT NULL, fts_rowid INTEGER NOT NULL)"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS chunk_map_item ON chunk_map(item_id)")
        except sqlite3.OperationalError as e:
            raise RuntimeError(
                "This Python's SQLite lacks the FTS5 extension, which the keyword index needs. "
                f"({e})"
            ) from e
        # The pre-0.6 JSON corpus is no longer read; free the disk it used.
        if os.path.exists(self._legacy_bm25_path):
            try:
                os.remove(self._legacy_bm25_path)
            except OSError as e:
                logger.warning("Could not remove legacy BM25 index %s: %s", self._legacy_bm25_path, e)

    def _fts_add(self, conn: sqlite3.Connection, ids: List[str], documents: List[str]) -> None:
        for chunk_id, doc in zip(ids, documents):
            body = " ".join(_tokenize_for_bm25(doc or ""))
            # Re-adding an id (full reindex of an item) replaces its row.
            old = conn.execute("SELECT fts_rowid FROM chunk_map WHERE id = ?", (chunk_id,)).fetchone()
            if old:
                conn.execute("DELETE FROM chunks WHERE rowid = ?", (old[0],))
            cur = conn.execute("INSERT INTO chunks(body) VALUES (?)", (body,))
            conn.execute(
                "INSERT OR REPLACE INTO chunk_map(id, item_id, fts_rowid) VALUES (?, ?, ?)",
                (chunk_id, _item_id_from_chunk_id(chunk_id), cur.lastrowid),
            )

    def _fts_delete_item(self, conn: sqlite3.Connection, item_id: str) -> None:
        conn.execute(
            "DELETE FROM chunks WHERE rowid IN (SELECT fts_rowid FROM chunk_map WHERE item_id = ?)",
            (item_id,),
        )
        conn.execute("DELETE FROM chunk_map WHERE item_id = ?", (item_id,))

    def _fts_count(self) -> int:
        with self._fts() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunk_map").fetchone()[0]

    def build_bm25_index(self) -> None:
        """Reconcile the keyword index with Chroma.

        The index is maintained incrementally, so this is a no-op when the
        two agree. When they do not (first run after upgrading from the JSON
        index, or a crash between the two writes) it is rebuilt by paging
        through Chroma, never holding more than one page in memory.
        """
        total = self.collection.count()
        if self._fts_count() == total:
            return
        logger.info("Rebuilding keyword index for %d chunks", total)
        with self._fts() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM chunk_map")
            for ids, docs in self._iter_documents():
                self._fts_add(conn, ids, docs)
        logger.info("Keyword index rebuilt with %d chunks", total)

    def query_bm25(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """Keyword (BM25) retrieval via FTS5.

        Returns a list of dicts with 'id', 'score', 'document' and 'metadata',
        best first. Only chunks matching at least one query token are returned.
        """
        match = _fts_match_expression(query)
        if match is None:
            return []
        if self._fts_count() == 0 and self.collection.count() > 0:
            self.build_bm25_index()
        # FTS5 takes its optimised ranking path only for its own `rank` column (bm25 by
        # default): the same query with ORDER BY bm25(chunks) took 124 s on 62k passages
        # for a 15-word query, ORDER BY rank 0.5 s, with the same results.
        with self._fts() as conn:
            rows = conn.execute(
                "SELECT m.id, -rank AS score FROM chunks "
                "JOIN chunk_map m ON m.fts_rowid = chunks.rowid "
                "WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                (match, int(k)),
            ).fetchall()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        scores = {r[0]: float(r[1]) for r in rows}
        found = self.collection.get(ids=ids, include=['documents', 'metadatas'])
        by_id = {
            cid: (doc, meta)
            for cid, doc, meta in zip(found['ids'], found['documents'], found['metadatas'])
        }
        return [
            {'id': cid, 'score': scores[cid], 'document': by_id[cid][0], 'metadata': by_id[cid][1]}
            for cid in ids if cid in by_id
        ]

    # ------------------------------------------------------------------
    # Paging helpers
    # ------------------------------------------------------------------

    def _iter_ids(self, page: int = _ID_PAGE) -> Iterator[List[str]]:
        offset = 0
        while True:
            got = self.collection.get(limit=page, offset=offset, include=[])
            ids = got['ids']
            if not ids:
                return
            yield ids
            if len(ids) < page:
                return
            offset += len(ids)

    def _iter_documents(self, page: int = _META_PAGE) -> Iterator[tuple]:
        offset = 0
        while True:
            got = self.collection.get(limit=page, offset=offset, include=['documents'])
            if not got['ids']:
                return
            yield got['ids'], got['documents']
            if len(got['ids']) < page:
                return
            offset += len(got['ids'])

    def _iter_metadatas(self, where: Optional[Dict[str, Any]] = None, page: int = _META_PAGE) -> Iterator[List[Dict]]:
        offset = 0
        while True:
            got = self.collection.get(where=where, limit=page, offset=offset, include=['metadatas'])
            metas = got['metadatas'] or []
            if not metas:
                return
            yield metas
            if len(metas) < page:
                return
            offset += len(metas)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _max_batch_size(self) -> int:
        try:
            return int(self.chroma_client.get_max_batch_size())
        except Exception:
            return 5000

    def add_chunks(self,
        ids: List[str],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """
        Bulk-adds document chunks and their vectors to the Chroma collection and
        the keyword index. Long books exceed Chroma's maximum batch size, so the
        add is split into batches the client accepts (issue #86).
        """
        self.__dict__.pop("_item_ids_cache", None)
        step = self._max_batch_size()
        for start in range(0, len(ids), step):
            sl = slice(start, start + step)
            self.collection.add(
                ids=ids[sl],
                documents=documents[sl],
                metadatas=metadatas[sl] if metadatas is not None else None,
                embeddings=embeddings[sl] if embeddings is not None else None,
            )
            with self._fts() as conn:
                self._fts_add(conn, ids[sl], documents[sl])

    def delete_item(self, item_id: str) -> int:
        self.__dict__.pop("_item_ids_cache", None)
        """
        Delete all chunks associated with an item from the database.

        Returns:
            Number of chunks deleted
        """
        item_id = str(item_id)
        ids = self.collection.get(where={"item_id": item_id}, include=[])['ids']
        if ids:
            self.collection.delete(ids=ids)
        with self._fts() as conn:
            self._fts_delete_item(conn, item_id)
        return len(ids)

    # ------------------------------------------------------------------
    # Dense + hybrid queries
    # ------------------------------------------------------------------

    def query_hybrid(self, query: str, k: int = 10, where: Optional[Dict[str, Any]] = None, embedding_model_id: str = "bge-base") -> Dict[str, Any]:
        """Hybrid search combining dense (semantic) and sparse (keyword) retrieval.

        Retrieves top-k from both methods and returns their union; the caller
        re-ranks with a cross-encoder.

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
        chroma_where, client_where = self._prefilter(chroma_where, client_where)
        if chroma_where is False:
            return {'ids': [[]], 'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

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

    # Filters Chroma cannot evaluate (a whole tag, collection or author in a comma-joined
    # field) used to be applied to the top few hundred retrieved chunks only, so on a
    # large library the matching items were often not in that pool at all and the limit
    # was set aside. They are now resolved to item ids first, which Chroma pre-filters on.
    _ITEM_IDS_TTL = 600.0

    def _prefilter(self, chroma_where, client_where):
        """(chroma_where with the client-side filters folded in as item ids, None), or
        (False, None) when nothing matches them."""
        if not client_where:
            return chroma_where, client_where
        from backend.metadata_utils import merge_where_clauses
        ids = self._item_ids_matching(client_where)
        if not ids:
            return False, None
        return merge_where_clauses(chroma_where, {"item_id": {"$in": sorted(ids)}}), None

    def _item_ids_matching(self, client_where) -> set:
        """Item ids whose chunks satisfy a client-side where clause; cached per clause,
        cleared on every write."""
        import json as _json
        key = _json.dumps(client_where, sort_keys=True)
        cache = self.__dict__.setdefault("_item_ids_cache", {})
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < self._ITEM_IDS_TTL:
            return hit[1]
        ids = set()
        for page in self._iter_metadatas():
            ids.update(m["item_id"] for m in page if m and self._matches_where_clause(m, client_where))
        cache[key] = (time.monotonic(), ids)
        return ids

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
        chroma_where, client_where = self._prefilter(chroma_where, client_where)
        if chroma_where is False:
            return {'ids': [[]], 'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

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
        return [r for r in results if self._matches_where_clause(r.get('metadata', {}), where)]

    def _matches_where_clause(self, metadata: Dict[str, Any], where: Dict[str, Any]) -> bool:
        """Check if metadata matches a where clause.

        Delegates to metadata_utils so scope filtering here and in the query path
        can't diverge again: this copy was case-sensitive on $contains and silently
        returned 0 items for a tag the UI matched fine. See issue #75.
        """
        from backend.metadata_utils import _matches_where_clause
        return _matches_where_clause(metadata, where)

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

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

        Used by the Scope panel to show an estimate of filtered items. Pages
        through metadata so memory stays bounded on large libraries.

        Returns:
            Dict with 'unique_items' and 'total_chunks' counts
        """
        from backend.metadata_utils import build_metadata_where_clause, separate_where_clauses

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
            # No filters: ids alone carry the item id, no metadata needed.
            return {
                'unique_items': len(self.get_indexed_item_ids()),
                'total_chunks': self.collection.count(),
            }

        chroma_where, client_where = separate_where_clauses(where)
        unique_items = set()
        total_chunks = 0
        for metas in self._iter_metadatas(where=chroma_where):
            for m in metas:
                if client_where and not self._matches_where_clause(m, client_where):
                    continue
                total_chunks += 1
                if m.get('item_id'):
                    unique_items.add(str(m['item_id']))
        return {'unique_items': len(unique_items), 'total_chunks': total_chunks}

    def get_indexed_item_ids(self) -> set:
        """
        Get all unique item IDs that are currently indexed in the database.

        Chunk IDs are '<item_id>:<chunk_idx>', so only ids are read, never
        metadata or documents.

        Returns:
            Set of item_id strings (always converted to strings for consistency)
        """
        item_ids = set()
        for ids in self._iter_ids():
            item_ids.update(_item_id_from_chunk_id(i) for i in ids)
        return item_ids

    def item_exists(self, item_id: str) -> bool:
        """Check if an item is already indexed in the database."""
        results = self.collection.get(
            where={"item_id": str(item_id)},
            limit=1,
            include=[],
        )
        return len(results['ids']) > 0

    def has_pdf_path(self, pdf_path: str) -> bool:
        """True if some indexed chunk points at this PDF path."""
        results = self.collection.get(where={"pdf_path": pdf_path}, limit=1, include=[])
        return len(results['ids']) > 0

    def get_item_metadata(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for an indexed item, or None if not found."""
        results = self.collection.get(
            where={"item_id": str(item_id)},
            limit=1
        )

        if results['metadatas']:
            return results['metadatas'][0]
        return None

    def get_document_count(self) -> int:
        """Get total number of document chunks in the collection."""
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
