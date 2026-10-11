"""The ranking harness's metrics (scripts/eval_ranking.py)."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("eval_ranking", Path(__file__).parents[2] / "scripts" / "eval_ranking.py")
er = importlib.util.module_from_spec(spec)
spec.loader.exec_module(er)


def test_a_perfect_ranking_scores_one_and_unjudged_items_count_as_not_relevant():
    grades = {"A": 2, "B": 1, "C": 0}
    assert er.score_query(["A", "B", "C"], grades) == {"ndcg@10": 1.0, "p@5": 0.4, "rr": 1.0, "unjudged@10": 0}
    worse = er.score_query(["X", "C", "B", "A"], grades)
    assert worse["rr"] == pytest.approx(1 / 3) and worse["unjudged@10"] == 1 and 0 < worse["ndcg@10"] < 1


def test_sign_test_and_platt_fit():
    assert er.sign_test(0, 0) == 1.0 and er.sign_test(8, 0) == pytest.approx(2 / 256)
    a, b = er.fit_platt([-6, -5, -4, -1, 0, 1, 3, 4, 5, 6], [0, 0, 0, 0, 1, 0, 1, 1, 1, 1])
    assert a > 0  # higher reranker scores mean more likely relevant
