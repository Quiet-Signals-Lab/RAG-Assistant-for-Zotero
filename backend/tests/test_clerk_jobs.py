"""Guards and fallbacks of the clerk's jobs. The model is not called here; the
eval script (scripts/eval_clerk.py) runs the same jobs against a real one."""

from datetime import date

import jsonschema
import pytest

from backend import clerk_jobs as jobs
from backend.clerk import GuardFailure

VOCAB = {
    "authors": ["Berlant", "Woodcock", "Kant"],
    "tags": ["Labour", "Security", "Affect theory"],
    "collections": ["PhD Research", "Security", "Reading group"],
    "item_types": ["book", "bookSection", "journalArticle", "thesis", "report"],
}
TODAY = date(2026, 10, 11)


def reading(**over):
    base = {"topic": "", "year_min": None, "year_max": None, "author": None,
            "tags": [], "collections": [], "item_types": [], "exclude": []}
    base.update(over)
    return base


def d_read(query):
    return jobs.read_query_input(query, VOCAB, TODAY)["library_reading"]


def guard_read(query, **model_out):
    """The guarded reading for a model reply (which has no topic: the guard derives it)."""
    d = jobs.read_query_input(query, VOCAB, TODAY)
    out = reading(**model_out)
    del out["topic"]
    jsonschema.validate(out, jobs.READ_QUERY.schema_for(d))
    return jobs.READ_QUERY.guard(out, d)


# --- READ_QUERY ---------------------------------------------------------------

def test_spans_index_the_request_as_the_guard_sees_it():
    """A double space or pasted newline in the request must not shift the spans the guard cuts."""
    d = jobs.read_query_input("courier  strikes\nsince 2015 by Berlant", VOCAB, TODAY)
    assert d["query"] == "courier strikes since 2015 by Berlant"
    assert all(d["query"][a:b] == d["query"][a:b].strip() and d["query"][a:b] for a, b in d["library_spans"])
    assert guard_read("courier  strikes since 2015 by Berlant", author="Berlant")["topic"] == "courier strikes"


def test_read_query_input_carries_the_library_reading_and_a_shortlist():
    d = jobs.read_query_input("what does Berlant argue about security", VOCAB, TODAY)
    assert d["today"] == "2026-10-11"
    assert d["candidates"]["authors"] == ["Berlant"] and "Security" in d["candidates"]["tags"]
    assert jobs.READ_QUERY.fallback(d) == d["library_reading"]


def test_read_query_schema_only_allows_shortlisted_names():
    d = jobs.read_query_input("papers by Berlant", VOCAB, TODAY)
    schema = jobs.READ_QUERY.schema_for(d)
    reply = {k: v for k, v in reading().items() if k != "topic"}
    jsonschema.validate({**reply, "author": "Berlant"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**reply, "author": "Haraway"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**reply, "tags": ["Labour"]}, schema)  # not shortlisted for this request


@pytest.mark.parametrize("query, asked", [
    ("courier strikes since 2015", False),           # the library reader found the date
    ("recent work on platform labour", False),       # "recent" sets no year
    ("Berlant's books on affect", False),
    ("anything Woodcock has written about riders", True),
    ("work from the nineties on labour unions", False),  # the library reader knows decades by name
    ("affect theory with the tag labour", True),
    ("surveillance chapters before 2000", True),
    ("readings from my thesis folder on affect", True),
])
def test_the_model_is_asked_only_when_the_library_reader_leaves_a_limit_unread(query, asked):
    d = jobs.read_query_input(query, VOCAB, TODAY)
    assert (jobs.READ_QUERY.skip(d) == "") is asked


def test_the_library_reading_wins_where_it_found_something():
    d = jobs.read_query_input("Berlant's books on affect since 2010", VOCAB, TODAY)
    model = reading(year_min=2009, item_types=["bookSection"])
    del model["topic"]
    out = jobs.READ_QUERY.guard(model, d)
    assert out == d["library_reading"] == reading(topic="affect", year_min=2010, author="Berlant", item_types=["book"])


def test_the_model_fills_what_the_library_reader_missed():
    out = guard_read("labour unions in the years after the war", year_min=1890, year_max=1910)
    assert out["year_min"] == 1890 and out["year_max"] == 1910 and not d_read("labour unions in the years after the war")["year_min"]


def test_an_open_end_is_no_limit_and_stated_years_are_copied():
    assert guard_read("unions post-2020", year_min=2021, year_max=2026)["year_max"] is None
    assert guard_read("unions until about 2000", year_max=2000)["year_max"] == 2000
    assert guard_read("unions until about 2000", year_max=1989)["year_max"] is None
    assert guard_read("unions in the years after the war", year_min=1910, year_max=1890)["year_min"] == 1890


