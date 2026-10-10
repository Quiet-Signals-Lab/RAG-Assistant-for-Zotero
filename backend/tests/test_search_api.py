"""POST /api/search and ZoteroChatbot.search(): the reference desk's no-model search path."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.interface import ZoteroChatbot


# --- endpoint -------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    bot = Mock()
    bot.search.return_value = {"query": "q", "items": [], "known_items": [], "scope": {}, "see_also_count": 0}
    monkeypatch.setattr(main, "chatbot", bot)
    return TestClient(main.app), bot


def test_empty_query_is_400(client):
    c, bot = client
    r = c.post("/api/search", json={"query": "   "})
    assert r.status_code == 400 and "looking for" in r.json()["detail"]
    bot.search.assert_not_called()


def test_filters_are_cleaned_before_reaching_the_search(client):
    c, bot = client
    r = c.post("/api/search", json={
        "query": "riders",
        "manual_filters": {"year_min": "2015", "year_max": "", "tags": ["Labour", " "], "collections": "PhD",
                           "author": "  ", "unknown": 1},
        "use_metadata_filters": False,
        "item_ids": "1, 2",
    })
    assert r.status_code == 200
    kwargs = bot.search.call_args.kwargs
    assert kwargs["manual_filters"] == {"year_min": 2015, "tags": ["Labour"], "collections": ["PhD"]}
    assert kwargs["use_metadata_filters"] is False
    assert kwargs["filter_item_ids"] == ["1", "2"]


def test_bad_year_is_400(client):
    c, _ = client
    r = c.post("/api/search", json={"query": "q", "manual_filters": {"year_min": "last year"}})
    assert r.status_code == 400 and "year_min" in r.json()["detail"]


def test_dimension_mismatch_explains_the_fix(client):
    c, bot = client
    bot.search.side_effect = RuntimeError("Collection expecting embedding with dimension of 768, got 1024")
    r = c.post("/api/search", json={"query": "q"})
    assert r.status_code == 500 and "re-index" in r.json()["detail"]


# --- orchestration -----------------------------------------------------------------

@pytest.fixture
def bot():
    with patch("backend.interface.ZoteroLibrary"), patch("backend.interface.ChromaClient"), \
            patch("backend.interface.ConversationStore"), patch("backend.interface.QueryCondenser"):
        bot = ZoteroChatbot(db_path="/nowhere/zotero.sqlite", chroma_path="/nowhere")
    bot.zlib.get_bibliographic.side_effect = lambda ids: {
        i: {"item_id": i, "item_key": f"KEY{i}", "title": f"Title {i}"} for i in ids}
    bot.chroma.item_exists.return_value = True
    bot.provider_manager = Mock()  # must never be called on the search path
    return bot


def hits(*pairs):
    docs = [f"passage about riders in item {item}" for item, _ in pairs]
    metas = [{"item_id": item, "title": f"Title {item}", "year": 2020, "page": 1} for item, _ in pairs]
    return {"documents": [docs], "metadatas": [metas]}


def rerank_in_order(scores):
    return lambda query, docs, top_k=None: list(enumerate(scores))[:top_k]


def test_search_returns_a_ranked_bibliography_with_citations(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0), ("2", 0), ("1", 0))
    with patch("backend.interface.rerank_passages", rerank_in_order([1.0, 5.0, -6.0])):
        out = bot.search("riders")
    assert [it["item_id"] for it in out["items"]] == ["2", "1"]
    assert out["items"][0]["citation"]["item_key"] == "KEY2"
    assert out["items"][1]["band"] == "good"
    assert out["see_also_count"] == 0
    assert out["scope"] == {"manual": {}, "extracted": {}, "extracted_ignored": False}
    assert bot.chroma.query_hybrid_rrf.call_args.kwargs["k"] == ZoteroChatbot.DESK_RETRIEVAL_K
    bot.provider_manager.chat.assert_not_called()


def test_scope_read_from_the_query_is_reported_and_applied(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        out = bot.search("riders since 2015")
    assert out["scope"]["extracted"] == {"year_min": 2015}
    assert out["scope"]["extracted_ignored"] is False
    where = bot.chroma.query_hybrid_rrf.call_args.kwargs["where"]
    assert "2015" in str(where)
    assert bot.chroma.query_hybrid_rrf.call_args.kwargs["query"] == "riders"  # scope words are not topic
    bot.provider_manager.chat.assert_not_called()


def test_extracted_scope_that_matches_nothing_is_dropped_and_said_so(bot):
    bot.chroma.query_hybrid_rrf.side_effect = [hits(), hits(("1", 0))]
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        out = bot.search("riders since 2015", manual_filters={"tags": ["Labour"]})
    assert out["scope"]["extracted_ignored"] is True
    retry_where = str(bot.chroma.query_hybrid_rrf.call_args_list[1].kwargs["where"])
    assert "Labour" in retry_where and "2015" not in retry_where  # manual scope survives the retry
    assert [it["item_id"] for it in out["items"]] == ["1"]


def test_nothing_found_is_an_empty_list_not_an_error(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits()
    out = bot.search("zebras")
    assert out["items"] == [] and out["known_items"] == []


def test_a_broken_zotero_database_does_not_break_search(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    bot.zlib.get_bibliographic.side_effect = RuntimeError("database is locked")
    bot.zlib.find_items_by_creator_year.side_effect = RuntimeError("database is locked")
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        out = bot.search("Woodcock 2020")
    assert out["items"][0]["citation"] is None and out["known_items"] == []


def test_chat_fallback_keeps_an_explicit_item_scope(bot):
    """Regression: the auto-filter fallback used to drop the item-id scope as well."""
    bot.chroma.query_hybrid_rrf.side_effect = [hits(), hits()]
    bot.get_retrieval_limits = Mock(return_value={
        "retrieval_k": 15, "rerank_top_k": 10, "max_snippets_per_paper": 3, "max_total_snippets": 6})
    bot.provider_manager.chat.return_value = Mock(content="answer")
    bot.chat("riders since 2015", filter_item_ids=["7"], use_metadata_filters=True)
    retry_where = bot.chroma.query_hybrid_rrf.call_args_list[1].kwargs["where"]
    assert retry_where == {"item_id": {"$in": ["7"]}}
