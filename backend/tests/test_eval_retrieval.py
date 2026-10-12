"""Scoring in scripts/eval_retrieval.py: item metrics, passage-page hits and passage-quality flags."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("eval_retrieval", Path(__file__).parents[2] / "scripts" / "eval_retrieval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def _item(key, passages):
    return {"item_id": key, "title": key, "year": 2020, "citation": {"item_key": key},
            "passages": [{"page": p, "text": t} for p, t in passages]}


def test_passage_query_scores_page_hits_and_flags_junk():
    res = {"items": [
        _item("B", [(9, "Smith, J. (2010) Things. London: Press. Jones, A. (2011) More. Oxford: Press. Lee, B. (2012) Yet. Press.")]),
        _item("A", [(5, "classiﬁcation of inter-\npretability"), (4, "A clean sentence about the topic.")]),
    ], "timing_ms": {"total": 10}}
    q = {"query": "q", "intent": "passage", "items": [{"key": "A", "grade": 2}], "target": {"key": "A", "page": 4}}
    row = ev.score(q, res)
    assert row["rr"] == 0.5 and row["hit@10"] == 1
    assert row["page_hit"] == 1 and row["extract_page_hit"] == 1, "page 5 is within one of the target page 4"
    assert row["junk@10"] == round(1 / 3, 3) and row["broken@10"] == round(1 / 3, 3)


def test_summary_groups_by_intent():
    rows = [{"intent": "topic", "ndcg@10": 1.0, "p@5": 0.2, "rr": 1.0, "hit@10": 1, "junk@10": 0.0, "ms": 5},
            {"intent": "passage", "ndcg@10": 0.5, "p@5": 0.2, "rr": 0.5, "hit@10": 1, "page_hit": 0, "junk@10": 0.5, "ms": 7}]
    s = ev.summarise(rows)
    assert s["all"]["n"] == 2 and s["all"]["rr"] == 0.75 and s["all"]["median_ms"] == 7
    assert s["passage"]["page_hit"] == 0 and "page_hit" not in s["topic"]