def test_guard_drops_dates_the_request_never_gave():
    assert guard_read("platform labour", year_min=2021)["year_min"] is None


def test_an_author_limit_needs_the_request_to_ask_for_their_own_work():
    assert guard_read("what does Berlant argue about optimism", author="Berlant")["author"] is None
    out = guard_read("anything Woodcock has written about riders", author="Woodcock")
    assert out["author"] == "Woodcock" and out["topic"] == "riders"
    assert guard_read("Kant on beauty", author="Kant")["author"] == "Kant"


def test_a_loosely_named_collection_is_kept_but_not_one_matched_by_a_stray_word():
    out = guard_read("readings from my thesis folder on affect", collections=["PhD Research"])
    assert out["collections"] == ["PhD Research"] and out["topic"] == "affect"
    assert guard_read("readings from my thesis folder on affect", collections=["Reading group"])["collections"] == []
    assert guard_read("the folder structure of digital archives", collections=["PhD Research"])["collections"] == []
    assert guard_read("theories of collection in museums", collections=["PhD Research"])["collections"] == []


def test_guard_drops_a_tag_or_collection_that_is_only_a_topic_word():
    out = guard_read("security of machine learning", tags=["Security"], collections=["Security"])
    assert out["tags"] == [] and out["collections"] == []
    # a tag counts only when it is the one the request names
    assert guard_read("affect theory with the tag labour",
                      tags=["Labour", "Affect theory"])["tags"] == ["Labour"]


def test_a_kind_of_document_must_be_asked_for():
    assert guard_read("reports of police violence", item_types=["report"])["item_types"] == []
    assert guard_read("affect and optimism", item_types=["book"])["item_types"] == []
    out = guard_read("surveillance chapters before 2000", item_types=["bookSection"])
    assert out["item_types"] == ["bookSection"] and out["year_max"] == 1999 and out["topic"] == "surveillance"


def test_an_exclusion_needs_an_exclusion_marker():
    assert guard_read("why workers do not join unions", exclude=["join unions"])["exclude"] == []
    assert guard_read("affect and optimism", exclude=["politics"])["exclude"] == []
    out = guard_read("image classification but nothing on medical imaging", exclude=["medical imaging"])
    assert out["exclude"] == ["medical imaging"] and out["topic"] == "image classification"


def test_the_topic_is_the_request_without_every_phrase_read_as_a_limit():
    assert guard_read("anything Woodcock has written about riders", author="Woodcock")["topic"] == "riders"
    assert guard_read("Biggio and colleagues on poisoning", author=None)["topic"] == "Biggio and colleagues on poisoning"
    assert guard_read("affect theory with the tag labour", tags=["Labour"])["topic"] == "affect theory"
    out = guard_read("Kant on beauty in the 1790s", author="Kant")
    assert out == reading(topic="beauty", year_min=1790, year_max=1799, author="Kant")


# --- NOTE ---------------------------------------------------------------------

PASSAGES = [
    {"page": 118, "text": "Couriers used WhatsApp groups to organise log-offs across the city, a tactic that spread from Turin to London."},
    {"page": 112, "text": "Platform workers rarely meet, so the waiting zone became the new shop floor."},
]
NOTE_IN = {"query": "how couriers organise", "title": "The gig economy", "passages": PASSAGES}


@pytest.fixture
def entails(monkeypatch):
    import backend.embed_utils as eu
    score = {"value": 0.97}
    monkeypatch.setattr(eu, "entailment", lambda premises, hypothesis: score["value"])
    return score


def test_a_faithful_note_passes(entails):
    out = jobs.NOTE.guard({"note": "Describes how couriers used WhatsApp groups to organise log-offs in Turin and London", "page": 118}, NOTE_IN)
    assert out == {"note": "Describes how couriers used WhatsApp groups to organise log-offs in Turin and London.",
                   "page": 118, "support": 0.97}


@pytest.mark.parametrize("note, why", [
    ("Describes strikes organised by Deliveroo couriers in Madrid.", "not in the passages: Deliveroo"),
    ("Reports that 4,000 couriers joined the log-offs.", "not in the passages: 4,000"),
    ("Shows that WhatsApp groups were decisive for courier organising.", "evaluative: Shows that"),
    ("An important account of courier organising.", "evaluative: important"),
    ("Describes a study showing remote work raises productivity.", "evaluative: showing"),
])
def test_invented_or_evaluative_notes_fail(entails, note, why):
    with pytest.raises(GuardFailure, match=why):
        jobs.NOTE.guard({"note": note, "page": 118}, NOTE_IN)


