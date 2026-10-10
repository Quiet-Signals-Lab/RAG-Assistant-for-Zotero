"""Tests for ChromaClient: batching, paging, FTS5 keyword index (issue #86)."""

import numpy as np
import pytest

from backend.vector_db import ChromaClient, _fts_match_expression, _item_id_from_chunk_id


def _vec(seed: int):
    rng = np.random.default_rng(seed)
    return rng.random(4).tolist()


def _add_items(client, items):
    """items: {item_id: [chunk texts]} with optional per-item meta via tuple."""
    ids, docs, metas, embs = [], [], [], []
    for item_id, spec in items.items():
        texts, meta = (spec, {}) if isinstance(spec, list) else spec
        for i, t in enumerate(texts):
            ids.append(f"{item_id}:{i}")
            docs.append(t)
            metas.append({"item_id": str(item_id), "chunk_idx": i, "pdf_path": f"/pdfs/{item_id}.pdf", **meta})
            embs.append(_vec(len(ids)))
    client.add_chunks(ids=ids, documents=docs, metadatas=metas, embeddings=embs)


@pytest.fixture
def client(tmp_path):
    return ChromaClient(db_path=str(tmp_path), embedding_model_id="test-model")


def test_item_id_from_chunk_id():
    assert _item_id_from_chunk_id("123:4") == "123"
    assert _item_id_from_chunk_id("ABC:12:7") == "ABC:12"
    assert _item_id_from_chunk_id("doc_0") == "doc_0"


def test_fts_match_expression_quotes_every_token():
    assert _fts_match_expression("deep NOT (learning)") == '"deep" OR "not" OR "(learning)"'
    assert _fts_match_expression('say "hi"') == '"say" OR """hi"""'
    assert _fts_match_expression("   ") is None


def test_add_chunks_splits_batches_over_chroma_max(client, monkeypatch):
    monkeypatch.setattr(client.chroma_client, "get_max_batch_size", lambda: 2)
    _add_items(client, {"1": ["a b", "c d", "e f", "g h", "i j"]})
    assert client.get_document_count() == 5
    assert client._fts_count() == 5


def test_get_indexed_item_ids_reads_ids_only(client):
    _add_items(client, {"10": ["x", "y"], "20": ["z"]})
    assert client.get_indexed_item_ids() == {"10", "20"}
    # paging walks every page and stops
    pages = list(client._iter_ids(page=2))
    assert [len(p) for p in pages] == [2, 1]


def test_delete_item_removes_chroma_and_fts_rows(client):
    _add_items(client, {"1": ["alpha", "beta"], "2": ["gamma"]})
    assert client.delete_item("1") == 2
    assert client.get_document_count() == 1
    assert client._fts_count() == 1
    assert client.get_indexed_item_ids() == {"2"}
    assert client.delete_item("missing") == 0


def test_query_bm25_ranks_and_returns_documents(client):
    _add_items(client, {
        "1": ["transformers use attention mechanisms", "attention is all you need"],
        "2": ["sqlite is a small database engine"],
    })
    hits = client.query_bm25("attention transformers", k=5)
    assert [h["id"] for h in hits][:1] == ["1:0"]
    assert {h["id"] for h in hits} == {"1:0", "1:1"}
    assert hits[0]["document"].startswith("transformers")
    assert hits[0]["metadata"]["item_id"] == "1"
    assert hits[0]["score"] > hits[1]["score"] > 0
    assert client.query_bm25("nothing matches here", k=5) == []
    assert client.query_bm25("NOT (database) AND *", k=5)[0]["id"] == "2:0"


def test_query_bm25_cjk_character_tokens(client):
    _add_items(client, {"1": ["深度学习模型"], "2": ["english only text"]})
    assert [h["id"] for h in client.query_bm25("学习")] == ["1:0"]


def test_build_bm25_index_rebuilds_when_out_of_sync(client):
    _add_items(client, {"1": ["needle in haystack"], "2": ["plain text"]})
    with client._fts() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunk_map")
    assert client._fts_count() == 0
    # Lazy path: querying an empty keyword index with a populated collection rebuilds it.
    assert [h["id"] for h in client.query_bm25("needle")] == ["1:0"]
    assert client._fts_count() == 2
    # Reconcile is a no-op when in sync.
    client.build_bm25_index()
    assert client._fts_count() == 2


def test_readding_an_item_replaces_its_fts_rows(client):
    _add_items(client, {"1": ["old words"]})
    client.delete_item("1")
    _add_items(client, {"1": ["new words"]})
    assert client._fts_count() == 1
    assert client.query_bm25("old") == []
    assert [h["id"] for h in client.query_bm25("new")] == ["1:0"]


def test_count_items_matching_filters_pages_and_filters(client):
    _add_items(client, {
        "1": (["a", "b"], {"year": 2019, "tags": "NLP,ML", "collections": "Thesis"}),
        "2": (["c"], {"year": 2021, "tags": "NLP", "collections": "Reading"}),
        "3": (["d", "e", "f"], {"year": 2022, "tags": "Vision", "collections": "Reading"}),
    })
    assert client.count_items_matching_filters() == {"unique_items": 3, "total_chunks": 6}
    assert client.count_items_matching_filters(year_min=2020) == {"unique_items": 2, "total_chunks": 4}
    assert client.count_items_matching_filters(tags=["NLP"]) == {"unique_items": 2, "total_chunks": 3}
    assert client.count_items_matching_filters(year_min=2020, collections=["Reading"]) == {
        "unique_items": 2, "total_chunks": 4}
    assert client.count_items_matching_filters(tags=["Nope"]) == {"unique_items": 0, "total_chunks": 0}


def test_has_pdf_path(client):
    _add_items(client, {"1": ["a"]})
    assert client.has_pdf_path("/pdfs/1.pdf")
    assert not client.has_pdf_path("/pdfs/other.pdf")


def test_query_hybrid_rrf_fuses_dense_and_keyword(client, monkeypatch):
    _add_items(client, {"1": ["cats purr softly"], "2": ["dogs bark loudly"], "3": ["fish swim"]})
    import backend.embed_utils as eu
    monkeypatch.setattr(eu, "get_embedding", lambda q, model_id=None: np.array(_vec(2), dtype=np.float32))
    out = client.query_hybrid_rrf("dogs bark", k=2, embedding_model_id="test-model")
    assert "2:0" in out["ids"][0]
    assert len(out["documents"][0]) == len(out["ids"][0]) == len(out["metadatas"][0])
    filtered = client.query_hybrid_rrf("dogs bark", k=2, where={"item_id": {"$in": ["1"]}},
                                       embedding_model_id="test-model")
    assert set(filtered["ids"][0]) <= {"1:0"}
