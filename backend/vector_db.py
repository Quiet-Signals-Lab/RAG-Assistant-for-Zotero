#vector_db.py
import chromadb
from chromadb.config import Settings
import logging
import os
import re
import sqlite3
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
# Most chunks of one item in the fused pool handed to the reranker. The list shows at
# most six passages per item, so more only crowds other items out.
POOL_PER_ITEM = 8


class ChromaClient:
    """
    Administers user interactions with the Chroma vector database for Zotero library items.
    Supports persistent per-library DB, bulk chunk addition, semantic querying, and
    hybrid (dense + keyword) retrieval.

    IMPORTANT: This class expects pre-computed embeddings and does NOT use ChromaDB's
    default embedding function. All embeddings must be generated using get_embedding()
    from embed_utils.py to ensure consistent dimensional vectors.

    Each embedding model gets its own collection to prevent dimension mismatch errors,
    and its own SQLite file next to the Chroma database holding the keyword index
    (FTS5), each passage's text, and one row of metadata per item. Chroma holds
    vectors and per-chunk metadata only: given the text too, it indexes it twice
    more (a trigram FTS and a string index), which was ~80% of its file.

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
        # Chroma phones home by default (posthog); a local library tool should not.
        self.chroma_client = chromadb.PersistentClient(path=self.db_path, settings=Settings(anonymized_telemetry=False))

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
                    " id TEXT PRIMARY KEY, item_id TEXT NOT NULL, fts_rowid INTEGER NOT NULL, text TEXT)"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS chunk_map_item ON chunk_map(item_id)")
                if "text" not in {r[1] for r in conn.execute("PRAGMA table_info(chunk_map)")}:
                    conn.execute("ALTER TABLE chunk_map ADD COLUMN text TEXT")  # stores from before 0.8
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS items (item_id TEXT PRIMARY KEY, item_key TEXT, title TEXT,"
                    " authors TEXT, tags TEXT, collections TEXT, item_type TEXT, year INTEGER, pdf_path TEXT)"
                )
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
                "INSERT OR REPLACE INTO chunk_map(id, item_id, fts_rowid, text) VALUES (?, ?, ?, ?)",
                (chunk_id, _item_id_from_chunk_id(chunk_id), cur.lastrowid, doc),
            )

    def _fts_delete_item(self, conn: sqlite3.Connection, item_id: str) -> None:
        conn.execute(
            "DELETE FROM chunks WHERE rowid IN (SELECT fts_rowid FROM chunk_map WHERE item_id = ?)",
            (item_id,),
        )
        conn.execute("DELETE FROM chunk_map WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM items WHERE item_id = ?", (item_id,))

    def _fts_count(self) -> int:
        with self._fts() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunk_map").fetchone()[0]

    def _texts(self, conn: sqlite3.Connection, ids: List[str]) -> Dict[str, str]:
        marks = ",".join("?" * len(ids))
        return dict(conn.execute(f"SELECT id, text FROM chunk_map WHERE id IN ({marks})", ids))

    def _hydrate(self, ids: List[str]) -> Dict[str, tuple]:
        """{chunk id: (text, metadata)} for ids Chroma knows. Text comes from the keyword
        store; chunks indexed before 0.8 still carry it in Chroma, which is the fallback."""
        if not ids:
            return {}
        found = self.collection.get(ids=ids, include=['documents', 'metadatas'])
        with self._fts() as conn:
            texts = self._texts(conn, ids)
        return {
            cid: (texts.get(cid) or doc or "", meta)
            for cid, doc, meta in zip(found['ids'], found['documents'], found['metadatas'])
        }

    def build_bm25_index(self) -> None:
        """Reconcile the keyword store with Chroma.

        Both are written for every item, so this is a no-op when they agree. When
        they do not, the keyword store is brought to Chroma's chunk list one page
        at a time: chunks only Chroma has are added from the text it still holds
        (stores from before 0.8) or, when it holds none, deleted so the item is
        indexed again at the next sync; chunks only the keyword store has (a crash
        between the two writes) are dropped.
        """
        total = self.collection.count()
        if self._fts_count() == total:
            return
        logger.info("Reconciling keyword store with %d chunks", total)
        orphans = []
        with self._fts() as conn:
            known = {row[0] for row in conn.execute("SELECT id FROM chunk_map")}
            seen = set()
            for ids, docs in self._iter_documents():
                seen.update(ids)
                missing = [(cid, doc) for cid, doc in zip(ids, docs) if cid not in known]
                self._fts_add(conn, [cid for cid, doc in missing if doc], [doc for cid, doc in missing if doc])
                orphans += [cid for cid, doc in missing if not doc]
            for cid in known - seen:
                conn.execute("DELETE FROM chunks WHERE rowid = (SELECT fts_rowid FROM chunk_map WHERE id = ?)", (cid,))
                conn.execute("DELETE FROM chunk_map WHERE id = ?", (cid,))
        if orphans:
            logger.warning("Dropping %d chunks whose text was lost; their items will be indexed again", len(orphans))
            self.collection.delete(ids=orphans)
        logger.info("Keyword store reconciled: %d chunks", self._fts_count())

    # ------------------------------------------------------------------
    # Item table: one row per item, so scope filters and counts never walk chunks
    # ------------------------------------------------------------------

    _ITEM_FIELDS = ("item_id", "item_key", "title", "authors", "tags", "collections", "item_type", "year", "pdf_path")

    def _upsert_items(self, conn: sqlite3.Connection, metadatas: Iterable[Dict[str, Any]]) -> None:
        """Write the item fields found in chunk (or item) metadata; fields not given keep their value."""
        latest: Dict[str, Dict[str, Any]] = {}
        for meta in metadatas:
            if meta and meta.get("item_id") is not None:
                latest[str(meta["item_id"])] = meta
        marks = ",".join("?" * len(self._ITEM_FIELDS))
        for item_id, meta in latest.items():
            old = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
            row = {"item_id": item_id, "year": 0, **{k: "" for k in self._ITEM_FIELDS if k not in ("item_id", "year")}}
            row.update(dict(zip(self._ITEM_FIELDS, old)) if old else {})
            row.update({k: meta[k] for k in self._ITEM_FIELDS if k in meta and k != "item_id"})
            try:
                row["year"] = int(row["year"])
            except (TypeError, ValueError):
                row["year"] = 0  # unknown; the chunks say 0 and the v1 migration said -1
            conn.execute(f"INSERT OR REPLACE INTO items VALUES ({marks})", tuple(row[k] for k in self._ITEM_FIELDS))

    def upsert_item(self, item_id: str, meta: Dict[str, Any]) -> None:
        """Refresh one item's row (metadata sync)."""
        with self._fts() as conn:
            self._upsert_items(conn, [{**meta, "item_id": str(item_id)}])

    def _item_rows(self) -> List[Dict[str, Any]]:
        """Every indexed item's metadata, from the item table."""
        with self._fts() as conn:
            n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            n_chunk_items = conn.execute("SELECT COUNT(DISTINCT item_id) FROM chunk_map").fetchone()[0]
        if n_items != n_chunk_items:
            # A store from before 0.8, or a table out of step with the chunks: rebuild it once
            # from the chunk metadata (about 15 s for 60k chunks), then it is kept incrementally.
            logger.info("Rebuilding the item table from chunk metadata (%d items)", n_chunk_items)
            with self._fts() as conn:
                conn.execute("DELETE FROM items")
                for metas in self._iter_metadatas():
                    self._upsert_items(conn, metas)
        with self._fts() as conn:
            return [dict(zip(self._ITEM_FIELDS, row)) for row in conn.execute(
                f"SELECT {','.join(self._ITEM_FIELDS)} FROM items")]

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
        by_id = self._hydrate(ids)
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
        Bulk-adds document chunks: text, keyword index and item row to the SQLite
        store, vectors and chunk metadata to Chroma. Long books exceed Chroma's
        maximum batch size, so the add is split into batches the client accepts
        (issue #86).
        """
        step = self._max_batch_size()
        for start in range(0, len(ids), step):
            sl = slice(start, start + step)
            # The keyword store is written first: a crash between the two writes leaves
            # rows Chroma does not know, which build_bm25_index drops, and the item is
            # indexed again at the next sync.
            with self._fts() as conn:
                self._fts_add(conn, ids[sl], documents[sl])
                if metadatas is not None:
                    self._upsert_items(conn, metadatas[sl])
            self.collection.add(
                ids=ids[sl],
                metadatas=metadatas[sl] if metadatas is not None else None,
                embeddings=embeddings[sl] if embeddings is not None else None,
            )

    def delete_item(self, item_id: str) -> int:
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

    # Filters Chroma cannot evaluate (a whole tag, collection or author in a comma-joined
    # field) used to be applied to the top few hundred retrieved chunks only, so on a
    # large library the matching items were often not in that pool at all and the limit
    # was set aside. They are now resolved to item ids first, which Chroma pre-filters on.

    def _prefilter(self, chroma_where, client_where):
        """(chroma_where with the client-side filters folded in as item ids, None);
        (False, None) when nothing matches them; or the two unchanged when the scope
        covers most of the library and the retrieved pool can be filtered instead."""
        if not client_where:
            return chroma_where, client_where
        from backend.metadata_utils import merge_where_clauses
        rows = self._item_rows()
        ids = {r["item_id"] for r in rows if self._matches_where_clause(r, client_where)}
        if not ids:
            return False, None
        # shortcut: a long $in list made Chroma's filtered search ~4x slower (2.7 s against
        # 0.7 s for 986 ids); drop the shortcut if Chroma ever filters id lists cheaply.
        if len(ids) * 2 > len(rows):
            return chroma_where, client_where
        return merge_where_clauses(chroma_where, {"item_id": {"$in": sorted(ids)}}), None

    def _item_ids_matching(self, client_where) -> set:
        """Item ids whose metadata satisfies a client-side where clause."""
        return {r["item_id"] for r in self._item_rows() if self._matches_where_clause(r, client_where)}

    def query_hybrid_rrf(
        self,
        query: str,
        k: int = 10,
        where: Optional[Dict[str, Any]] = None,
        embedding_model_id: str = "bge-base",
        rrf_k: int = 60,
        per_item: int = POOL_PER_ITEM,
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
            per_item: Most chunks of any one item in the result

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
            bm25_results = [r for r in bm25_results if self._matches_where_clause(r.get('metadata', {}), chroma_where)]

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

        # Best first, at most `per_item` chunks of any one item: a long paper that matched
        # strongly (stored twice in Zotero) otherwise filled the whole pool, every reranked
        # passage was its, and the list showed one item (eval_desk trace, 2026-10-13).
        sorted_ids: List[str] = []
        taken: Dict[str, int] = {}
        for cid in sorted(rrf_scores, key=rrf_scores.get, reverse=True):
            item = _item_id_from_chunk_id(cid)
            if taken.get(item, 0) < per_item:
                taken[item] = taken.get(item, 0) + 1
                sorted_ids.append(cid)
                if len(sorted_ids) == k:
                    break

        # Retrieve full documents for top-k IDs
        if not sorted_ids:
            return {
                'ids': [[]],
                'documents': [[]],
                'metadatas': [[]],
                'distances': [[]]
            }

        by_id = self._hydrate(sorted_ids)
        ordered_docs = [by_id[cid][0] for cid in sorted_ids if cid in by_id]
        ordered_metas = [by_id[cid][1] for cid in sorted_ids if cid in by_id]
        ordered_scores = [rrf_scores[cid] for cid in sorted_ids if cid in by_id]

        return {
            'ids': [sorted_ids],
            'documents': [ordered_docs],
            'metadatas': [ordered_metas],
            'distances': [[1 - score for score in ordered_scores]]  # Convert to distance
        }

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
        Count how many unique items and chunks match the given filters, from the
        item table (used by the Scope panel; walking chunk metadata took 14 s).

        Returns:
            Dict with 'unique_items' and 'total_chunks' counts
        """
        from backend.metadata_utils import build_metadata_where_clause

        where = build_metadata_where_clause(
            year_min=year_min,
            year_max=year_max,
            tags=tags,
            collections=collections,
            title=title,
            author=author,
            item_types=item_types,
        )
        rows = self._item_rows()
        if where is not None:
            rows = [r for r in rows if self._matches_where_clause(r, where)]
        with self._fts() as conn:
            chunks = dict(conn.execute("SELECT item_id, COUNT(*) FROM chunk_map GROUP BY item_id"))
        return {'unique_items': len(rows), 'total_chunks': sum(chunks.get(r["item_id"], 0) for r in rows)}

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
