"""Pins and the query log, kept per profile in desk.json (GET/PUT /api/profiles/{id}/desk)."""

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.profile_manager import ProfileManager


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(ProfileManager, "BASE_DIR", tmp_path)
    monkeypatch.setattr(ProfileManager, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(ProfileManager, "ACTIVE_PROFILE_FILE", tmp_path / "active_profile.json")
    pm = ProfileManager()
    monkeypatch.setattr(main, "profile_manager", pm)
    return TestClient(main.app), pm


PIN = {"id": "7:12:Couriers used", "itemId": "7", "label": "Woodcock (2020)", "page": 12, "text": "Couriers used…",
       "query": "courier strikes", "at": 1}


def test_a_new_profile_has_an_empty_desk(client):
    c, _ = client
    assert c.get("/api/profiles/default/desk").json() == {"pins": [], "log": []}


def test_pins_and_log_round_trip_through_the_profile_file(client):
    c, pm = client
    log = [{"query": "courier strikes", "scope": {"year_min": 2015, "tags": ["Labour"]}, "count": 12, "at": 2}]
    assert c.put("/api/profiles/default/desk", json={"pins": [PIN], "log": log}).status_code == 200
    assert c.get("/api/profiles/default/desk").json() == {"pins": [PIN], "log": log}
    assert pm.get_profile_desk_file("default").exists()


def test_unknown_fields_are_dropped_and_sizes_capped(client):
    c, _ = client
    pins = [{**PIN, "id": f"p{i}", "text": "x" * 10000, "html": "<b>"} for i in range(600)] + [{"no": "id"}, "junk"]
    log = [{"query": "q", "scope": {"year_min": "not a year"}, "count": True}]
    out = c.put("/api/profiles/default/desk", json={"pins": pins, "log": log}).json()
    assert len(out["pins"]) == main.DESK_PIN_LIMIT and len(out["pins"][0]["text"]) == 4000 and "html" not in out["pins"][0]
    assert out["pins"][-1]["id"] == "p599"  # the newest are kept
    assert out["log"] == [{"query": "q", "scope": {}, "count": 0, "at": 0}]


def test_bad_profile_ids_and_unknown_profiles_are_refused(client):
    c, _ = client
    assert c.get("/api/profiles/..%2Fetc/desk").status_code in (400, 404)
    assert c.put("/api/profiles/nobody/desk", json={"pins": [], "log": []}).status_code == 404


def test_an_unreadable_file_is_moved_aside_not_overwritten(client):
    c, pm = client
    path = pm.get_profile_desk_file("default")
    path.write_text("{ half a file")
    assert c.get("/api/profiles/default/desk").json() == {"pins": [], "log": []}
    assert path.with_suffix(".json.bad").read_text() == "{ half a file" and not path.exists()
