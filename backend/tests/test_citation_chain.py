"""Citation chaining through Semantic Scholar: one request, only the DOI or title sent."""

from unittest.mock import Mock, patch

import pytest
import requests
from fastapi.testclient import TestClient

import backend.main as main
from backend.external_api_utils import fetch_citation_chain


def response(status, body=None):
    r = Mock(status_code=status, headers={})
    r.json.return_value = body or {}
    r.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(response=r)
    return r


PAPER = {"title": "Riders on the storm", "year": 2020, "url": "https://s2/p",
         "references": [{"title": "Old work", "year": 2001, "authors": [{"name": "A. Author"}], "externalIds": {"DOI": "10.1/X"}}],
         "citations": [{"title": "New work", "year": 2023, "authors": [], "externalIds": {}, "url": "https://s2/n"},
                       {"title": None}]}


def test_a_doi_is_looked_up_in_one_request():
    with patch("backend.external_api_utils.requests.get", return_value=response(200, PAPER)) as get:
        out = fetch_citation_chain(doi="10.1177/0950017019862954")
    assert get.call_count == 1 and get.call_args.args[0].endswith("/paper/DOI:10.1177/0950017019862954")
    assert out["references"] == [{"title": "Old work", "year": 2001, "authors": ["A. Author"], "doi": "10.1/x",
                                  "url": "https://doi.org/10.1/X"}]
    assert [c["title"] for c in out["cited_by"]] == ["New work"]


def test_without_a_doi_the_title_is_matched_first_and_unknown_papers_are_none():
    with patch("backend.external_api_utils.requests.get",
               side_effect=[response(200, {"data": [{"paperId": "abc"}]}), response(200, PAPER)]) as get:
        assert fetch_citation_chain(title="Riders on the storm")["title"] == "Riders on the storm"
    assert get.call_args_list[0].kwargs["params"]["query"] == "Riders on the storm"
    with patch("backend.external_api_utils.requests.get", return_value=response(404)):
        assert fetch_citation_chain(doi="10.0/none") is None


@pytest.fixture
def client(monkeypatch):
    bot = Mock()
    monkeypatch.setattr(main, "chatbot", bot)
    return TestClient(main.app), bot


def test_the_endpoint_explains_rate_limits_and_missing_items(client):
    c, bot = client
    assert c.post("/api/desk/chain", json={"item_id": "x"}).status_code == 400
    bot.citation_chain.side_effect = requests.HTTPError(response=Mock(status_code=429))
    r = c.post("/api/desk/chain", json={"item_id": "2"})
    assert r.status_code == 503 and "limiting" in r.json()["detail"]
    bot.citation_chain.side_effect = None
    bot.citation_chain.return_value = None
    assert c.post("/api/desk/chain", json={"item_id": "2"}).status_code == 404


def test_the_chain_marks_owned_works_with_their_citations():
    from backend.interface import ZoteroChatbot
    me = Mock()
    me.zlib.get_bibliographic.side_effect = lambda ids: {"2": {"doi": "https://doi.org/10.1177/X", "title": "T"},
                                                         "9": {"item_key": "OLDWORK1"}} if "2" in set(map(str, ids)) else {"9": {"item_key": "OLDWORK1"}}
    me.zlib.get_doi_and_title_index.return_value = ({"10.1/x": "9"}, {})
    with patch("backend.external_api_utils.requests.get", return_value=response(200, PAPER)) as get:
        out = ZoteroChatbot.citation_chain(me, "2")
    assert get.call_args.args[0].endswith("/paper/DOI:10.1177/X")
    assert out["found"] and out["references"][0]["owned_item_id"] == "9"
    assert out["references"][0]["citation"] == {"item_key": "OLDWORK1"} and out["cited_by"][0]["citation"] is None


def test_a_busy_api_is_tried_once_more():
    with patch("backend.external_api_utils.requests.get", side_effect=[response(429), response(200, PAPER)]) as get, \
            patch("time.sleep") as sleep:
        assert fetch_citation_chain(doi="10.1/x")["title"] == "Riders on the storm"
    assert get.call_count == 2 and sleep.call_args.args[0] == 1.5
    with patch("backend.external_api_utils.requests.get", side_effect=[response(429), response(429)]), patch("time.sleep"):
        with pytest.raises(requests.HTTPError):
            fetch_citation_chain(doi="10.1/x")
