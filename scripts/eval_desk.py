"""Trace the reference desk end to end on a set of queries, through the running app.

For each query: the search (what came back, in which bands, what scope was read,
how long), then the model's work as the reader would receive it (`POST /api/annotate`,
each note, next-search list and theme label stamped with when it arrived), and
checks on each: judged retrieval metrics where the query is in the ranking test set,
the expectations the query set states, what was read from the query and by whom,
and heuristics for the model's output (next searches that are library-wide
category tags or echo the query, themes' labels).

    python scripts/eval_desk.py run --out run.json --report report.md
    python scripts/eval_desk.py run --only "images"          # queries containing a word
    python scripts/eval_desk.py compare run-before.json run-after.json

The query set lives in the profile folder (eval/desk_testset.json) because its
queries describe the owner's library. Each entry: {"intent", "query", "why",
"expect"}, where expect may hold: known ("doi" | "title" | "author_year"),
scope ({field: value} read from the query), scope_set_aside (the same, for a limit
that is read but matches nothing in the index), has_items (bool), good (bool: at
least one strong or good item), none_good (bool: a negative control), top_ids (item ids
of which at least one must be in the first three).
"""

import argparse
import json
import re
import sqlite3
import statistics
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_ranking import key_of, mean, ranked, score_query  # noqa: E402

PROFILE = Path("~/.zotero-llm/profiles/default").expanduser()
# A tag on this many items is a classification or housekeeping tag, not a next search (as ChromaClient.common_tags).
CATEGORY_MIN_ITEMS, CATEGORY_SHARE = 10, 0.01
_WORD = re.compile(r"[^\W_]+")
_STOP = {"a", "an", "and", "the", "of", "in", "on", "for", "to", "with", "by", "about", "not"}


# ---- the app ---------------------------------------------------------------------

