"""POST /api/search and ZoteroChatbot.search(): the reference desk's no-model search path."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.interface import ZoteroChatbot


# --- endpoint -------------------------------------------------------------------

SETTINGS = {"deskReadQuery": True, "deskReadTimeout": 5, "deskAlsoTry": False, "deskThemes": False}


@pytest.fixture
def client(monkeypatch):
    bot = Mock()
    bot.search.return_value = {"query": "q", "items": [], "known_items": [], "scope": {}, "see_also_count": 0}
    monkeypatch.setattr(main, "chatbot", bot)
    monkeypatch.setattr(main, "load_settings", lambda *a, **k: dict(SETTINGS))
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
    assert kwargs["read_with_model"] is True and kwargs["read_timeout"] == 5.0


def test_exclusions_and_excluded_items_reach_the_search(client):
    c, bot = client
    c.post("/api/search", json={"query": "q", "manual_filters": {"exclude": ["gig economy"]}, "exclude_item_ids": ["7", "8"]})
    kwargs = bot.search.call_args.kwargs
    assert kwargs["manual_filters"] == {"exclude": ["gig economy"]} and kwargs["exclude_item_ids"] == ["7", "8"]


def test_annotate_streams_events_as_json_lines(client):
    c, bot = client
    bot.annotate.return_value = (e for e in [{"type": "also_try", "suggestions": [], "source": "model"},
                                             {"type": "done", "counts": {}}])
    r = c.post("/api/annotate", json={"query": "q", "items": [
        {"item_id": "1", "title": "T", "passages": [{"page": 3, "text": "x"}, {"page": "bad", "text": "y"}]}]})
    import json
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["also_try", "done"]
    args, kwargs = bot.annotate.call_args
    assert args[1][0]["passages"][1]["page"] is None  # a non-integer page from the client is dropped
    assert (kwargs["also_try"], kwargs["themes"]) == (False, False)


def test_annotate_needs_a_query(client):
    c, _ = client
    assert c.post("/api/annotate", json={"items": []}).status_code == 400


def test_desk_model_reports_availability_and_measurements(client):
    c, bot = client
    from types import SimpleNamespace
    bot.clerk.model.return_value = "lmstudio/never-measured-model"
    bot.clerk.available.return_value = True
    bot.provider_manager.get_active_provider.return_value = SimpleNamespace(requires_api_key=False)
    body = c.get("/api/desk/model").json()
    assert body == {"available": True, "model": "lmstudio/never-measured-model", "measured": None,
                    "cloud": False, "cloud_allowed": False,
                    "jobs": {"read_query": True, "also_try": False, "themes": False}}


def test_annotate_refuses_a_body_not_sent_as_json(client):
    c, bot = client
    import json
    r = c.post("/api/annotate", content=json.dumps({"query": "q", "items": []}), headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
    bot.annotate.assert_not_called()


def test_annotate_survives_odd_item_shapes_and_uses_one_worker_for_a_local_model(client):
    from types import SimpleNamespace
    c, bot = client
    bot.provider_manager.get_active_provider.return_value = SimpleNamespace(requires_api_key=False)
    bot.annotate.return_value = (e for e in [{"type": "done", "counts": {}}])
    r = c.post("/api/annotate", json={"query": "q", "items": [
        {"item_id": "1", "passages": "not a list", "tags": "x"}, {"item_id": "2", "passages": ["text", {"text": "ok"}]}]})
    assert r.status_code == 200
    args, kwargs = bot.annotate.call_args
    assert args[1][0]["passages"] == [] and args[1][1]["passages"] == [{"page": None, "text": "ok"}]
    assert kwargs["workers"] == 1


def test_the_clerk_may_use_a_cloud_model_only_when_the_desk_allows_it(client, monkeypatch):
    c, bot = client
    c.post("/api/search", json={"query": "q"})
    assert bot.clerk.allow_cloud is False
    monkeypatch.setattr(main, "load_settings", lambda *a, **k: {**SETTINGS, "deskClerkCloud": True})
    c.post("/api/search", json={"query": "q"})
    assert bot.clerk.allow_cloud is True


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


def test_filters_off_still_keeps_scope_phrases_out_of_the_search_text(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    with patch("backend.interface.rerank_passages", rerank_in_order([3.0])):
        out = bot.search("riders since 2015", use_metadata_filters=False)
    assert out["scope"]["topic"] == "riders" and out["scope"]["extracted"] == {} and out["scope"]["read_by"] is None
    assert bot.chroma.query_hybrid_rrf.call_args.kwargs["query"] == "riders"


def test_search_returns_a_ranked_bibliography_with_citations(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0), ("2", 0), ("1", 0))
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0, 6.0, -6.0])):
        out = bot.search("riders")
    assert [it["item_id"] for it in out["items"]] == ["2", "1"]
    assert out["items"][0]["citation"]["item_key"] == "KEY2"
    assert out["items"][1]["band"] == "good"
    assert out["see_also_count"] == 0
    assert out["scope"] == {"manual": {}, "extracted": {}, "extracted_ignored": False,
                            "topic": "riders", "read_by": "library", "read_reason": ""}
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


def test_the_model_reading_sets_topic_and_scope(bot):
    from backend.clerk import Result
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    reading = {"topic": "riders", "year_min": 2015, "year_max": None, "author": None, "tags": [],
               "collections": [], "item_types": [], "exclude": []}
    bot.clerk = Mock()
    bot.clerk.run.return_value = Result(reading, "model")
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        out = bot.search("riders who struck since 2015", read_with_model=True, read_timeout=3)
    assert bot.clerk.run.call_args.kwargs["timeout"] == 3
    assert out["scope"]["read_by"] == "model" and out["scope"]["extracted"] == {"year_min": 2015}
    assert bot.chroma.query_hybrid_rrf.call_args.kwargs["query"] == "riders"


def test_a_failed_model_reading_falls_back_to_the_library_and_says_why(bot):
    from backend.clerk import Result
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    bot.clerk = Mock()
    bot.clerk.run.side_effect = lambda job, data, timeout=None: Result(data["library_reading"], "fallback", "timeout")
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        out = bot.search("riders since 2015", read_with_model=True)
    assert out["scope"]["read_by"] == "library" and out["scope"]["read_reason"] == "timeout"
    assert out["scope"]["extracted"] == {"year_min": 2015}


def test_excluded_terms_drop_matching_passages(bot):
    bot.chroma.query_hybrid_rrf.return_value = {
        "documents": [["riders and medical imaging", "riders on strike"]],
        "metadatas": [[{"item_id": "1", "title": "A", "page": 1}, {"item_id": "2", "title": "B", "page": 1}]]}
    with patch("backend.interface.rerank_passages", rerank_in_order([3.0, 2.0])):
        out = bot.search("riders, not medical imaging")
    assert [it["item_id"] for it in out["items"]] == ["2"]
    assert out["scope"]["extracted"] == {"exclude": ["medical imaging"]}


def test_excluded_items_are_filtered_out_in_the_search(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        bot.search("riders", exclude_item_ids=["9"])
    assert bot.chroma.query_hybrid_rrf.call_args.kwargs["where"] == {"item_id": {"$nin": ["9"]}}


def test_annotate_runs_next_searches_and_writes_no_notes():
    from types import SimpleNamespace
    from backend.clerk import Result
    from backend.interface import ZoteroChatbot

    order = []

    class FakeClerk:
        def available(self):
            return True

        def model(self):
            return "fake/model"

        def run(self, job, data):
            order.append(job.name)
            return Result([{"term": "Labour", "relation": "related"}], "model")

    items = [{"item_id": str(i), "title": f"T{i}", "tags": ["Labour"], "band": "good",
              "passages": [{"page": 1, "text": "x"}]} for i in range(5)]
    items.append({"item_id": "s", "title": "Ts", "tags": ["Weak only"], "band": "see_also", "passages": [{"page": 1, "text": "x"}]})
    me = SimpleNamespace(clerk=FakeClerk(), embedding_model_id="none", _vocabulary=lambda: {"common_tags": {"Common"}})
    events = list(ZoteroChatbot.annotate(me, "q", items, themes=False, workers=1))

    assert order == ["also_try"]
    assert [e["type"] for e in events] == ["also_try", "done"]
    assert events[-1]["counts"]["model"] == 1
    # Nothing listed (only "see also" rows): no next searches are suggested from their tags.
    order.clear()
    events = list(ZoteroChatbot.annotate(me, "q", items[5:], themes=False, workers=1))
    assert order == [] and [e["type"] for e in events] == ["done"]


def test_one_failed_annotate_job_does_not_end_the_stream():
    from types import SimpleNamespace
    from backend.clerk import Result
    from backend.interface import ZoteroChatbot

    class Clerk:
        def available(self):
            return True

        def model(self):
            return "m"

        def run(self, job, data):
            if job.name == "also_try":
                raise RuntimeError("embedding service down")
            return Result({1: "Labour"}, "model")

    items = [{"item_id": str(i), "title": f"T{i} labour", "tags": ["Labour"], "band": "good", "passages": [{"page": 1, "text": "x"}]}
             for i in range(9)]
    me = SimpleNamespace(clerk=Clerk(), embedding_model_id="x", _vocabulary=lambda: {"common_tags": set()})
    with patch("backend.clerk_jobs.cluster_items", return_value=[{"id": 1, "item_ids": ["0"], "titles": ["T0"], "tags": [[]]}]):
        events = list(ZoteroChatbot.annotate(me, "q", items, workers=1))
    assert [e["type"] for e in events] == ["themes", "done"] and events[-1]["counts"]["reasons"] == {"error": 1}


def test_an_item_set_aside_is_not_pinned_back_as_the_known_item(bot):
    bot.chroma.query_hybrid_rrf.return_value = hits(("1", 0))
    bot.zlib.find_items_by_creator_year.return_value = ["9"]
    with patch("backend.interface.rerank_passages", rerank_in_order([2.0])):
        assert [k["item_id"] for k in bot.search("Woodcock 2020")["known_items"]] == ["9"]
        assert bot.search("Woodcock 2020", exclude_item_ids=["9"])["known_items"] == []