def test_a_plural_or_compound_of_a_name_in_the_passages_is_not_a_new_name(entails):
    d = {"query": "q", "title": "T", "passages": [{"page": 3, "text": "We train a CNN with MCMC sampling."}]}
    assert jobs.NOTE.guard({"note": "Describes training CNNs with MCMC-based sampling.", "page": 3}, d)["page"] == 3


def test_the_entailment_check_sees_sentence_windows(monkeypatch):
    import backend.embed_utils as eu
    seen = {}
    monkeypatch.setattr(eu, "entailment", lambda premises, hypothesis: seen.update(p=premises, h=hypothesis) or 0.9)
    text = "One. Two. Three. Four."
    jobs.NOTE.guard({"note": "Describes how one leads to two.", "page": 1}, {"query": "q", "title": "T", "passages": [{"page": 1, "text": text}]})
    assert seen["h"] == "One leads to two."
    assert seen["p"] == [text, "One. Two. Three.", "Two. Three. Four."]


def test_an_unsupported_note_fails_the_entailment_check(entails):
    entails["value"] = 0.02
    with pytest.raises(GuardFailure, match="not supported"):
        jobs.NOTE.guard({"note": "Describes how a union called the strikes.", "page": 118}, NOTE_IN)


def test_only_the_first_sentence_is_kept_and_a_missing_page_takes_the_best_passage(entails):
    out = jobs.NOTE.guard({"note": "Discusses courier organising. It also covers waiting zones.", "page": None}, NOTE_IN)
    assert out["note"] == "Discusses courier organising." and out["page"] == 118


def test_note_schema_only_allows_the_passages_pages():
    schema = jobs.NOTE.schema_for(NOTE_IN)
    jsonschema.validate({"note": "x", "page": 112}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"note": "x", "page": 7}, schema)


def test_note_input_caps_the_passages():
    item = {"title": "T", "passages": [{"page": i, "text": "word " * 300} for i in range(5)]}
    d = jobs.note_input("q", item)
    assert len(d["passages"]) <= 3 and sum(len(p["text"]) for p in d["passages"]) <= 2400


# --- ALSO_TRY -------------------------------------------------------------------

ITEMS = [
    {"item_id": "1", "title": "Riders on the storm", "tags": ["Labour", "Platforms", "Gig economy"]},
    {"item_id": "2", "title": "Courier strikes", "tags": ["Labour", "Strikes"]},
    {"item_id": "3", "title": "Unions and platforms", "tags": ["Platforms", "Labour", "Unions"]},
]


def test_also_try_candidates_come_from_the_results_tags_most_common_first():
    d = jobs.also_try_input("courier organising", ITEMS)
    assert d["candidates"][:2] == ["Labour", "Platforms"]
    assert jobs.ALSO_TRY.fallback(d) == [{"term": "Labour", "relation": "related"},
                                         {"term": "Platforms", "relation": "related"},
                                         {"term": "Gig economy", "relation": "related"}]


def test_also_try_guard_drops_repeats_and_the_search_itself():
    d = {"query": "labour", "candidates": ["Labour", "Platforms", "Strikes"]}
    out = jobs.ALSO_TRY.guard({"terms": ["Labour", "Strikes", "Strikes"]}, d)
    assert out == [{"term": "Strikes", "relation": "related"}]


def test_relations_come_from_the_words_not_the_model():
    assert jobs.relation("Robustness", "deep learning robustness") == "broader"
    assert jobs.relation("Adversarial examples in vision", "adversarial examples") == "narrower"
    assert jobs.relation("Security", "adversarial examples") == "related"


# --- THEMES ---------------------------------------------------------------------

GROUPS = {"groups": [
    {"id": 1, "item_ids": ["1", "2"], "titles": ["Courier strikes in London", "Riders and strikes"], "tags": [["Labour"], ["Labour"]]},
    {"id": 2, "item_ids": ["3"], "titles": ["Algorithmic management at work"], "tags": [[]]},
]}


def test_theme_labels_must_reuse_the_groups_words():
    out = jobs.THEMES.guard({"labels": [{"id": 1, "label": "Courier strikes"}, {"id": 2, "label": "Late capitalism"}]}, GROUPS)
    assert out == {1: "Courier strikes", 2: "Algorithmic"}


def test_theme_fallback_prefers_a_shared_tag():
    assert jobs.THEMES.fallback(GROUPS) == {1: "Labour", 2: "Algorithmic"}


def test_too_few_items_are_not_clustered():
    assert jobs.cluster_items(ITEMS, embed=lambda texts: [[1.0, 0.0]] * len(texts)) == []