def post(api, path, body, timeout=600):
    req = urllib.request.Request(f"{api}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def search(api, query):
    with post(api, "/api/search", {"query": query}) as r:
        return json.load(r)


def annotate(api, query, res):
    """The model's work, as the frontend requests it: every item, its first three passages."""
    items = [{"item_id": it["item_id"], "title": it["title"], "tags": it["tags"], "band": it["band"],
              "passages": [{"page": p["page"], "text": p["text"]} for p in it["passages"][:3]]} for it in res["items"]]
    started = time.perf_counter()
    with post(api, "/api/annotate", {"query": res["scope"].get("topic") or query, "items": items}) as r:
        for line in r:
            if line.strip():
                yield round((time.perf_counter() - started) * 1000), json.loads(line)


def category_tags(zotero_path):
    """Tags carried by a sizeable share of the library's PDF items."""
    conn = sqlite3.connect(f"file:{zotero_path}?mode=ro", uri=True)
    rows = conn.execute("""
        SELECT t.name, COUNT(DISTINCT it.itemID) FROM tags t JOIN itemTags it ON it.tagID = t.tagID
        WHERE it.itemID IN (SELECT parentItemID FROM itemAttachments WHERE contentType = 'application/pdf')
        GROUP BY t.name""").fetchall()
    total = conn.execute("SELECT COUNT(DISTINCT parentItemID) FROM itemAttachments WHERE contentType = 'application/pdf'").fetchone()[0]
    conn.close()
    floor = max(CATEGORY_MIN_ITEMS, CATEGORY_SHARE * total)
    return {name for name, n in rows if n >= floor}


# ---- checks ------------------------------------------------------------------------

def words(text):
    return {w.lower() for w in _WORD.findall(text or "")} - _STOP


def check_expectations(q, res):
    """Expectations the query set states, as a list of failures (empty when all hold)."""
    expect, failed = q.get("expect") or {}, []
    items, good = res["items"], [it for it in res["items"] if it["band"] in ("strong", "good")]
    known = [k for k in res["known_items"] if k.get("citation")]
    if "known" in expect and (not known or known[0]["kind"] != expect["known"]):
        failed.append(f"known item {expect['known']!r} expected, got {known[0]['kind'] if known else 'none'}")
    def same(got, want):
        if isinstance(want, list):
            return {str(v).lower() for v in got or []} == {str(v).lower() for v in want}
        return str(got).lower() == str(want).lower()
    aside = res["scope"]["extracted_ignored"]
    for key, want_aside in (("scope", False), ("scope_set_aside", True)):
        for field, want in (expect.get(key) or {}).items():
            got = res["scope"]["extracted"].get(field)
            if not same(got, want) or aside != want_aside:
                failed.append(f"{key} {field}={got!r} (want {want!r}){' and it was set aside' if aside else ''}")
    if expect.get("has_items") is True and not items:
        failed.append("no items")
    if expect.get("has_items") is False and items:
        failed.append(f"{len(items)} items where none were expected")
    if expect.get("top_ids") and not any(it["item_id"] in expect["top_ids"] for it in items[:3]):
        failed.append(f"none of {expect['top_ids']} in the top three: {[it['item_id'] for it in items[:3]]}")
    if expect.get("good") and not good:
        failed.append("no strong or good item")
    if expect.get("none_good") and good:
        failed.append(f"{len(good)} good items for a query the library should not answer: {good[0]['title'][:60]!r}")
    return failed


def trace(api, q, judged, categories):
    res = search(api, q["query"])
    listed = [it for it in res["items"] if it["band"] != "see_also"]
    row = {
        "query": q["query"], "intent": q["intent"], "why": q.get("why", ""),
        "search_ms": res["timing_ms"], "items": len(res["items"]), "listed": len(listed),
        "bands": dict(Counter(it["band"] for it in res["items"])),
        "known": [{"kind": k["kind"], "title": k["citation"]["title"], "indexed": k["indexed"]} for k in res["known_items"] if k.get("citation")],
        "read_by": res["scope"]["read_by"], "read_reason": res["scope"]["read_reason"],
        "topic": res["scope"]["topic"], "extracted": res["scope"]["extracted"], "extracted_ignored": res["scope"]["extracted_ignored"],
        "top": [{"rank": it["rank"], "band": it["band"], "title": it["title"][:80], "year": it["year"], "passages": len(it["passages"]),
                 "extract": it["extract"]["text"][:160]} for it in res["items"][:5]],
        "failed": check_expectations(q, res),
    }
    grades = judged.get(q["query"].lower())
    if grades:
        row["retrieval"] = score_query([e["key"] for e in ranked(res)], grades)

    events, also, themes, done = [], None, None, None
    for t, event in annotate(api, q["query"], res):
        kind = event["type"]
        if kind == "also_try":
            qw = words(res["scope"].get("topic") or q["query"])
            also = {"t": t, "source": event["source"], "terms": [
                {"term": s["term"], "relation": s["relation"],
                 "flags": [f for f, hit in (("category", s["term"] in categories), ("echo", bool(words(s["term"])) and words(s["term"]) <= qw)) if hit]}
                for s in event["suggestions"]]}
            events.append((t, f"also_try ({event['source']})"))
        elif kind == "themes":
            themes = {"t": t, "source": event["source"],
                      "groups": [{"label": g["label"], "size": len(g["item_ids"])} for g in event["groups"]]}
            events.append((t, f"themes ({event['source']})"))
        elif kind == "done":
            done = {"t": t, **event["counts"], "model_name": event.get("model")}
            events.append((t, "done"))
    row["model"] = {
        "events": events, "also_try": also, "themes": themes, "done": done,
        "first_ms": events[0][0] if events else None,
        # Work is meant to arrive in the order the reader looks: next searches before themes.
        "order_kept": also is None or themes is None or also["t"] <= themes["t"],
    }
    return row


# ---- summary and report --------------------------------------------------------------

def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values)) if values else None


