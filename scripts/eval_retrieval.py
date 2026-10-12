"""Score the desk's retrieval against a test set, in-process (no running app needed).

Companion to eval_ranking.py, which goes through the API. This one builds the
pipeline directly, so it can run against a *copy* of the index with uncommitted
code, which is how a chunking change is measured before it costs anyone a reindex.

    python scripts/eval_retrieval.py run --out run-before.json
    python scripts/eval_retrieval.py run --chroma /path/to/other/index --out run-after.json
    python scripts/eval_ranking.py compare run-before.json run-after.json

The test set (profile folder, eval/testset.json) adds to eval_ranking's judgments:
"passage" queries name the page their answer is on, so passage-level hits are
scored too, and every query's displayed passages are checked for junk (reference
lists, boilerplate) and broken words (line-break hyphens, ligatures) that the
PDF pipeline should not have let through.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval_ranking import fit_platt, key_of, mean, ranked, score_query  # noqa: E402

PROFILE = Path("~/.zotero-llm/profiles/default").expanduser()
TOP_ITEMS = 10

# ---- passage-quality heuristics ------------------------------------------------
from backend.chunking import looks_like_references  # noqa: E402

_BOILERPLATE = re.compile(r"Downloaded from|All rights reserved|©|Copyright \d|Creative Commons|Terms (?:of|and) "
                          r"(?:Use|Conditions)|This content downloaded|For personal use only", re.I)
_BROKEN = re.compile(r"[a-z]-\s*\n\s*[a-z]|[\ufb00-\ufb06]")


def passage_flags(text: str) -> dict:
    return {
        "junk": looks_like_references(text) or bool(_BOILERPLATE.search(text)),
        "broken": bool(_BROKEN.search(text)),
        "midsentence": text[:1].islower(),
    }


# ---- scoring -------------------------------------------------------------------

def score(q: dict, res: dict) -> dict:
    keys = [e["key"] for e in ranked(res)]
    grades = {it["key"]: int(it["grade"]) for it in q["items"]}
    row = {"query": q["query"], "intent": q["intent"], **score_query(keys, grades),
           "hit@10": int(any(grades.get(k, 0) >= 1 for k in keys[:TOP_ITEMS])),
           "ms": res.get("timing_ms", {}).get("total")}
    shown = [p for it in res["items"][:TOP_ITEMS] for p in it.get("passages", [])]
    flags = [passage_flags(p["text"]) for p in shown]
    for name in ("junk", "broken", "midsentence"):
        row[f"{name}@10"] = round(sum(f[name] for f in flags) / len(flags), 3) if flags else None
    if q.get("target"):
        target = q["target"]
        pages = [p.get("page") for it in res["items"][:TOP_ITEMS] if key_of(it) == target["key"]
                 for p in it.get("passages", [])]
        row["page_hit"] = int(any(p and abs(p - target["page"]) <= 1 for p in pages))
        # The desk's extract is what the reader sees first: did the best passage come from the right page?
        first = next((it for it in res["items"] if key_of(it) == target["key"]), None)
        row["extract_page_hit"] = int(bool(first and first.get("passages")
                                           and first["passages"][0].get("page")
                                           and abs(first["passages"][0]["page"] - target["page"]) <= 1))
    return row


METRICS = ("ndcg@10", "p@5", "rr", "hit@10", "page_hit", "extract_page_hit", "junk@10", "broken@10", "midsentence@10")


def summarise(rows: list) -> dict:
    out = {}
    for intent in ["all"] + sorted({r["intent"] for r in rows}):
        sub = [r for r in rows if intent == "all" or r["intent"] == intent]
        out[intent] = {m: mean([r.get(m) for r in sub]) for m in METRICS if any(r.get(m) is not None for r in sub)}
        out[intent]["n"] = len(sub)
    ms = sorted(r["ms"] for r in rows if r.get("ms") is not None)
    out["all"]["median_ms"] = ms[len(ms) // 2] if ms else None
    return out


# ---- commands ------------------------------------------------------------------

def build_bot(args):
    settings = json.loads((PROFILE / "settings.json").read_text())
    from backend.interface import ZoteroChatbot
    return ZoteroChatbot(
        db_path=args.zotero or settings["zoteroPath"],
        chroma_path=args.chroma or settings["chromaPath"],
        embedding_model_id=args.embedding or settings.get("embeddingModel", "bge-base"),
        storage_path=settings.get("pdfStoragePath") or None,
    )


def run(args):
    testset = json.loads(Path(args.testset).expanduser().read_text())
    bot = build_bot(args)
    rows = []
    for q in testset["queries"]:
        started = time.perf_counter()
        res = bot.search(q["query"], use_metadata_filters=True, read_with_model=False)
        res.setdefault("timing_ms", {})["total"] = round((time.perf_counter() - started) * 1000)
        row = score(q, res)
        rows.append(row)
        page = f"page {row['page_hit']}/{row['extract_page_hit']}  " if "page_hit" in row else ""
        print(f"  ndcg {row['ndcg@10'] if row['ndcg@10'] is not None else '-':>5}  rr {row['rr']:.2f}  {page}"
              f"junk {row['junk@10'] if row['junk@10'] is not None else '-':>5}  {row['query'][:70]!r}")
    summary = summarise(rows)
    for intent, s in summary.items():
        print(f"{intent:10} " + "  ".join(f"{k} {v}" for k, v in s.items()))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "queries": rows}, indent=1, ensure_ascii=False))
        print(f"wrote {args.out}")


def calibrate(args):
    """Platt scaling of the reranker's logit on judged items, as eval_ranking.py calibrate, in-process."""
    import math
    testset = json.loads(Path(args.testset).expanduser().read_text())
    bot = build_bot(args)
    xs, ys = [], []
    for q in testset["queries"]:
        grades = {it["key"]: int(it["grade"]) for it in q["items"]}
        # Topic and scoped queries were judged over the whole collection, so an unlisted
        # item is a negative there; passage queries judged only their target item.
        whole = q["intent"] in ("topic", "scoped")
        for it in bot.search(q["query"], use_metadata_filters=True, read_with_model=False)["items"]:
            grade = grades.get(key_of(it), 0 if whole else None)
            if grade is not None:
                xs.append(float(it["score"]))
                ys.append(1 if grade >= 1 else 0)
    a, b = fit_platt(xs, ys)
    print(f"Fitted on {len(xs)} judged items ({sum(ys)} relevant): P(relevant) = sigmoid({a:.3f} * score + {b:.3f})")
    for band, p in (("strong", 0.8), ("good", 0.5), ("weak", 0.2)):
        print(f"  {band:7} P >= {p}: score >= {(math.log(p / (1 - p)) - b) / a:.2f}")
    print("Compare with BAND_CUTOFFS in backend/desk.py before changing them.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--testset", default=str(PROFILE / "eval" / "testset.json"))
    p.add_argument("--chroma", help="index directory (default: the profile's live index)")
    p.add_argument("--zotero", help="zotero.sqlite path (default: from settings)")
    p.add_argument("--embedding", help="embedding model id (default: from settings)")
    p.add_argument("--out")
    p.set_defaults(fn=run)
    c = sub.add_parser("calibrate")
    for name in ("--testset", "--chroma", "--zotero", "--embedding"):
        c.add_argument(name, default=str(PROFILE / "eval" / "testset.json") if name == "--testset" else None)
    c.set_defaults(fn=calibrate)
    args = parser.parse_args()
    args.fn(args)
