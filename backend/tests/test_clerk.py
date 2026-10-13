"""The clerk's run loop: parse, validate, retry once, guard, fall back, cache."""

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend import clerk
from backend.clerk import Clerk, GuardFailure, Job, parse_json


class FakeProvider:
    requires_api_key = False


class FakeManager:
    """Replies with the queued strings in order; records what it was sent."""

    def __init__(self, *replies, delay=0.0, error=None):
        self.replies = list(replies)
        self.calls = []
        self.delay = delay
        self.error = error
        self.active_provider_id = "ollama"

    def get_active_model(self):
        return "qwen3:4b-instruct-2507-q4_K_M"

    def get_active_provider(self):
        return FakeProvider()

    def get_credentials(self, pid=None):
        return {}

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.replies.pop(0))


def guard(out, data):
    if out["word"] not in data["allowed"]:
        raise GuardFailure(f"{out['word']} is not a candidate")
    return out["word"]


JOB = Job(
    name="pick",
    prompt=lambda d: f"Pick one of {d['allowed']}",
    schema={"type": "object", "additionalProperties": False, "required": ["word"],
            "properties": {"word": {"type": "string"}}},
    guard=guard,
    fallback=lambda d: d["allowed"][0],
    timeout=2.0,
)
DATA = {"allowed": ["alpha", "beta"]}


def test_parse_json_ignores_thinking_and_fences():
    assert parse_json('<think>hmm {"x": 0}</think>```json\n{"word": "beta"}\n```') == {"word": "beta"}
    with pytest.raises(ValueError):
        parse_json("no object here")


def test_a_good_answer_is_used_and_marked_as_the_models():
    mgr = FakeManager('{"word": "beta"}')
    result = Clerk(mgr).run(JOB, DATA)
    assert (result.value, result.source, result.reason) == ("beta", "model", "")
    messages, kwargs = mgr.calls[0]
    assert messages[0].role == "system" and kwargs["temperature"] == 0.0
    assert kwargs["response_schema"] == JOB.schema  # providers can constrain decoding


def test_malformed_output_gets_one_retry_with_the_error():
    mgr = FakeManager("Sure! The word is beta.", '{"word": "beta"}')
    result = Clerk(mgr).run(JOB, DATA)
    assert result.source == "model" and len(mgr.calls) == 2
    retry_messages = mgr.calls[1][0]
    assert retry_messages[-1].role == "user" and "not valid" in retry_messages[-1].content


def test_malformed_twice_falls_back():
    mgr = FakeManager("nope", '{"wrong": 1}')
    result = Clerk(mgr).run(JOB, DATA)
    assert (result.value, result.source, result.reason) == ("alpha", "fallback", "malformed")


def test_a_guard_failure_falls_back_without_a_retry():
    mgr = FakeManager('{"word": "gamma"}', '{"word": "beta"}')
    result = Clerk(mgr).run(JOB, DATA)
    assert result.source == "fallback" and result.reason.startswith("guard: gamma")
    assert len(mgr.calls) == 1


def test_a_slow_model_falls_back_at_the_time_limit():
    mgr = FakeManager('{"word": "beta"}', delay=1.0)
    started = time.perf_counter()
    result = Clerk(mgr).run(JOB, DATA, timeout=0.2)
    assert result.reason == "timeout" and time.perf_counter() - started < 0.8


def test_a_provider_error_falls_back():
    result = Clerk(FakeManager(error=RuntimeError("connection refused"))).run(JOB, DATA)
    assert result.reason == "provider_error: RuntimeError: connection refused"


def test_no_model_means_the_fallback_without_a_call():
    mgr = FakeManager('{"word": "beta"}')
    mgr.get_active_model = lambda: ""
    result = Clerk(mgr).run(JOB, DATA)
    assert result.reason == "no_model" and mgr.calls == []
    assert Clerk(None).run(JOB, DATA).reason == "no_model"


