"""Measure a model on the reference desk's clerk jobs.

Runs every case in backend/tests/fixtures/clerk_eval.json through the jobs,
guards and fallbacks the app uses, and reports, per job, how often the model's
answer survives its guard and, for query reading, how often what the reader
finally gets is right, next to the library reader that needs no model.

    python scripts/eval_clerk.py --provider lmstudio --model qwen3-4b-instruct-2507 --base-url http://localhost:1234
    python scripts/eval_clerk.py --provider ollama --model qwen3:4b-instruct
    python scripts/eval_clerk.py --profile          # the model the active profile uses

--record adds the summary to backend/clerk_models.json, which the app reads to
label a model "measured". Notes are also printed in full for a human read: the
guards check faithfulness, not whether a note is useful.
"""

import argparse
import json
import re
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import clerk_jobs  # noqa: E402
from backend.clerk import MEASURED_FILE, Clerk, _normalise_model  # noqa: E402
from backend.model_providers import ProviderManager  # noqa: E402

FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "clerk_eval.json"
EMPTY = {"year_min": None, "year_max": None, "author": None, "tags": [], "collections": [], "item_types": [], "exclude": []}


def manager(args) -> ProviderManager:
    if args.profile:
        from backend.profile_manager import ProfileManager
        pm = ProfileManager()
        settings = pm.load_profile_settings(pm.get_active_profile()["id"])
        creds = {pid: cfg.get("credentials", {}) for pid, cfg in settings.get("providers", {}).items() if cfg.get("enabled")}
        return ProviderManager(active_provider_id=settings["activeProviderId"], active_model=settings.get("activeModel"), credentials=creds)
    creds = {k: v for k, v in {"base_url": args.base_url, "api_key": args.api_key}.items() if v}
    return ProviderManager(active_provider_id=args.provider, active_model=args.model, credentials={args.provider: creds})


def score_reading(reading, case):
    """Errors in a reading: wrong fields, missing topic words, scope words left in the topic."""
    expected = {**EMPTY, **case["expect"]}
    errors = []
    for field, want in expected.items():
        got = reading.get(field)
        if isinstance(want, list):
            if {str(v).lower() for v in got or []} != {str(v).lower() for v in want}:
                errors.append(f"{field}={got} (want {want})")
        elif (got.lower() if isinstance(got, str) else got) != (want.lower() if isinstance(want, str) else want):
            errors.append(f"{field}={got} (want {want})")
    topic = clerk_jobs._words(reading.get("topic", ""))
    for word in case.get("topic_has", []):
        if not clerk_jobs._words(word) <= topic:
            errors.append(f"topic lacks '{word}'")
    for word in case.get("topic_not", []):
        if word.lower() in reading.get("topic", "").lower():
            errors.append(f"topic keeps '{word}'")
    return errors


def median(values):
    return round(statistics.median(values)) if values else None


