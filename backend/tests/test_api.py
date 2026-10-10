"""Smoke tests for the HTTP API. The module imports without side effects, so
the chatbot and profile manager are replaced with mocks here."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture
def client(monkeypatch):
    bot = Mock()
    bot.is_indexing = False
    bot.embedding_model_id = "bge-base"
    bot.index_progress = {"processed_items": 1, "total_items": 2}
    bot.chroma.has_pdf_path.return_value = False
    bot.zlib.db_path = "/nowhere/zotero.sqlite"
    bot.zlib.storage_path = None
    monkeypatch.setattr(main, "chatbot", bot)
    pm = Mock()
    pm.get_active_profile.return_value = {"id": "default", "name": "Default"}
    pm.load_profile_settings.return_value = {}
    pm.get_profile_chroma_path.return_value = "/nowhere/chroma"
    monkeypatch.setattr(main, "profile_manager", pm)
    return TestClient(main.app), bot, pm


def test_import_has_no_side_effects():
    """Nothing is initialised at import; lifespan does it when the server starts."""
    assert main.chatbot is None
    assert main.profile_manager is None
    assert hasattr(main, "lifespan")


def test_health_endpoints(client):
    c, _, _ = client
    assert c.get("/health").json() == {"status": "healthy"}
    body = c.get("/api/health").json()
    assert body["components"]["database"]["path"] == main.DB_PATH


def test_index_status(client):
    c, bot, _ = client
    assert c.get("/api/index_status").json() == {"status": "idle", "progress": bot.index_progress}


def test_exceptions_become_500_with_detail(client):
    c, bot, _ = client
    bot.chroma.get_indexed_item_ids.side_effect = RuntimeError("disk on fire")
    r = c.get("/api/index_stats")
    assert r.status_code == 500
    assert r.json() == {"detail": "disk on fire"}


def test_missing_query_is_400(client):
    c, _, _ = client
    r = c.post("/api/chat", json={})
    assert r.status_code == 400
    assert "query" in r.json()["detail"]


def test_chat_passes_through(client):
    c, bot, _ = client
    bot.chat.return_value = {"summary": "hi", "citations": [], "snippets": [], "generated_title": None}
    r = c.post("/api/chat", json={"query": "q", "item_ids": "1, 2"})
    assert r.status_code == 200 and r.json()["summary"] == "hi"
    assert bot.chat.call_args.kwargs["filter_item_ids"] == ["1", "2"]


def test_profile_switch_blocked_while_indexing(client):
    c, bot, _ = client
    bot.is_indexing = True
    r = c.post("/api/profiles/other/activate")
    assert r.status_code == 409


def test_profile_id_validation(client):
    c, _, _ = client
    r = c.get("/api/profiles/bad%20id")
    assert r.status_code == 400
    assert "Invalid profile ID" in r.json()["detail"]


def test_open_pdf_outside_storage_is_forbidden(client, tmp_path):
    c, _, _ = client
    r = c.post("/api/open_pdf", json={"pdf_path": str(tmp_path / "x.pdf")})
    assert r.status_code == 403
    assert c.post("/api/open_pdf", json={}).status_code == 400


def test_open_pdf_accepts_indexed_linked_file(client, tmp_path, monkeypatch):
    c, bot, _ = client
    bot.chroma.has_pdf_path.return_value = True
    pdf = tmp_path / "linked.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    opened = []
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(main.platform, "system", lambda: "Darwin")
    r = c.post("/api/open_pdf", json={"pdf_path": str(pdf)})
    assert r.status_code == 200, r.text
    assert opened


def test_settings_masks_api_keys(client):
    c, _, pm = client
    pm.load_profile_settings.return_value = {"providers": {"openai": {"enabled": True, "credentials": {"api_key": "sk-secret-123"}}}}
    body = c.get("/api/settings").json()
    assert body["providers"]["openai"]["credentials"]["api_key"].endswith("123")
    assert "secret" not in body["providers"]["openai"]["credentials"]["api_key"]