def test_answers_are_cached_per_model_and_input():
    mgr = FakeManager('{"word": "beta"}')
    c = Clerk(mgr)
    assert c.run(JOB, DATA).value == "beta"
    assert c.run(JOB, DATA).value == "beta" and len(mgr.calls) == 1
    mgr.replies.append('{"word": "alpha"}')
    assert c.run(JOB, {"allowed": ["alpha"]}).value == "alpha" and len(mgr.calls) == 2


def test_measured_models_match_across_runtimes(tmp_path, monkeypatch):
    table = tmp_path / "clerk_models.json"
    table.write_text('{"models": [{"label": "Qwen3 4B Instruct", "match": ["^qwen3-4b-instruct"]}]}')
    monkeypatch.setattr(clerk, "MEASURED_FILE", table)
    for name in ("ollama/qwen3:4b-instruct-2507-q4_K_M", "lmstudio/mlx-community/Qwen3-4B-Instruct-2507-4bit",
                 "lmstudio/qwen3-4b-instruct-2507"):
        assert clerk.measured(name)["label"] == "Qwen3 4B Instruct", name
    assert clerk.measured("ollama/llama3.2:3b") is None


def test_the_prompt_shows_the_reply_as_a_template_not_a_schema():
    from backend.clerk import shape
    schema = {"type": "object", "properties": {
        "note": {"type": "string"},
        "page": {"type": ["integer", "null"], "enum": [3, 4, None]},
        "tags": {"type": "array", "maxItems": 0, "items": {"type": "string"}},
        "labels": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "object", "properties": {"label": {"type": "string"}}}},
        "pick": {"type": "string", "enum": [str(i) for i in range(20)]},
        "year": {"type": ["integer", "null"]},
    }}
    assert shape(schema) == ('{"note": "<text>", "page": <one of 3, 4, null>, "tags": [], '
                             '"labels": [{"label": "<text>"}, … 2 in all], "pick": <one of the values listed above>, '
                             '"year": <whole number> or null}')


def test_a_null_list_and_a_numeric_string_are_read_as_meant_not_retried():
    from backend.clerk import _repair
    schema = {"type": "object", "properties": {"exclude": {"type": "array"}, "author": {"type": ["string", "null"]},
                                               "page": {"type": ["integer", "null"]}}}
    assert _repair({"exclude": None, "author": None, "page": "118"}, schema) == {"exclude": [], "author": None, "page": 118}
    assert _repair({"author": "7", "page": "p. 3"}, schema) == {"author": "7", "page": "p. 3", "exclude": []}


@pytest.mark.parametrize("model, switched", [
    ("mlx-community/Qwen3-1.7B-4bit", True), ("qwen3:4b", True),
    ("qwen3:4b-instruct-2507-q4_K_M", False), ("mlx-community/Qwen3-4B-Instruct-2507-4bit", False), ("llama3.2", False),
])
def test_hybrid_qwen3_models_are_told_not_to_think(model, switched):
    from backend.clerk import Clerk
    pm = Mock(active_provider_id="lmstudio")
    pm.get_active_model.return_value = model
    assert Clerk(pm)._system_prompt().endswith("/no_think") is switched


def test_a_cloud_provider_is_used_only_when_allowed():
    pm = Mock(active_provider_id="openai")
    pm.get_active_model.return_value = "gpt-x"
    pm.get_active_provider.return_value = SimpleNamespace(requires_api_key=True)
    pm.get_credentials.return_value = {"api_key": "sk-test"}
    c = Clerk(pm)
    assert c.available() is False
    c.allow_cloud = True
    assert c.available() is True


def test_strict_schema_modes_get_the_schema_without_size_limits():
    from backend.model_providers.base import structured_request
    schema = {"type": "object", "additionalProperties": False, "required": ["note", "tags"], "properties": {
        "note": {"type": "string", "maxLength": 300},
        "tags": {"type": "array", "maxItems": 4, "items": {"type": "string", "enum": ["a", "b"]}}}}
    sent = structured_request({"response_schema": schema})["response_format"]["json_schema"]["schema"]
    assert sent == {"type": "object", "additionalProperties": False, "required": ["note", "tags"], "properties": {
        "note": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}}}
    assert schema["properties"]["note"]["maxLength"] == 300  # the clerk's own copy keeps them for validation
