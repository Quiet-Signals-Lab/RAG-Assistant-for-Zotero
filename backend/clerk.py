"""The desk clerk: small, structured model jobs with guards and fallbacks.

Every model call the reference desk makes goes through Clerk.run(). A job is a
short prompt, a JSON schema, a guard that checks the answer against the job's
own input, and a fallback that needs no model. The model can only improve on
the fallback: when it is missing, slow, malformed or fails its guard, the desk
uses the fallback and says why.

The design follows docs/DESK_CLERK.md, which records the research behind it:
- constrained decoding guarantees syntax, never meaning, so every job has a guard;
- small models fail on parametric knowledge, so jobs choose from candidates
  drawn from the library rather than generate freely;
- a malformed answer gets one retry with the error; a guard failure gets none,
  because a retry only teaches the model to slip past the guard;
- each call has a time limit, so a slow local model never holds up the desk;
- a job may decline when the answer without a model is already complete, so the
  model is asked only about what the library's own data cannot settle.
"""

import concurrent.futures
import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

import jsonschema

from backend.model_providers import Message

logger = logging.getLogger(__name__)

# Shared by every job. Short on purpose: small models follow a few plain rules
# better than a long persona.
PREAMBLE = (
    "You work at the reference desk of a personal research library. "
    "You describe requests and documents; you never answer questions or state facts about the world. "
    "Use only what you are given. Reply with one JSON object that matches the requested fields, and nothing else."
)


class GuardFailure(Exception):
    """The model's answer was well formed but not supported by the job's input."""


