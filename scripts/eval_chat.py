"""Check the chat's answers against what the prompt promises, through the running app.

For each topical query in the profile's desk test set: a first question over the whole
library, a follow-up in the same session, and the same first question scoped to the
top three items of a search. Each answer is checked for what can be checked without a
judge: every [N] names a returned source, a number keeps its source across turns, how
many sentences carry a citation, whether the model wrote a reference list anyway, and
length. Faithfulness to the passages still needs a human read: --show prints answers.

    python scripts/eval_chat.py                    # needs the backend at 127.0.0.1:8000 and a model
    python scripts/eval_chat.py --limit 4 --show
"""

import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
import uuid
from pathlib import Path

PROFILE = Path("~/.zotero-llm/profiles/default").expanduser()
FOLLOW_UP = "Which of these is the earliest, and what does it argue?"
CITE = re.compile(r"\[(\d+)\]")
REFERENCES = re.compile(r"^\s*(#+\s*|\*\*)?(references|bibliography|sources)\b", re.I | re.M)


def post(api, path, body):
    req = urllib.request.Request(f"{api}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def check(answer, citations):
    """What is wrong with one answer, and its numbers."""
    ids = {c["id"] for c in citations}
    used = {int(n) for n in CITE.findall(answer)}
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.split()) >= 6]
    return {
        "words": len(answer.split()),
        "cited_share": round(sum(1 for s in sentences if CITE.search(s)) / len(sentences), 2) if sentences else None,
        "unknown_numbers": sorted(used - ids),
        "reference_list": bool(REFERENCES.search(answer)),
        "pages_in_brackets": len(re.findall(r"\[p\.", answer)),
        "headings_or_tables": len(re.findall(r"^(#+ |\*\*[^*]+\*\*:?\s*$|\|)", answer, re.M)),
    }


def run(args):
    queries = [q for q in json.loads(Path(args.queries).read_text())["queries"] if q.get("intent") == "topic" and q.get("expect", {}).get("good")]
    if args.limit:
        queries = queries[: args.limit]
    rows = []
    for q in queries:
        session = str(uuid.uuid4())
        t0 = time.time()
        first = post(args.api, "/api/chat", {"query": q["query"], "session_id": session})
        second = post(args.api, "/api/chat", {"query": FOLLOW_UP, "session_id": session})
        top = [it["item_id"] for it in post(args.api, "/api/search", {"query": q["query"]})["items"][:3]]
        scoped = post(args.api, "/api/chat", {"query": q["query"], "session_id": str(uuid.uuid4()), "item_ids": top}) if top else None
        names = {c["id"]: c["title"] for c in first["citations"]}
        renumbered = [c["id"] for c in second["citations"] if c["id"] in names and names[c["id"]] != c["title"]]
        row = {
            "query": q["query"],
            "first": check(first["summary"], first["citations"]),
            "follow_up": {**check(second["summary"], second["citations"]), "renumbered": renumbered},
            "scoped": check(scoped["summary"], scoped["citations"]) if scoped else None,
            "seconds": round(time.time() - t0),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
        if args.show:
            for label, res in (("first", first), ("follow-up", second), ("scoped", scoped)):
                if res:
                    print(f"\n--- {label}: {q['query']}\n{res['summary']}\n")
    print("\nSummary over", len(rows), "queries")
    for turn in ("first", "follow_up", "scoped"):
        checks = [r[turn] for r in rows if r[turn]]
        if not checks:
            continue
        shares = [c["cited_share"] for c in checks if c["cited_share"] is not None]
        print(f"  {turn:10s} answers with unknown [N]: {sum(1 for c in checks if c['unknown_numbers'])}/{len(checks)}"
              f" · with a reference list: {sum(1 for c in checks if c['reference_list'])}"
              f" · pages in brackets: {sum(c['pages_in_brackets'] for c in checks)}"
              f" · answers with headings or tables: {sum(1 for c in checks if c['headings_or_tables'])}"
              f" · median cited share: {statistics.median(shares) if shares else None}"
              f" · median words: {statistics.median(c['words'] for c in checks)}")
    print(f"  follow-ups where a number changed source: {sum(1 for r in rows if r['follow_up']['renumbered'])}/{len(rows)}")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--queries", default=str(PROFILE / "eval" / "desk_testset.json"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--show", action="store_true")
    p.add_argument("--out")
    run(p.parse_args())