def summarise(rows):
    judged = [r["retrieval"] for r in rows if r.get("retrieval")]
    models = [r["model"] for r in rows]
    reasons = Counter(k for m in models if m["done"] for k, n in (m["done"].get("reasons") or {}).items() for _ in range(n))
    terms = [t for m in models if m["also_try"] for t in m["also_try"]["terms"]]
    return {
        "queries": len(rows),
        "expectations_failed": sum(1 for r in rows if r["failed"]),
        "search_ms_median": median(r["search_ms"]["total"] for r in rows),
        "queries_with_a_good_item": sum(1 for r in rows if any(b in r["bands"] for b in ("strong", "good"))),
        "retrieval": {m: mean([j[m] for j in judged]) for m in ("ndcg@10", "p@5", "rr")} | {"judged": len(judged)},
        "annotate_ms_median": median(m["done"]["t"] for m in models if m["done"]),
        "first_event_ms_median": median(m["first_ms"] for m in models),
        "model_calls": sum((m["done"] or {}).get("model", 0) for m in models), "fallbacks": sum((m["done"] or {}).get("fallback", 0) for m in models),
        "fallback_reasons": dict(reasons),
        "read_by": dict(Counter(str(r["read_by"]) for r in rows)),
        "also_try": {"queries_with": sum(1 for m in models if m["also_try"]), "by_model": sum(1 for m in models if m["also_try"] and m["also_try"]["source"] == "model"),
                     "terms": len(terms), "category_terms": sum("category" in t["flags"] for t in terms), "echo_terms": sum("echo" in t["flags"] for t in terms)},
        "themes": {"queries_with": sum(1 for m in models if m["themes"]), "by_model": sum(1 for m in models if m["themes"] and m["themes"]["source"] == "model")},
        "order_kept": sum(1 for m in models if m["order_kept"]),
    }


def report(rows, summary):
    s = summary
    out = ["# Reference desk trace", "",
           f"{s['queries']} queries; {s['expectations_failed']} failed an expectation. Search median {s['search_ms_median']} ms; "
           f"a good or strong item on {s['queries_with_a_good_item']} queries.",
           f"Judged retrieval ({s['retrieval']['judged']} queries): nDCG@10 {s['retrieval']['ndcg@10']}, P@5 {s['retrieval']['p@5']}, RR {s['retrieval']['rr']}.",
           f"Queries read by {s['read_by']}. Model: first piece of work after a median {s['first_event_ms_median']} ms, all done after "
           f"{s['annotate_ms_median']} ms; {s['model_calls']} jobs by the model, {s['fallbacks']} fallbacks {s['fallback_reasons']}.",
           f"Next searches on {s['also_try']['queries_with']} queries ({s['also_try']['by_model']} chosen by the model): {s['also_try']['terms']} terms, "
           f"{s['also_try']['category_terms']} category tags, {s['also_try']['echo_terms']} echoing the query. "
           f"Themes on {s['themes']['queries_with']} queries ({s['themes']['by_model']} named by the model). Order kept on {s['order_kept']}.",
           "", "| query | intent | items (listed) | bands | read by | ms | next searches | themes | failed |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        m = r["model"]
        bands = " ".join(f"{n} {b.replace('_', ' ')}" for b, n in sorted(r["bands"].items(), key=lambda kv: ("strong", "good", "weak", "see_also").index(kv[0])))
        also = ", ".join(t["term"] + ("*" if t["flags"] else "") for t in m["also_try"]["terms"]) if m["also_try"] else "—"
        themes = ", ".join(g["label"] for g in m["themes"]["groups"]) if m["themes"] else "—"
        out.append(f"| {r['query'][:48]} | {r['intent']} | {r['items']} ({r['listed']}) | {bands} | {r['read_by']} | {r['search_ms']['total']} | "
                   f"{also[:70]} | {themes[:50]} | {'; '.join(r['failed'])[:60]} |")
    out += ["", "`*` a next search that is a library-wide category tag or echoes the query.", ""]
    for r in rows:
        m = r["model"]
        out += [f"## {r['query']}", f"*{r['intent']}* — {r['why']}", ""]
        scope = f"scope read by {r['read_by']}: {r['extracted'] or 'none'}{' (set aside)' if r['extracted_ignored'] else ''}; topic {r['topic']!r}"
        out.append(f"Search {r['search_ms']['total']} ms (read {r['search_ms']['read']}, retrieve {r['search_ms']['retrieve']}): {r['items']} items, {r['bands']}. {scope}.")
        for k in r["known"]:
            out.append(f"Known item ({k['kind']}): {k['title']}{'' if k['indexed'] else ' (not indexed)'}")
        if r.get("retrieval"):
            out.append(f"Judged: nDCG@10 {r['retrieval']['ndcg@10']}, RR {r['retrieval']['rr']}, unjudged in top 10: {r['retrieval']['unjudged@10']}")
        for f in r["failed"]:
            out.append(f"**Failed:** {f}")
        out.append("")
        for t in r["top"]:
            out.append(f"- r{t['rank']} [{t['band']}] {t['title']} ({t['year']}), {t['passages']} passages — “{t['extract']}”")
        out.append("")
        out.append("Model's work, ms after the list appeared:")
        if m["also_try"]:
            out.append(f"- +{m['also_try']['t']} next searches ({m['also_try']['source']}): " +
                       "; ".join(f"{t['term']} [{t['relation']}{', ' + ', '.join(t['flags']) if t['flags'] else ''}]" for t in m["also_try"]["terms"]))
        if m["themes"]:
            out.append(f"- +{m['themes']['t']} themes ({m['themes']['source']}): " + "; ".join(f"{g['label']} ({g['size']})" for g in m["themes"]["groups"]))
        if m["done"]:
            d = m["done"]
            out.append(f"- +{d['t']} done: {d.get('model', 0)} by the model, {d.get('fallback', 0)} fallbacks {d.get('reasons') or ''} {d.get('detail') or ''}")
        if not m["order_kept"]:
            out.append("- order: the themes arrived before the next searches")
        out.append("")
    return "\n".join(out)


# ---- commands -----------------------------------------------------------------------

def run(args):
    testset = json.loads(Path(args.queries).expanduser().read_text())
    queries = [q for q in testset["queries"] if not args.only or args.only.lower() in q["query"].lower()]
    judged = {}
    judgments = Path(args.judgments).expanduser()
    if judgments.exists():
        for q in json.loads(judgments.read_text())["queries"]:
            grades = {it["key"]: int(it["grade"]) for it in q["items"] if it.get("grade") is not None}
            if grades:
                judged[q["query"].lower()] = grades
    settings = json.loads((PROFILE / "settings.json").read_text())
    categories = category_tags(settings["zoteroPath"])
    rows = []
    for i, q in enumerate(queries, 1):
        row = trace(args.api, q, judged, categories)
        rows.append(row)
        m = row["model"]
        also = ", ".join(t["term"] + ("*" if t["flags"] else "") for t in m["also_try"]["terms"]) if m["also_try"] else "—"
        print(f"[{i}/{len(queries)}] {row['items']:2} items {row['search_ms']['total']:5} ms | read by {row['read_by']} {row['extracted'] or ''} "
              f"| {also[:60]} | {'FAILED: ' + '; '.join(row['failed']) if row['failed'] else 'ok'} | {q['query'][:50]!r}", flush=True)
    if args.out:  # the run is saved before it is summarised: a bug in the report must not cost the run
        Path(args.out).write_text(json.dumps({"queries": rows}, indent=1, ensure_ascii=False))
    summary = summarise(rows)
    print(json.dumps(summary, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "queries": rows}, indent=1, ensure_ascii=False))
    if args.report:
        Path(args.report).write_text(report(rows, summary))
        print(f"wrote {args.report}")


