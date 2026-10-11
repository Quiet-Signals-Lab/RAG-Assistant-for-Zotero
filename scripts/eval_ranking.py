"""Measure the desk's ranking on your own library (roadmap Stage 4: the test collection).

Cranfield-style: a set of queries, relevance judgments for the items they return,
and scores computed from those judgments. Judgments are about your library, so
they live in your profile folder, never in the repository. Runs go through the
app's own search endpoint, so start the app (or the backend) first.

    # 1. Pool: run each query and write the top items to a file you judge
    python scripts/eval_ranking.py pool queries.txt --out ~/.zotero-llm/profiles/default/judgments.json
    #    queries.txt: one query per line, optionally "intent<TAB>query"
    #    (intents: topic, known_item, scoped). In the file, set each item's "grade":
    #    2 = what you were looking for, 1 = useful, 0 = not relevant.

    # 2. Run: score the current ranking against your judgments
    python scripts/eval_ranking.py run ~/.zotero-llm/profiles/default/judgments.json --out run-a.json

    # 3. Compare two runs query by query (e.g. before and after a reindex)
    python scripts/eval_ranking.py compare run-a.json run-b.json

    # 4. Calibrate: fit P(relevant | reranker score) and propose band cut-offs
    python scripts/eval_ranking.py calibrate ~/.zotero-llm/profiles/default/judgments.json

Items are identified by their Zotero item key, which survives reindexing.
"""

import argparse
import json
import math
import sys
import urllib.request
from pathlib import Path

POOL_DEPTH = 20


def search(api: str, query: str) -> dict:
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(f"{api}/api/search", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def key_of(item: dict) -> str:
    return (item.get("citation") or {}).get("item_key") or f"id:{item['item_id']}"


def ranked(res: dict) -> list:
    """What the reader sees, in order: the known-item card above the list, then the list."""
    known = [{"key": key_of(k), "title": k["citation"]["title"], "year": k["citation"].get("year"), "extract": ""}
             for k in res.get("known_items", []) if k.get("citation")]
    listed = [{"key": key_of(it), "title": it["title"], "year": it["year"], "extract": (it.get("extract") or {}).get("text", "")}
              for it in res["items"]]
    seen, out = set(), []
    for entry in known + listed:
        if entry["key"] not in seen:
            seen.add(entry["key"])
            out.append(entry)
    return out


# -- metrics ---------------------------------------------------------------------

def dcg(grades):
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def ndcg(ranked_grades, all_grades, k=10):
    ideal = dcg(sorted(all_grades, reverse=True)[:k])
    return dcg(ranked_grades[:k]) / ideal if ideal else None


def precision(ranked_grades, k=5):
    top = ranked_grades[:k]
    return sum(g >= 1 for g in top) / k if top else 0.0


def reciprocal_rank(ranked_grades):
    return next((1 / (i + 1) for i, g in enumerate(ranked_grades) if g >= 1), 0.0)


def score_query(ranked_keys, grades):
    """Metrics for one query. Unjudged items count as not relevant (pooling's usual assumption)."""
    ranked = [grades.get(k, 0) for k in ranked_keys]
    return {"ndcg@10": ndcg(ranked, list(grades.values())), "p@5": precision(ranked), "rr": reciprocal_rank(ranked),
            "unjudged@10": sum(k not in grades for k in ranked_keys[:10])}


def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


# -- commands ----------------------------------------------------------------------

def pool(args):
    queries = []
    for line in Path(args.queries).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            intent, _, query = line.partition("\t") if "\t" in line else ("topic", "", line)
            queries.append({"intent": intent.strip(), "query": query.strip()})
    out = {"about": "Grades: 2 = what you were looking for, 1 = useful, 0 = not relevant. Keep this file private.",
           "queries": []}
    for q in queries:
        res = search(args.api, q["query"])
        items = [{**entry, "grade": None, "extract": entry["extract"][:240]} for entry in ranked(res)[:POOL_DEPTH]]
        out["queries"].append({**q, "items": items})
        print(f"pooled {len(items):2} items for {q['query']!r}")
    Path(args.out).expanduser().write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"Judge the items in {args.out}, then run: eval_ranking.py run {args.out}")


def load_judgments(path):
    data = json.loads(Path(path).expanduser().read_text())
    judged = []
    for q in data["queries"]:
        grades = {it["key"]: int(it["grade"]) for it in q["items"] if it.get("grade") is not None}
        if grades:
            judged.append({**q, "grades": grades})
    if not judged:
        sys.exit("No graded items yet: set each item's grade to 0, 1 or 2.")
    return judged


