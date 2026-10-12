"""Turn a PDF's text blocks into passages worth indexing.

Blocks come from PDF.extract_blocks(): paragraphs in reading order, each with
its page, with headings marked. Chunks are packed from whole sentences within a
section, so they never mix two sections and may cross a page break. There is no
overlap; the desk shows neighbouring passages instead. Reference lists and
number-only garble are labelled so indexing can leave them out.
"""

import re
from typing import Any, Dict, List

TARGET_CHARS = 1100   # about 250 tokens: room for the context header within the embedder's window
CAP_CHARS = 1600      # a single run of text with no sentence breaks (tables, lists) is cut here
MIN_CHARS = 150       # a tail shorter than this joins the previous chunk of its section

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(\[])")
_REFERENCES_SECTION = re.compile(
    r"^(?:\d+\.?\s*|[ivx]+\.?\s*)?(?:references?|bibliography|works cited|literature cited|reference list|notes and references)\b", re.I)

# Reference-list text: citation structure (numbered entries, "Surname, I." runs,
# trailing years) and venue markers, with little running prose.
_ENTRY = re.compile(r"\[\d{1,4}\]\s+(?:[A-Z][\w'’`-]+|[A-Z]\.)|\b[A-Z][\w'’`-]+,\s(?:[A-Z]\.\s?){1,3}(?:,|&|\(|and\b)"
                    r"|(?<![\w(])(?:19|20)\d{2}[a-z]?\)?\.(?=\s|$)")
_VENUE = re.compile(r"\bdoi\b|https?://|arXiv|\bIn Proceedings\b|\bProc\.|\bpp\.|\bpages \d|\b[Vv]ol\.|\bPress\b"
                    r"|\b\d+\s?\(\d+\)|\b\d+\s?[–-]\s?\d+\b")
_PROSE = re.compile(r"\b(?:is|are|was|were|that|which|we|this|these|be|been|it|its|can|has|have|not|our|they|their"
                    r"|also|however|thus|such|than|would|could|may|should|there|when|while|because|but)\b", re.I)
_WORD = re.compile(r"[A-Za-z]{2,}")


def citation_density(text: str) -> tuple:
    """(citation markers, prose function words) per 100 words."""
    words = max(len(_WORD.findall(text)), 1)
    cites = (len(_ENTRY.findall(text)) + len(_VENUE.findall(text))) * 100 / words
    return cites, len(_PROSE.findall(text)) * 100 / words


def looks_like_references(text: str) -> bool:
    cites, prose = citation_density(text)
    return cites >= 6 and prose < 6


def kind_of(text: str, section: str) -> str:
    """'body', 'references' or 'garble'. A references heading decides unless the
    text is plainly prose (appendices that follow the list without a heading of their own)."""
    cites, prose = citation_density(text)
    if cites >= 6 and prose < 6:
        return "references"
    if _REFERENCES_SECTION.match(section) and not (prose >= 8 and cites < 3):
        return "references"
    if sum(c.isalpha() for c in text) < 0.4 * len(text):
        return "garble"
    return "body"


def context_header(title: str, authors: str, year: Any, section: str = "") -> str:
    """The line prepended to a passage before embedding or reranking, so the
    vector knows which work and section it came from. Never shown to the reader."""
    first = (authors or "").split(",")[0].strip()
    who = f"{first} et al." if "," in (authors or "") else first
    parts = [title or "", ", ".join(p for p in (who, str(year) if year and int(year) > 0 else "") if p)]
    if section:
        parts.append(section)
    return " — ".join(p for p in parts if p) + "\n"


def _label_for(heading: str, title: str) -> str:
    """The section label a heading gives its chunks: none for the work's own title,
    author lines, banners and the like, which font size alone cannot tell from headings."""
    a, b = (re.sub(r"[^a-z0-9]", "", s.lower()) for s in (heading, title))
    if len(a) >= 10 and len(b) >= 10 and (a in b or b in a):
        return ""
    if len(heading) > 70 or heading.count(",") >= 3 or re.search(r"https?:|@|\bdoi\b|\d{4}", heading):
        return ""
    return heading


def _hard_split(sentence: str) -> List[str]:
    pieces = []
    while len(sentence) > CAP_CHARS:
        cut = sentence.rfind(" ", 0, CAP_CHARS)
        cut = cut if cut > CAP_CHARS // 2 else CAP_CHARS
        pieces.append(sentence[:cut])
        sentence = sentence[cut:].lstrip()
    pieces.append(sentence)
    return pieces


def chunk_blocks(blocks: List[Dict[str, Any]], title: str = "") -> List[Dict[str, Any]]:
    """Pack blocks into chunks: {text, page, section, kind}. `page` is where the chunk starts."""
    chunks: List[Dict[str, Any]] = []
    section = ""
    buf: List[str] = []
    buf_len = 0
    buf_page = 0

    def flush():
        nonlocal buf, buf_len
        text = " ".join(buf).strip()
        buf, buf_len = [], 0
        if not text:
            return
        if len(text) < MIN_CHARS and chunks and chunks[-1]["section"] == section:
            chunks[-1]["text"] += " " + text
            return
        chunks.append({"text": text, "page": buf_page, "section": section, "kind": kind_of(text, section)})

    for block in blocks:
        if block.get("heading"):
            flush()
            section = _label_for(block["text"], title)
            if _REFERENCES_SECTION.match(block["text"]):
                section = block["text"]
            continue
        for sentence in _SENTENCE.split(block["text"]):
            for piece in _hard_split(sentence.strip()):
                if not piece:
                    continue
                if buf and buf_len + 1 + len(piece) > TARGET_CHARS:
                    flush()
                if not buf:
                    buf_page = block["page"]
                buf.append(piece)
                buf_len += len(piece) + 1
    flush()
    return chunks