def run(args):
    fx = json.loads(FIXTURES.read_text())
    clerk = Clerk(manager(args))
    clerk.allow_cloud = True  # running the evaluation against a cloud model is the reader's explicit choice
    if not clerk.available():
        sys.exit(f"No model available for {clerk.model() or 'the given provider'}; check the provider settings.")
    print(f"Model: {clerk.model()}\n")
    report = {"model": clerk.model(), "date": date.today().isoformat(), "hardware": args.hardware, "jobs": {}}

    # -- read_query --------------------------------------------------------------
    vocab, today = fx["vocab"], date.fromisoformat(fx["today"])
    rows = []
    print("READ_QUERY")
    for case in fx["read_query"]:
        data = clerk_jobs.read_query_input(case["query"], vocab, today)
        result = clerk.run(clerk_jobs.READ_QUERY, data, timeout=args.timeout)
        final = score_reading(result.value, case)
        library = score_reading(data["library_reading"], case)
        rows.append({"query": case["query"], "group": case.get("group", "plain"), "source": result.source, "reason": result.reason,
                     "ms": result.ms, "final_errors": final, "library_errors": library, "reading": result.value})
        mark = "ok " if not final else "ERR"
        print(f"  {mark} {result.source:8} {result.ms:6} ms  {case['query']!r}" + (f"  -> {'; '.join(final)}" if final else ""))
    asked = [r for r in rows if not r["reason"].startswith("not_needed")]
    summary = {
        "cases": len(rows),
        "model_asked": len(asked),
        "model_used": sum(r["source"] == "model" for r in rows),
        "correct": sum(not r["final_errors"] for r in rows),
        "library_reader_correct": sum(not r["library_errors"] for r in rows),
        "by_group": {g: {"cases": sum(r["group"] == g for r in rows),
                         "correct": sum(r["group"] == g and not r["final_errors"] for r in rows),
                         "library_reader_correct": sum(r["group"] == g and not r["library_errors"] for r in rows)}
                     for g in dict.fromkeys(r["group"] for r in rows)},
        "median_ms_when_asked": median([r["ms"] for r in asked]),
        "fallback_reasons": sorted({r["reason"] for r in rows if r["reason"] and not r["reason"].startswith("not_needed")}),
    }
    print(f"  -> correct {summary['correct']}/{summary['cases']} (library reader alone {summary['library_reader_correct']}); "
          f"model asked {summary['model_asked']}, median {summary['median_ms_when_asked']} ms when asked")
    for g, n in summary["by_group"].items():
        print(f"     {g:6} {n['correct']}/{n['cases']} (library reader alone {n['library_reader_correct']})")
    print()
    report["jobs"]["read_query"] = {"summary": summary, "cases": rows}

    # -- note ---------------------------------------------------------------------
    rows = []
    print("NOTE")
    for case in fx["note"]:
        data = {"query": case["query"], "title": case["title"], "passages": case["passages"]}
        result = clerk.run(clerk_jobs.NOTE, data, timeout=args.timeout)
        value = result.value or {}
        rows.append({"id": case["id"], "source": result.source, "reason": result.reason, "ms": result.ms,
                     "note": value.get("note"), "page": value.get("page"), "support": value.get("support"), "raw": result.raw[:400]})
        shown = value.get("note") or f"(kept the extract: {result.reason})"
        print(f"  {result.source:8} {result.ms:6} ms  [{case['id']}] {shown}")
    used = [r for r in rows if r["source"] == "model"]
    summary = {"cases": len(rows), "model_used": len(used), "median_ms": median([r["ms"] for r in used]),
               "guard_catches": sorted({r["reason"] for r in rows if r["reason"].startswith("guard")})}
    print(f"  -> notes used {summary['model_used']}/{summary['cases']}, median {summary['median_ms']} ms\n")
    report["jobs"]["note"] = {"summary": summary, "cases": rows}

    # -- also_try -----------------------------------------------------------------
    rows = []
    print("ALSO_TRY")
    for case in fx["also_try"]:
        result = clerk.run(clerk_jobs.ALSO_TRY, case, timeout=args.timeout)
        rows.append({"query": case["query"], "source": result.source, "reason": result.reason, "ms": result.ms, "suggestions": result.value})
        print(f"  {result.source:8} {result.ms:6} ms  {case['query']!r}: " + ", ".join(f"{s['relation']} {s['term']}" for s in result.value))
    used = [r for r in rows if r["source"] == "model"]
    report["jobs"]["also_try"] = {"summary": {"cases": len(rows), "model_used": len(used), "median_ms": median([r["ms"] for r in used])}, "cases": rows}
    print()

    # -- themes -------------------------------------------------------------------
    rows = []
    print("THEMES")
    for case in fx["themes"]:
        result = clerk.run(clerk_jobs.THEMES, case, timeout=args.timeout)
        rows.append({"source": result.source, "reason": result.reason, "ms": result.ms, "labels": result.value})
        print(f"  {result.source:8} {result.ms:6} ms  " + " | ".join(str(v) for v in result.value.values()))
    used = [r for r in rows if r["source"] == "model"]
    report["jobs"]["themes"] = {"summary": {"cases": len(rows), "model_used": len(used), "median_ms": median([r["ms"] for r in used])}, "cases": rows}

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nReport written to {args.out}")
    if args.record:
        record(report, args)


def record(report, args):
    """Add this model's summary to backend/clerk_models.json, or update its entry.

    An existing entry whose patterns match the model keeps its label and patterns
    (which may name the same model in other runtimes, e.g. Ollama tags).
    """
    table = json.loads(MEASURED_FILE.read_text()) if MEASURED_FILE.exists() else {"models": []}
    name = _normalise_model(report["model"])
    results = {job: data["summary"] for job, data in report["jobs"].items()}
    entry = next((m for m in table["models"] if any(re.search(p, name) for p in m.get("match", []))), None)
    if entry is None:
        entry = {"label": args.label or name, "match": [f"^{re.escape(name)}$"]}
        table["models"].append(entry)
    elif args.label:
        entry["label"] = args.label
    entry.update(measured=report["date"], hardware=args.hardware, results=results)
    MEASURED_FILE.write_text(json.dumps(table, indent=2, ensure_ascii=False) + "\n")
    print(f"Recorded {entry['label']} in {MEASURED_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--profile", action="store_true", help="use the active profile's provider and model")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds per call (the app uses shorter limits)")
    parser.add_argument("--hardware", default="", help='where it ran, e.g. "Apple M1, 16 GB"')
    parser.add_argument("--label", help="display name for --record")
    parser.add_argument("--out", help="write the full report as JSON here")
    parser.add_argument("--record", action="store_true", help="add the summary to backend/clerk_models.json")
    run(parser.parse_args())