def run(args):
    rows = []
    for q in load_judgments(args.judgments):
        res = search(args.api, q["query"])
        keys = [entry["key"] for entry in ranked(res)]
        rows.append({"query": q["query"], "intent": q.get("intent", "topic"), **score_query(keys, q["grades"]),
                     "ms": res.get("timing_ms", {}).get("total")})
        r = rows[-1]
        print(f"  ndcg@10 {r['ndcg@10'] if r['ndcg@10'] is not None else '-':>5}  p@5 {r['p@5']:.2f}  rr {r['rr']:.2f}  "
              f"unjudged@10 {r['unjudged@10']:2}  {q['query']!r}")
    summary = {intent: {m: mean([r[m] for r in rows if r["intent"] == intent or intent == "all"])
                        for m in ("ndcg@10", "p@5", "rr")}
               for intent in ["all"] + sorted({r["intent"] for r in rows})}
    summary["all"]["median_ms"] = sorted(r["ms"] for r in rows if r["ms"] is not None)[len(rows) // 2] if rows else None
    for intent, s in summary.items():
        print(f"{intent:10} " + "  ".join(f"{k} {v}" for k, v in s.items()))
    if any(r["unjudged@10"] for r in rows):
        print("Some top-10 items are unjudged and count as not relevant: pool again to judge them.")
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "queries": rows}, indent=1, ensure_ascii=False))


def compare(args):
    a = {r["query"]: r for r in json.loads(Path(args.a).read_text())["queries"]}
    b = {r["query"]: r for r in json.loads(Path(args.b).read_text())["queries"]}
    diffs = [(q, b[q]["ndcg@10"] - a[q]["ndcg@10"]) for q in a.keys() & b.keys()
             if a[q]["ndcg@10"] is not None and b[q]["ndcg@10"] is not None]
    for q, d in sorted(diffs, key=lambda x: x[1]):
        print(f"  {d:+.3f}  {q!r}")
    wins, losses = sum(d > 0.001 for _, d in diffs), sum(d < -0.001 for _, d in diffs)
    print(f"B better on {wins}, worse on {losses}, level on {len(diffs) - wins - losses} of {len(diffs)} queries; "
          f"mean change {mean([d for _, d in diffs])}. Sign test p = {sign_test(wins, losses):.3f}")


def sign_test(wins, losses):
    """Two-sided exact sign test: how often a fair coin splits at least this unevenly."""
    n, k = wins + losses, min(wins, losses)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def calibrate(args):
    """Platt scaling: P(relevant) = 1 / (1 + exp(-(a * score + b))), fitted on judged items."""
    xs, ys = [], []
    for q in load_judgments(args.judgments):
        for it in search(args.api, q["query"])["items"]:
            grade = q["grades"].get(key_of(it))
            if grade is not None:
                xs.append(float(it["score"]))
                ys.append(1 if grade >= 1 else 0)
    if len(set(ys)) < 2 or len(xs) < 20:
        sys.exit(f"Need at least 20 judged items with both relevant and non-relevant ones (have {len(xs)}).")
    a, b = fit_platt(xs, ys)
    print(f"Fitted on {len(xs)} judged items ({sum(ys)} relevant): P(relevant) = sigmoid({a:.3f} * score + {b:.3f})")
    for band, p in (("strong", 0.8), ("good", 0.5), ("weak", 0.2)):
        print(f"  {band:7} P >= {p}: score >= {(math.log(p / (1 - p)) - b) / a:.2f}")
    print("Compare with BAND_CUTOFFS in backend/desk.py before changing them.")


def fit_platt(xs, ys):
    from sklearn.linear_model import LogisticRegression
    model = LogisticRegression(C=1e6).fit([[x] for x in xs], ys)
    return float(model.coef_[0][0]), float(model.intercept_[0])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="the running backend")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pool"); p.add_argument("queries"); p.add_argument("--out", required=True); p.set_defaults(fn=pool)
    p = sub.add_parser("run"); p.add_argument("judgments"); p.add_argument("--out"); p.set_defaults(fn=run)
    p = sub.add_parser("compare"); p.add_argument("a"); p.add_argument("b"); p.set_defaults(fn=compare)
    p = sub.add_parser("calibrate"); p.add_argument("judgments"); p.set_defaults(fn=calibrate)
    args = parser.parse_args()
    args.fn(args)