@dataclass
class Job:
    """One kind of clerk task.

    prompt(data) builds the instructions and input; schema is a JSON schema, or a
    function of data when the allowed values depend on the input (candidate lists);
    guard(output, data) returns the cleaned output or raises GuardFailure;
    fallback(data) is the answer without a model; skip(data), if given, returns a
    reason when that answer is already complete and the model need not be asked.
    """

    name: str
    prompt: Callable[[Dict[str, Any]], str]
    schema: Union[Dict[str, Any], Callable[[Dict[str, Any]], Dict[str, Any]]]
    guard: Callable[[Dict[str, Any], Dict[str, Any]], Any]
    fallback: Callable[[Dict[str, Any]], Any]
    max_tokens: int = 200
    timeout: float = 30.0
    skip: Optional[Callable[[Dict[str, Any]], str]] = None

    def schema_for(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.schema(data) if callable(self.schema) else self.schema


@dataclass
class Result:
    value: Any
    source: str  # "model" or "fallback"
    reason: str = ""  # why the fallback was used: no_model, not_needed: ..., timeout, provider_error, malformed, guard: ...
    ms: int = 0
    model: str = ""
    raw: str = field(default="", repr=False)  # last model output, for evaluation reports


_THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_json(text: str) -> Any:
    """The JSON object in a model reply, ignoring thinking blocks and code fences."""
    text = _THINK.sub("", text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def shape(schema: Dict[str, Any], long_enum: int = 8) -> str:
    """A one-line template of the reply a schema asks for, for the prompt.

    Small models fill in a template; given the raw JSON Schema, Llama 3.2 3B echoed
    the schema back in 8 of 10 note calls. Providers that enforce schemas still
    receive the full one through response_format.
    """
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    if "enum" in schema:
        values = schema["enum"]
        if len(values) > long_enum:
            return "<one of the values listed above>"
        listed = ", ".join(json.dumps(v) for v in values)
        return f"<one of {listed}>"
    if "object" in kinds:
        props = schema.get("properties", {})
        return "{" + ", ".join(f'"{k}": {shape(v, long_enum)}' for k, v in props.items()) + "}"
    if "array" in kinds:
        if schema.get("maxItems") == 0:
            return "[]"
        most, least = schema.get("maxItems"), schema.get("minItems")
        count = f" {most} in all" if most and most == least else f" up to {most}" if most else ""
        return f"[{shape(schema.get('items', {}), long_enum)}, …{count}]"
    names = {"string": '"<text>"', "integer": "<whole number>", "number": "<number>", "boolean": "<true or false>", "null": "null"}
    return " or ".join(names.get(k, "<value>") for k in kinds if k)


def _repair(value: Any, schema: Dict[str, Any]) -> Any:
    """Read the two harmless slips small models make as what they mean, instead of retrying.

    A null or missing list is an empty list ("exclude": null; Qwen3-4B did it twice
    running), and a string of digits where a whole number is wanted is that number
    ("page": "118"; Qwen3 1.7B).
    """
    if not isinstance(value, dict) or schema.get("type") != "object":
        return value
    for key, prop in schema.get("properties", {}).items():
        kinds = prop.get("type") if isinstance(prop.get("type"), list) else [prop.get("type")]
        if prop.get("type") == "array" and value.get(key) is None:
            value[key] = []
        elif "integer" in kinds and isinstance(value.get(key), str) and value[key].strip().isdigit():
            value[key] = int(value[key])
    return value


def _key(job: Job, model: str, data: Dict[str, Any]) -> str:
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return f"{job.name}:{model}:{hashlib.sha1(blob.encode()).hexdigest()}"


class Clerk:
    """Runs jobs against the active provider, with a small result cache."""

    def __init__(self, provider_manager, cache_size: int = 1024, workers: int = 4):
        self.provider_manager = provider_manager
        # A cloud provider is used only when the reader allowed it for the desk (main.py).
        self.allow_cloud = False
        self._cache: "OrderedDict[str, Result]" = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        # Calls run on this pool so a time limit can abandon them; the provider's own
        # request timeout then closes the connection so a local server stops generating.
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="clerk")

    # ------------------------------------------------------------------ #

    def model(self) -> str:
        pm = self.provider_manager
        if pm is None:
            return ""
        try:
            return f"{pm.active_provider_id}/{pm.get_active_model() or ''}"
        except Exception:
            return ""

    def available(self) -> bool:
        """A provider is selected, enabled with credentials, and a model is chosen; a cloud one only if allowed."""
        pm = self.provider_manager
        if pm is None:
            return False
        try:
            pid = pm.active_provider_id
            model = pm.get_active_model()
            provider = pm.get_active_provider()
        except Exception:
            return False
        if not pid or not model or provider is None:
            return False
        if getattr(provider, "requires_api_key", False):
            return self.allow_cloud and bool(pm.get_credentials(pid).get("api_key"))
        return True

    def run(self, job: Job, data: Dict[str, Any], timeout: Optional[float] = None) -> Result:
        """Run one job. Never raises: every failure becomes the fallback with a reason."""
        started = time.perf_counter()
        model = self.model()

        def done(value, source, reason="", raw=""):
            result = Result(value, source, reason, round((time.perf_counter() - started) * 1000), model, raw)
            if source == "model" or reason.startswith("guard") or reason == "malformed":
                self._remember(_key(job, model, data), result)
            return result

        if not self.available():
            return done(job.fallback(data), "fallback", "no_model")
        declined = job.skip(data) if job.skip else ""
        if declined:
            return done(job.fallback(data), "fallback", f"not_needed: {declined}")

        cached = self._recall(_key(job, model, data))
        if cached is not None:
            return cached

        limit = timeout or job.timeout
        future = self._pool.submit(self._ask, job, data, limit)
        try:
            outcome, raw = future.result(timeout=limit)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return done(job.fallback(data), "fallback", "timeout")
        except Exception as e:  # provider down, auth, rate limit: the desk carries on
            logger.info("Clerk job %s failed: %s", job.name, e)
            return done(job.fallback(data), "fallback", "provider_error")

        if isinstance(outcome, Exception):
            reason = "malformed" if not isinstance(outcome, GuardFailure) else f"guard: {outcome}"
            logger.debug("Clerk job %s fell back (%s); raw=%r", job.name, reason, raw[:300])
            return done(job.fallback(data), "fallback", reason, raw)
        return done(outcome, "model", "", raw)

    # ------------------------------------------------------------------ #

    def _system_prompt(self) -> str:
        # Hybrid Qwen3 models think before answering unless told not to, and spend a
        # job's whole token budget doing it (Qwen3 1.7B: 10 of 10 notes empty). Ollama
        # gets think: false; servers with an OpenAI API only have the prompt switch.
        # The 2507 Instruct models do not think and need no switch.
        model = self.model().lower()
        if "qwen3" in model and not re.search(r"instruct|2507", model):
            return PREAMBLE + " /no_think"
        return PREAMBLE

    def _ask(self, job: Job, data: Dict[str, Any], limit: float):
        """Call the model, parse and validate, with one retry for malformed output.

        Returns (cleaned value or the exception that ended the attempt, raw reply).
        """
        schema = job.schema_for(data)
        prompt = job.prompt(data) + "\n\nReply with one JSON object of this shape:\n" + shape(schema)
        messages = [Message(role="system", content=self._system_prompt()), Message(role="user", content=prompt)]
        raw = ""
        for attempt in range(2):
            reply = self.provider_manager.chat(
                messages=messages,
                temperature=0.0,
                max_tokens=job.max_tokens,
                response_schema=schema,
                timeout=limit,
            )
            raw = reply.content or ""
            try:
                parsed = _repair(parse_json(raw), schema)
                jsonschema.validate(parsed, schema)
            except (ValueError, jsonschema.ValidationError) as e:
                if attempt == 0:
                    problem = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
                    messages += [
                        Message(role="assistant", content=raw[:2000]),
                        Message(role="user", content=f"That reply was not valid ({problem}). Reply again with only the JSON object."),
                    ]
                    continue
                return ValueError(str(e)), raw
            try:
                return job.guard(parsed, data), raw
            except GuardFailure as e:
                return e, raw
        return ValueError("no valid reply"), raw

    def _recall(self, key: str) -> Optional[Result]:
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
            return hit

    def _remember(self, key: str, result: Result) -> None:
        with self._lock:
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)


# ---------------------------------------------------------------------- #
# Measured models                                                          #
# ---------------------------------------------------------------------- #

MEASURED_FILE = Path(__file__).with_name("clerk_models.json")


def _normalise_model(name: str) -> str:
    """Comparable model name across runtimes: "mlx-community/Qwen3-4B-Instruct-2507-4bit",
    "qwen3:4b-instruct-2507-q4_K_M" and "qwen3-4b-instruct-2507" all become "qwen3-4b-instruct-2507"."""
    n = name.lower().split("/")[-1].replace(":", "-").replace("_", "-")
    n = re.sub(r"-(?:\d+bit|q\d[\w-]*|fp16|bf16|gguf|mlx|instruct-?gguf|latest)$", "", n)
    return n


def measured(model: str) -> Optional[Dict[str, Any]]:
    """The desk's own evaluation results for a model, if it has been measured.

    Results come from scripts/eval_clerk.py and live in backend/clerk_models.json.
    """
    try:
        table = json.loads(MEASURED_FILE.read_text())
    except (OSError, ValueError):
        return None
    name = _normalise_model(model)
    for entry in table.get("models", []):
        if any(re.search(p, name) for p in entry.get("match", [])):
            return entry
    return None
