"""Ranking rules of the reference desk (backend/desk.py)."""

from backend import desk


def meta(item_id, page=1, title=None, year=2020, chunk_idx=0):
    return {"item_id": item_id, "page": page, "title": title or f"Title {item_id}", "year": year, "chunk_idx": chunk_idx,
            "authors": "A", "tags": "Labour,Platforms", "collections": "", "pdf_path": f"/{item_id}.pdf"}


# --- terms and highlighting -------------------------------------------------

def test_query_terms_drop_stopwords_digits_and_stem():
    assert desk.query_terms("How do platform workers organise collectively since 2015?") == [
        "platform", "worker", "organise", "collective",
    ]


def test_term_spans_match_inflections_both_ways():
    text = "Couriers organising strikes; the strike was organised."
    terms = desk.query_terms("organise strike")
    words = [text[a:b] for a, b in desk.term_spans(text, terms)]
    assert words == ["organising", "strikes", "strike", "organised"]


def test_short_terms_need_an_exact_match():
    assert desk.term_spans("lawyers and the law", desk.query_terms("law")) == [[16, 19]]


def test_cjk_terms_match_as_substrings():
    terms = desk.query_terms("劳动")
    assert terms == ["劳动"]
    assert desk.term_spans("平台劳动与组织", terms) == [[2, 4]]


# --- extracts ---------------------------------------------------------------

def test_extract_picks_the_sentence_with_most_terms():
    text = ("Platforms changed retail. Couriers used WhatsApp groups to organise log-offs "
            "and strikes across the city. Pay fell.")
    out = desk.query_biased_extract(text, desk.query_terms("courier strikes organise"))
    assert out["text"] == "Couriers used WhatsApp groups to organise log-offs and strikes across the city."
    assert [out["text"][a:b] for a, b in out["highlights"]] == ["Couriers", "organise", "strikes"]


def test_extract_marks_a_fragment_at_the_start_of_a_chunk():
    out = desk.query_biased_extract("of the riders who struck in Turin. Nothing else.", ["rider"])
    assert out["text"].startswith("…of the riders")


def test_extract_cuts_long_sentences_around_the_first_match():
    long = "word " * 80 + "the courier strike began " + "word " * 80
    out = desk.query_biased_extract(long, ["courier"], max_chars=100)
    assert len(out["text"]) <= 102 and "courier" in out["text"]
    assert out["text"].startswith("…") and out["text"].endswith("…")


def test_extract_without_matches_still_returns_text():
    out = desk.query_biased_extract("Nothing relevant here.", ["zebra"])
    assert out == {"text": "Nothing relevant here.", "highlights": []}


# --- bands, dedupe, ranking -------------------------------------------------

def test_bands_follow_the_cutoffs():
    assert [desk.band_for(s) for s in (5, 3, 1, 0, -2, -4, -9)] == [
        "strong", "strong", "good", "good", "weak", "weak", "see_also"]


def test_dedupe_drops_repeated_text_but_keeps_overlapping_neighbours():
    a = {"text": "one two three four five six seven eight nine ten"}
    dup = {"text": "one two three four five six seven eight nine ten eleven"}
    neighbour = {"text": "eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen"}
    assert desk.dedupe_passages([a, dup, neighbour]) == [a, neighbour]


def test_items_are_ranked_by_their_best_passage_not_first_appearance():
    docs = ["early weak passage about riders", "strong passage about riders", "another on riders"]
    metas = [meta("1", page=3), meta("2", page=9), meta("1", page=4, chunk_idx=1)]
    items = desk.build_bibliography(docs, metas, [-1.0, 6.0, 2.0], "riders")
    assert [it["item_id"] for it in items] == ["2", "1"]
    assert [it["rank"] for it in items] == [1, 2]
    first, second = items
    assert first["band"] == "strong" and second["band"] == "good"
    assert second["pages"] == [3, 4]
    assert [p["page"] for p in second["passages"]] == [4, 3]  # best first
    assert second["extract"]["page"] == 4
    assert second["tags"] == ["Labour", "Platforms"]


def test_unknown_page_and_year_become_none():
    items = desk.build_bibliography(["x"], [meta("1", page=0, year=0)], [1.0], "x")
    assert items[0]["year"] is None and items[0]["pages"] == []
    assert items[0]["passages"][0]["page"] is None


def test_items_without_an_id_group_by_title_year_and_path():
    m = {"title": "Same", "year": 2001, "pdf_path": "/s.pdf"}
    items = desk.build_bibliography(["a b c", "d e f"], [m, dict(m)], [1.0, 0.5], "q")
    assert len(items) == 1 and len(items[0]["passages"]) == 2


def test_max_items_caps_the_list():
    docs = [f"doc {i}" for i in range(5)]
    metas = [meta(str(i)) for i in range(5)]
    assert len(desk.build_bibliography(docs, metas, [1, 2, 3, 4, 5], "doc", max_items=3)) == 3