def compare(args):
    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())
    print("summary A → B")
    for key in ("expectations_failed", "search_ms_median", "annotate_ms_median", "first_event_ms_median", "order_kept", "model_calls", "fallbacks"):
        print(f"  {key}: {a['summary'][key]} → {b['summary'][key]}")
    for key in ("also_try", "themes", "retrieval", "read_by"):
        print(f"  {key}: {a['summary'][key]} → {b['summary'][key]}")
    rows_b = {r["query"]: r for r in b["queries"]}
    for ra in a["queries"]:
        rb = rows_b.get(ra["query"])
        if not rb:
            continue
        ta = [t["term"] + ("*" if t["flags"] else "") for t in (ra["model"]["also_try"] or {}).get("terms", [])]
        tb = [t["term"] + ("*" if t["flags"] else "") for t in (rb["model"]["also_try"] or {}).get("terms", [])]
        if ta != tb or ra["failed"] != rb["failed"] or ra["items"] != rb["items"]:
            print(f"\n{ra['query']!r}\n  items {ra['items']} → {rb['items']}; next searches: {ta} → {tb}; failed {ra['failed']} → {rb['failed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="the running backend")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--queries", default=str(PROFILE / "eval" / "desk_testset.json"))
    p.add_argument("--judgments", default=str(PROFILE / "eval" / "testset.json"), help="eval_ranking judgments, for retrieval metrics")
    p.add_argument("--only", help="run only queries containing this text")
    p.add_argument("--out")
    p.add_argument("--report")
    p.set_defaults(fn=run)
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(fn=compare)
    args = parser.parse_args()
    args.fn(args)
