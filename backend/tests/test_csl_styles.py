"""Drop-in CSL styles are read from Zotero's own styles folder and served by bare file name only."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture
def client(monkeypatch, tmp_path):
    (tmp_path / "styles").mkdir()
    (tmp_path / "styles" / "apa.csl").write_text('<?xml version="1.0"?><style><info><title>APA Style 7th edition</title></info></style>')
    (tmp_path / "styles" / "bare.csl").write_text("<style/>")
    (tmp_path / "secret.txt").write_text("not a style")
    bot = Mock()
    bot.zlib.db_path = str(tmp_path / "zotero.sqlite")
    monkeypatch.setattr(main, "chatbot", bot)
    return TestClient(main.app)


def test_styles_are_listed_with_their_titles(client):
    assert client.get("/api/csl/styles").json() == {"styles": [
        {"file": "apa.csl", "title": "APA Style 7th edition"}, {"file": "bare.csl", "title": "bare"},
    ]}


def test_a_style_is_served_and_nothing_else_is(client):
    r = client.get("/api/csl/styles/apa.csl")
    assert r.status_code == 200 and "<title>APA" in r.text and r.headers["content-type"].startswith("application/xml")
    assert client.get("/api/csl/styles/missing.csl").status_code == 404
    assert client.get("/api/csl/styles/..%2Fsecret.txt").status_code in (400, 404)
    assert client.get("/api/csl/styles/secret.txt").status_code == 400


def test_no_styles_folder_means_an_empty_list(client, monkeypatch):
    main.chatbot.zlib.db_path = "/nowhere/zotero.sqlite"
    assert client.get("/api/csl/styles").json() == {"styles": []}
