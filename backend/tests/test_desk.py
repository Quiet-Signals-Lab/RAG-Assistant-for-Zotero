"""Ranking rules of the reference desk (backend/desk.py)."""

from backend import desk


def meta(item_id, page=1, title="T", year=2020, chunk_idx=0):
    return {"item_id": item_id, "page": page, "title": title, "year": year, "chunk_idx": chunk_idx,
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
