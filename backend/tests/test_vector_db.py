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


def test_text_lives_in_the_keyword_store_not_in_chroma(client):
    _add_items(client, {"1": ["needle in haystack"]})
    assert client.collection.get(ids=["1:0"], include=["documents"])["documents"] == [None]
    assert client.query_bm25("needle")[0]["document"] == "needle in haystack"


def test_reconcile_adopts_text_chroma_still_holds_and_drops_chunks_whose_text_is_lost(client):
    # A store from before 0.8: text in Chroma, nothing in the keyword store.
    client.collection.add(ids=["1:0"], documents=["needle in haystack"], metadatas=[{"item_id": "1"}], embeddings=[_vec(1)])
    _add_items(client, {"2": ["plain text"]})
    with client._fts() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunk_map")
    # Lazy path: querying an empty keyword index with a populated collection reconciles it.
    assert [h["id"] for h in client.query_bm25("needle")] == ["1:0"]
    assert client._fts_count() == 1
    assert client.get_indexed_item_ids() == {"1"}, "2:0 had no text anywhere, so its item is indexed again next sync"
    # Rows only the keyword store has (a crash after its write) are dropped too.
    with client._fts() as conn:
        client._fts_add(conn, ["9:0"], ["ghost"])
    client.build_bm25_index()
    assert client._fts_count() == 1 and client.query_bm25("ghost") == []
    # Reconcile is a no-op when in sync.
    client.build_bm25_index()
    assert client._fts_count() == 1


def test_item_table_is_rebuilt_from_chunk_metadata_when_out_of_step(client):
    _add_items(client, {"1": (["a", "b"], {"year": 2019, "tags": "NLP"}), "2": (["c"], {"year": "2021"})})
    with client._fts() as conn:
        conn.execute("DELETE FROM items")
    assert client.count_items_matching_filters(year_min=2020) == {"unique_items": 1, "total_chunks": 1}
    assert {r["item_id"]: r["year"] for r in client._item_rows()} == {"1": 2019, "2": 2021}
    client.upsert_item("2", {"tags": "NLP", "year": None})
    assert client.count_items_matching_filters(tags=["NLP"]) == {"unique_items": 2, "total_chunks": 3}
    assert client.delete_item("2") == 1
    assert {r["item_id"] for r in client._item_rows()} == {"1"}


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


def test_author_and_tag_limits_are_resolved_to_items_before_retrieval(client, monkeypatch):
    """A limit Chroma cannot evaluate must not depend on the item being in the retrieved pool."""
    _add_items(client, {
        "1": (["causal diagrams"], {"authors": "Pearl,Bareinboim", "tags": "Causality"}),
        "2": (["grammar induction"], {"authors": "Lang,Pearlmutter,Price", "tags": "Learning"}),
        "3": (["unrelated text"], {"authors": "Smith", "tags": "Causality,Other"}),
    })
    import backend.embed_utils as eu
    monkeypatch.setattr(eu, "get_embedding", lambda q, model_id=None: np.array(_vec(2), dtype=np.float32))
    by_author = client.query_hybrid_rrf("anything", k=5, where={"authors": {"$contains_item": "Pearl"}}, embedding_model_id="test-model")
    assert by_author["ids"][0] == ["1:0"], "Pearlmutter is not Pearl"
    by_tag = client.query_hybrid_rrf("anything", k=5, where={"tags": {"$contains_item": "Causality"}}, embedding_model_id="test-model")
    assert set(by_tag["ids"][0]) == {"1:0", "3:0"}
    none = client.query_hybrid_rrf("anything", k=5, where={"authors": {"$contains_item": "Nobody"}}, embedding_model_id="test-model")
    assert none["ids"][0] == []
    assert client._item_ids_matching({"authors": {"$contains_item": "Pearl"}}) == {"1"}
    _add_items(client, {"4": (["more causal"], {"authors": "Pearl", "tags": ""})})
    assert client._item_ids_matching({"authors": {"$contains_item": "Pearl"}}) == {"1", "4"}
    # Half the library or more: the pool is filtered after retrieval, not Chroma.
    broad = {"$or": [{"tags": {"$contains_item": "Causality"}}, {"authors": {"$contains_item": "Pearl"}}]}  # 3 of 4 items
    assert client._prefilter(None, broad) == (None, broad)
    assert client._prefilter(None, {"authors": {"$contains_item": "Smith"}}) == ({"item_id": {"$in": ["3"]}}, None)


def test_fused_pool_caps_chunks_per_item(client, monkeypatch):
    _add_items(client, {"1": [f"dogs bark loudly {i}" for i in range(12)], "2": ["dogs bark softly"], "3": ["cats purr"]})
    import backend.embed_utils as eu
    monkeypatch.setattr(eu, "get_embedding", lambda q, model_id=None: np.array(_vec(2), dtype=np.float32))
    out = client.query_hybrid_rrf("dogs bark", k=6, embedding_model_id="test-model", per_item=2)
    by_item = {}
    for cid in out["ids"][0]:
        by_item[cid.split(":")[0]] = by_item.get(cid.split(":")[0], 0) + 1
    assert by_item["1"] == 2 and "2" in by_item, by_item
