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
    assert c.get("/api/profiles/default/desk").json() == {"pins": [], "log": [], "context": []}


def test_pins_and_log_round_trip_through_the_profile_file(client):
    c, pm = client
    log = [{"query": "courier strikes", "scope": {"year_min": 2015, "tags": ["Labour"]}, "count": 12, "at": 2}]
    assert c.put("/api/profiles/default/desk", json={"pins": [PIN], "log": log}).status_code == 200
    assert c.get("/api/profiles/default/desk").json() == {"pins": [PIN], "log": log, "context": []}
    assert pm.get_profile_desk_file("default").exists()


def test_unknown_fields_are_dropped_and_sizes_capped(client):
    c, _ = client
    pins = [{**PIN, "id": f"p{i}", "text": "x" * 10000, "html": "<b>"} for i in range(600)] + [{"no": "id"}, "junk"]
    log = [{"query": "q", "scope": {"year_min": "not a year"}, "count": True}]
    out = c.put("/api/profiles/default/desk", json={"pins": pins, "log": log}).json()
    assert len(out["pins"]) == main.DESK_PIN_LIMIT and len(out["pins"][0]["text"]) == 4000 and "html" not in out["pins"][0]
    assert out["pins"][-1]["id"] == "p599"  # the newest are kept
    assert out["log"] == [{"query": "q", "scope": {}, "count": 0, "at": 0}]


def test_the_context_folder_round_trips_and_defaults_to_attached(client):
    c, _ = client
    entries = [{**PIN, "id": "7", "attached": False}, {**PIN, "id": "8", "itemId": "8"}, {"no": "id"}]
    out = c.put("/api/profiles/default/desk", json={"pins": [], "log": [], "context": entries}).json()
    assert [(e["id"], e["attached"]) for e in out["context"]] == [("7", False), ("8", True)]
    assert c.get("/api/profiles/default/desk").json()["context"] == out["context"]


def test_bad_profile_ids_and_unknown_profiles_are_refused(client):
    c, _ = client
    assert c.get("/api/profiles/..%2Fetc/desk").status_code in (400, 404)
    assert c.put("/api/profiles/nobody/desk", json={"pins": [], "log": []}).status_code == 404


def test_an_unreadable_file_is_moved_aside_not_overwritten(client):
    c, pm = client
    path = pm.get_profile_desk_file("default")
    path.write_text("{ half a file")
    assert c.get("/api/profiles/default/desk").json() == {"pins": [], "log": [], "context": []}
    assert path.with_suffix(".json.bad").read_text() == "{ half a file" and not path.exists()


def test_a_failed_save_keeps_the_old_settings(client, monkeypatch):
    _, pm = client
    pm.save_profile_settings("default", {"providers": {"openai": {"credentials": {"api_key": "sk-x"}}}})

    def full_disk(obj, fp, **kwargs):
        fp.write('{"prov')
        fp.flush()
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as patched:
        patched.setattr("backend.profile_manager.json.dump", full_disk)
        assert pm.save_profile_settings("default", {"providers": {}}) is False
    assert pm.load_profile_settings("default")["providers"]["openai"]["credentials"]["api_key"] == "sk-x"


def test_corrupt_settings_are_kept_aside_for_recovery(client):
    _, pm = client
    path = pm.get_profile_settings_file("default")
    path.write_text('{"providers": {"openai"')
    assert pm.load_profile_settings("default") == {}
    assert path.with_suffix(".json.bad").read_text() == '{"providers": {"openai"'


def test_corrupt_sessions_are_an_error_not_an_empty_history(client):
    c, pm = client
    pm.get_profile_sessions_file("default").write_text('{"sessions": {"a"')
    assert c.get("/api/profiles/default/sessions").status_code == 500


def test_a_transient_read_error_leaves_the_desk_file_alone(client, monkeypatch):
    _, pm = client
    pm.save_desk_state("default", {"pins": [PIN], "log": [], "context": []})

    def sharing_violation(path):
        raise PermissionError(13, "in use")

    with monkeypatch.context() as patched:
        patched.setattr(pm, "_read_json", sharing_violation)
        with pytest.raises(PermissionError):
            pm.load_desk_state("default")
    assert pm.load_desk_state("default")["pins"][0]["id"] == PIN["id"]


def test_settings_are_private_to_the_user(client):
    _, pm = client
    pm.save_profile_settings("default", {"providers": {}})
    assert pm.get_profile_settings_file("default").stat().st_mode & 0o777 == 0o600


def test_deleting_the_active_profile_leaves_a_usable_one(client):
    _, pm = client
    pm.create_profile("second", "Second")
    assert pm.delete_profile("default", force=True) is True
    assert pm.get_active_profile()["id"] == "second"


def test_an_active_profile_file_naming_a_deleted_profile_heals_itself(client):
    _, pm = client
    pm.create_profile("second", "Second")
    pm.ACTIVE_PROFILE_FILE.write_text('{"activeProfileId": "gone"}')
    assert pm.get_active_profile()["id"] in ("default", "second")


def test_the_only_profile_cannot_be_deleted(client):
    _, pm = client
    with pytest.raises(ValueError):
        pm.delete_profile("default", force=True)


def test_a_damaged_profile_json_keeps_settings_and_starts(client):
    _, pm = client
    pm.save_profile_settings("default", {"zoteroPath": "/mine"})
    pm.get_profile_metadata_file("default").write_text('{"id": "def')
    restarted = ProfileManager()
    assert restarted.get_active_profile()["id"] == "default"
    assert restarted.load_profile_settings("default") == {"zoteroPath": "/mine"}


def test_a_brief_read_error_is_retried(client, monkeypatch):
    _, pm = client
    path = pm.get_profile_settings_file("default")
    path.write_text('{"theme": "dark"}')
    real_open, failures = open, [PermissionError(13, "held by antivirus")]

    def flaky_open(file, *args, **kwargs):
        if failures and str(file) == str(path):
            raise failures.pop()
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", flaky_open)
    assert pm.load_profile_settings("default") == {"theme": "dark"}


def test_a_lasting_read_error_is_not_mistaken_for_empty_settings(client, monkeypatch):
    _, pm = client
    monkeypatch.setattr(pm, "_read_json", lambda path: (_ for _ in ()).throw(PermissionError(13, "held")))
    with pytest.raises(PermissionError):
        pm.load_profile_settings("default")

