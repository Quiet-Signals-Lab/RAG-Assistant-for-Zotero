"""Reading a request without a model: scope from the library's own vocabulary."""

from datetime import date

import pytest

from backend import query_reader

TODAY = date(2026, 10, 11)
VOCAB = {
    "authors": ["Berlant", "Woodcock", "Graham", "Kant", "de Beauvoir", "Biggio"],
    "tags": ["Labour", "Security", "Affect theory", "Platforms"],
    "collections": ["PhD Research", "Security", "Teaching 2024"],
    "item_types": ["book", "bookSection", "journalArticle", "thesis", "report"],
}


def read(q):
    return query_reader.read(q, VOCAB, TODAY)


@pytest.mark.parametrize("query, expected", [
    ("courier strikes since 2015", {"year_min": 2015, "topic": "courier strikes"}),
    ("papers by Berlant about optimism", {"author": "Berlant", "topic": "optimism"}),
    ("Berlant's books on affect", {"author": "Berlant", "item_types": ["book"], "topic": "affect"}),
    ("theses on algorithmic management from the last five years",
     {"item_types": ["thesis"], "year_min": 2021, "topic": "algorithmic management"}),
    ("adversarial attacks in my Security collection", {"collections": ["Security"], "topic": "adversarial attacks"}),
    ('adversarial attacks tagged "Security"', {"tags": ["Security"], "topic": "adversarial attacks"}),
    ("image classification, not medical imaging", {"exclude": ["medical imaging"], "topic": "image classification"}),
    ("travail de plateforme depuis 2018", {"year_min": 2018, "topic": "travail de plateforme"}),
    ("labour unions between 1990 and 1999", {"year_min": 1990, "year_max": 1999, "topic": "labour unions"}),
    ("feminist theory in the 1970s", {"year_min": 1970, "year_max": 1979, "topic": "feminist theory"}),
    ("strikes after 2020", {"year_min": 2021}),
    ("post-2020 research on algorithmic management", {"year_min": 2021, "topic": "algorithmic management"}),
    ("pre-2000 work on surveillance", {"year_max": 1999, "topic": "surveillance"}),
    ("work from the nineties on labour unions", {"year_min": 1990, "year_max": 1999, "topic": "labour unions"}),
    ("anything about riders", {"topic": "riders"}),
    ("research ethics", {"topic": "research ethics"}),             # a topic word, not request filler
    ("work-life balance", {"topic": "work-life balance"}),
    ("papers in 1990-2000", {"year_min": 1990, "year_max": 2000}),  # "in 1990" is part of the range
    ("courier strikes before the 1990s", {"year_max": 1989, "topic": "courier strikes"}),
    ("courier strikes since the 1990s", {"year_min": 1990, "topic": "courier strikes"}),
    ("courier strikes after the 1980s", {"year_min": 1990, "topic": "courier strikes"}),
    ("river trade in the 1800s", {"year_min": 1800, "year_max": 1899, "topic": "river trade"}),
    ("river trade in the 2000s", {"year_min": 2000, "year_max": 2009}),
    ("unions in the early nineties", {"year_min": 1990, "year_max": 1993, "topic": "unions"}),
    ("unions in the late 1980s", {"year_min": 1986, "year_max": 1989}),
    ("unions before 1990 or after 2000", {"year_min": None, "year_max": None}),  # no single range says that
    ("strikes before 2000", {"year_max": 1999}),
    ("the second sex by de Beauvoir", {"author": "de Beauvoir", "topic": "the second sex"}),
    ("readings in my PhD folder on affect", {"collections": ["PhD Research"]}),
    ("platform work excluding gig economy", {"exclude": ["gig economy"], "topic": "platform work"}),
])
def test_reads_scope_and_topic(query, expected):
    reading = read(query)
    for key, value in expected.items():
        assert reading[key] == value, (query, key, reading)


@pytest.mark.parametrize("query, field", [
    ("Kant's ethics of duty", "author"),            # a possessive alone is a topic, not an author filter
    ("by the sea in Victorian novels", "author"),    # "by" before a word that is no author in the library
    ("reports of police violence", "item_types"),    # a type word inside the topic
    ("how workers organise without unions", "exclude"),  # "without" is not an exclusion marker
    ("why do small models not generalise", "exclude"),
    ("security of machine learning", "collections"),  # a collection name used as a topic word
    ("recent work on platform labour", "year_min"),   # "recent" alone sets no date
])
def test_does_not_read_scope_into_the_topic(query, field):
    assert not read(query)[field], (query, read(query))


def test_a_name_that_is_not_in_the_library_stays_in_the_topic():
    reading = read("papers by Haraway on cyborgs")
    assert reading["author"] is None and "Haraway" in reading["topic"]


def test_nothing_to_read_leaves_the_query_as_the_topic():
    assert read("how do platform workers organise collectively") == {
        "topic": "how do platform workers organise collectively", "year_min": None, "year_max": None,
        "author": None, "tags": [], "collections": [], "item_types": [], "exclude": []}


def test_candidates_shortlist_what_the_request_might_mean():
    c = query_reader.candidates("what does Berlant argue about security and affect", VOCAB)
    assert c["authors"] == ["Berlant"]
    assert c["tags"] == ["Affect theory", "Security"]
    assert c["collections"] == ["Security"]
    assert c["item_types"] == sorted(VOCAB["item_types"])