def test_the_same_paper_stored_twice_is_one_row():
    docs = ["adversarial passage one", "adversarial passage two", "other"]
    metas = [meta("1", title="Explaining and Harnessing Adversarial Examples", year=2015),
             meta("2", title="Explaining and harnessing adversarial examples.", year=2015),
             meta("3", title="Explaining and Harnessing Adversarial Examples", year=2014)]
    items = desk.build_bibliography(docs, metas, [5.0, 4.0, 1.0], "adversarial")
    assert [it["item_id"] for it in items] == ["1", "3"]  # a different year is a different item
    assert items[0]["duplicates"] == ["2"] and items[1]["duplicates"] == []
    assert [it["rank"] for it in items] == [1, 2]


def test_different_items_with_similar_titles_are_kept_apart():
    metas = [meta("1", title="Introduction", year=2020), dict(meta("2", title="Introduction", year=2020), authors="B"),
             meta("3", title="Title 1"), meta("4", title="Title 2")]
    items = desk.build_bibliography(["a", "b", "c", "d"], metas, [4.0, 3.0, 2.0, 1.0], "x")
    assert [it["item_id"] for it in items] == ["1", "2", "3", "4"]


def test_extracted_scope_keeps_only_set_values():
    assert desk.extracted_scope({"year_min": 2015, "year_max": None, "tags": [], "has_filters": True}) == {"year_min": 2015}
    assert desk.extracted_scope(None) == {}


# --- known items --------------------------------------------------------------

def test_detects_doi_isbn_and_arxiv():
    assert desk.detect_known_item("see doi:10.1177/0950017019862954.") == {"kind": "doi", "doi": "10.1177/0950017019862954"}
    assert desk.detect_known_item("ISBN 978-1-5095-3636-8") == {"kind": "isbn", "isbn": "9781509536368"}
    assert desk.detect_known_item("arXiv:2101.00001v2") == {"kind": "arxiv", "arxiv": "2101.00001"}


def test_invalid_isbn_checksum_is_not_a_known_item():
    hint = desk.detect_known_item("1234567890")
    assert hint is None or hint["kind"] != "isbn"


def test_detects_author_and_year():
    assert desk.detect_known_item("Woodcock 2020") == {"kind": "author_year", "authors": ["Woodcock"], "year": 2020}
    assert desk.detect_known_item("woodcock & graham (2020)") == {
        "kind": "author_year", "authors": ["woodcock", "graham"], "year": 2020}
    assert desk.detect_known_item("Tassinari and Maccarrone, 2020")["authors"] == ["Tassinari", "Maccarrone"]


def test_detects_quoted_and_plain_titles():
    assert desk.detect_known_item('find "Cruel optimism"') == {"kind": "title", "title": "Cruel optimism", "quoted": True}
    assert desk.detect_known_item("the gig economy a critical introduction")["kind"] == "title"


def test_single_word_and_empty_queries_are_not_known_items():
    assert desk.detect_known_item("platforms") is None
    assert desk.detect_known_item("   ") is None


def test_title_match_is_symmetric_overlap():
    title = "The gig economy: A critical introduction"
    assert desk.title_match_score("the gig economy a critical introduction", title) == 1.0
    assert desk.title_match_score("gig economy", title) == 0.5
    assert desk.title_match_score("cruel optimism", "Cruel Optimism") == 1.0
    assert desk.title_match_score("platform workers organise", title) == 0.0
    # Found on a real library: a topical query sharing three words with a generic title.
    topical = desk.title_match_score("adversarial examples against machine learning classifiers", "Adversarial machine learning")
    assert topical < desk.TITLE_MATCH_MIN


def test_topic_drops_the_phrases_read_as_scope():
    assert desk.topic_of("courier strikes since 2015") == "courier strikes"
    assert desk.topic_of('riders between 2010 and 2020 tagged "Labour" in "PhD"') == "riders"
    assert desk.topic_of("riders 2015-2020") == "riders"
    assert desk.topic_of("since 2015") == "since 2015"  # nothing left: keep the query
    assert desk.topic_of("from Turin to London") == "from Turin to London"


def test_a_passage_that_follows_another_drops_the_repeated_words():
    first = " ".join(f"w{i}" for i in range(100))
    second = " ".join(f"w{i}" for i in range(60, 100)) + " fresh words follow here"
    alone = " ".join(f"w{i}" for i in range(60, 100)) + " no predecessor kept"
    passages = [{"text": first, "chunk_idx": 3}, {"text": second, "chunk_idx": 4}, {"text": alone, "chunk_idx": 9}]
    desk.trim_overlaps(passages)
    assert passages[0]["text"] == first
    assert passages[1]["text"] == "…fresh words follow here"
    assert passages[2]["text"] == alone


def test_overlap_trimming_in_the_bibliography_keeps_highlights_aligned():
    # As the chunker writes them: about 130 words, the last 40 repeated at the start of the next.
    shared = " ".join(f"s{i}" for i in range(40))
    first = "Couriers organised. " + " ".join(f"a{i}" for i in range(90)) + " " + shared
    fresh = "couriers struck again " + " ".join(f"b{i}" for i in range(87))
    second = shared + " " + fresh
    items = desk.build_bibliography([first, second], [meta("1", chunk_idx=0), meta("1", chunk_idx=1)], [2.0, 1.0], "couriers")
    later = items[0]["passages"][1]
    assert later["text"] == "…" + fresh
    assert [later["text"][a:b] for a, b in later["highlights"]] == ["couriers"]
