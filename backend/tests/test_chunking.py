"""The PDF pipeline: layout-aware extraction (on a PDF built here) and section-aware chunking."""

import fitz
import pytest

from backend.chunking import CAP_CHARS, TARGET_CHARS, chunk_blocks, context_header, kind_of
from backend.pdf import PDF

BODY = ("The quick brown fox jumps over the lazy dog near the river bank while the sun sets slowly. "
        "This sentence is here so that the paragraph has more than one sentence in it. ")
REFS = ("[1] J. Smith and A. Jones. A study of things. In Proceedings of ACL, pages 1–10, 2019. "
        "[2] B. Lee, C. Kim, and D. Park. Another study. Journal of Studies, 12(3):45–67, 2020. "
        "[3] E. Brown. Yet another study. arXiv preprint arXiv:2001.00001, 2021. ")


def _block(text, page=1, heading=False):
    return {"page": page, "text": text, "heading": heading}


# ---- chunking ---------------------------------------------------------------------

def test_chunks_stay_within_sections_and_carry_their_label():
    blocks = [_block("1 Introduction", heading=True), _block(BODY * 3, 1), _block(BODY * 3, 2),
              _block("2 Method", heading=True), _block(BODY * 2, 2)]
    chunks = chunk_blocks(blocks)
    assert {c["section"] for c in chunks} == {"1 Introduction", "2 Method"}
    assert all(c["kind"] == "body" for c in chunks)
    assert chunks[0]["page"] == 1
    # The last Introduction chunk ends before the Method heading, whatever its size.
    intro = [c for c in chunks if c["section"] == "1 Introduction"]
    assert "Method" not in intro[-1]["text"]


def test_a_chunk_may_cross_a_page_break_and_reports_its_first_page():
    chunks = chunk_blocks([_block(BODY, 3), _block(BODY, 4)])
    assert len(chunks) == 1 and chunks[0]["page"] == 3


def test_long_runs_without_sentence_breaks_are_capped():
    table = "cell " * 2000  # 10,000 characters, no full stop
    chunks = chunk_blocks([_block(table)])
    assert all(len(c["text"]) <= CAP_CHARS for c in chunks)
    assert sum(len(c["text"]) for c in chunks) >= 9500


def test_chunks_are_near_the_target_size_and_do_not_overlap():
    chunks = chunk_blocks([_block(BODY * 20)])
    assert all(len(c["text"]) <= TARGET_CHARS for c in chunks)
    assert " ".join(c["text"] for c in chunks) == (BODY * 20).strip()


def test_a_short_tail_joins_the_previous_chunk_of_its_section():
    chunks = chunk_blocks([_block(BODY * 5), _block("A last short line.")])
    assert chunks[-1]["text"].endswith("A last short line.")
    assert all(len(c["text"]) >= 150 for c in chunks)


def test_reference_lists_are_labelled_by_heading_and_by_content():
    humanities = ("Smith, J. (2010) On Things. London: Routledge. Jones, A. and Lee, B. (2012) ‘More things’, "
                  "Journal of Things, 4(2), pp. 10–20. Brown, C. (2015) Thingness. Oxford: Oxford University Press. ")
    by_heading = chunk_blocks([_block("References", heading=True), _block(humanities)])
    assert by_heading[0]["kind"] == "references"
    by_content = chunk_blocks([_block("Related work", heading=True), _block(REFS * 2)])
    assert by_content[0]["kind"] == "references"
    # Plain prose after the list, with no heading of its own, is kept.
    appendix = chunk_blocks([_block("References", heading=True), _block(REFS * 4), _block(BODY * 4)])
    assert [c["kind"] for c in appendix] == ["references", "body"]


def test_number_garble_is_labelled():
    assert kind_of("0.12 0.34 0.56 0.78 0.90 1.23 4.56 7.89 0.11 0.22", "") == "garble"
    assert kind_of(BODY, "") == "body"


def test_title_author_and_banner_headings_give_no_section_label():
    chunks = chunk_blocks([_block("Fine-Grained Analysis of Propaganda", heading=True), _block(BODY),
                           _block("Giovanni Da San Martino1, Seunghak Yu2, Alberto Barrón-Cedeño3, Preslav Nakov1", heading=True),
                           _block(BODY), _block("http://tcs.sagepub.com/ Theory, Culture & Society", heading=True), _block(BODY)],
                          title="Fine-Grained Analysis of Propaganda in News Articles")
    assert [c["section"] for c in chunks] == ["", "", ""]


def test_context_header_names_work_authors_year_and_section():
    assert context_header("A Title", "Smith,Jones", 2020, "3 Results") == "A Title — Smith et al., 2020 — 3 Results\n"
    assert context_header("A Title", "Smith", 0) == "A Title — Smith\n"
    assert context_header("", "", None) == "\n"


# ---- extraction -----------------------------------------------------------------

@pytest.fixture
def paper(tmp_path):
    """Three pages: running header and page numbers, a large title, bold headings,
    a hyphenated line break, a ligature, an arXiv-style rotated stamp and a references section."""
    doc = fitz.open()
    for n in range(1, 4):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 30), "JOURNAL OF TESTING", fontsize=8)
        page.insert_text((290, 820), str(n), fontsize=9)
        y = 80
        if n == 1:
            page.insert_text((72, y), "A Paper About Testing", fontsize=16, fontname="helv"); y += 30
            page.insert_text((72, y), "Abstract", fontsize=11, fontname="hebo"); y += 20
            page.insert_text((72, y), "We study classification of inter-", fontsize=10); y += 14
            page.insert_text((72, y), "pretability methods in depth.", fontsize=10); y += 20
            page.insert_text((72, y), "1 Introduction", fontsize=11, fontname="hebo"); y += 20
            page.insert_text((72, y), "Body text of the introduction goes here.", fontsize=10)
            page.insert_text((20, 700), "arXiv:1234.5678v1 [cs.CL] 1 Jan 2020", fontsize=12, rotate=90)
        elif n == 2:
            page.insert_text((72, y), "Second page body text continues the argument.", fontsize=10)
        else:
            page.insert_text((72, y), "References", fontsize=11, fontname="hebo"); y += 20
            page.insert_text((72, y), "[1] J. Smith. A study. In Proc. ACL, pages 1-10, 2019.", fontsize=10)
    path = tmp_path / "paper.pdf"
    doc.save(str(path))
    return str(path)


def test_extract_blocks_cleans_and_marks_structure(paper):
    blocks = PDF(paper).extract_blocks()
    texts = [b["text"] for b in blocks]
    joined = " ".join(texts)
    assert "JOURNAL OF TESTING" not in joined and "arXiv:" not in joined
    assert not any(t in {"1", "2", "3"} for t in texts), "page numbers are dropped"
    assert "classification of interpretability" in joined, "line-break hyphen joined"
    headings = [b["text"] for b in blocks if b["heading"]]
    assert headings == ["A Paper About Testing", "Abstract", "1 Introduction", "References"]
    assert [b["page"] for b in blocks if b["text"].startswith("Second page")] == [2]
    body = [b for b in blocks if not b["heading"]]
    assert all("Body text" not in b["text"] or b["page"] == 1 for b in body)
