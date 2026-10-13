#pdf.py
import collections
import re
import unicodedata

import fitz

# Join hyphenated line breaks and expand ligatures (ﬁ → fi) while reading.
_FLAGS = fitz.TEXT_DEHYPHENATE | (fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_LIGATURES)
_MARGIN = 0.1  # share of the page height, top and bottom, where running headers and footers live
_BOILERPLATE = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$|Downloaded from|This content downloaded|All rights reserved"
                          r"|©|Copyright \d|For personal use only", re.I)
_SECTION_WORDS = {
    "abstract", "introduction", "background", "related work", "methods", "method", "methodology",
    "materials and methods", "results", "discussion", "conclusion", "conclusions", "references", "bibliography",
    "acknowledgments", "acknowledgements", "appendix", "notes", "summary", "limitations", "experiments",
    "evaluation", "works cited", "literature cited",
}
_NUMBERED = re.compile(r"^(?:\d+|[IVX]+|[A-Z])(?:\.\d+)*\.?\s+\S")


def _is_bold(span) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower() or "CMBX" in span["font"]


def _is_heading(lines, body_size) -> bool:
    """A short block set apart by size, or bold and shaped like a section title."""
    text = " ".join(t for t, _, _, _ in lines)
    if len(lines) > 3 or len(text) > 120 or not re.search(r"[A-Za-z]{3}", text):
        return False
    size = max(s for _, s, _, _ in lines)
    if size >= body_size + 1:
        return True
    bold = all(b for _, _, b, _ in lines)
    titled = _NUMBERED.match(text) or re.sub(r"^\d+(\.\d+)*\.?\s*", "", text).lower().rstrip(".:") in _SECTION_WORDS
    return bold and size >= body_size - 0.5 and bool(titled) and not text.endswith((".", ":", ","))


class PDF:
    """Text extraction for one PDF: a sample for the API, or paragraph blocks for indexing."""

    def __init__(self, zotero_item_or_path):
        self.filepath = getattr(zotero_item_or_path, "filepath", zotero_item_or_path)

    def extract_text(self, max_chars=2000):
        with fitz.open(self.filepath) as doc:
            text = ""
            for page in doc:
                text += page.get_text()
                if len(text) >= max_chars:
                    break
        return text[:max_chars]

    def extract_blocks(self):
        """Paragraph blocks in reading order: [{"page", "text", "heading"}].

        Reads each page's layout once. Lines are normalised (NFKC, soft hyphens
        dropped); rotated text (arXiv stamps), boilerplate lines, page numbers and
        lines repeated in the page margins across the document (running headers
        and footers) are left out. Headings are told by font size and weight.
        """
        pages = []  # (page_num, height, [[(text, size, bold, bbox), ...] per block])
        sizes = collections.Counter()
        with fitz.open(self.filepath) as doc:
            for i, page in enumerate(doc):
                blocks = []
                for b in page.get_text("dict", flags=_FLAGS)["blocks"]:
                    lines = []
                    for l in b.get("lines", []):
                        if abs(l["dir"][0]) < 0.9:
                            continue
                        spans = [s for s in l["spans"] if s["text"].strip()]
                        text = unicodedata.normalize("NFKC", "".join(s["text"] for s in spans)).replace("­", "").strip()
                        if not text or _BOILERPLATE.search(text):
                            continue
                        size = max(s["size"] for s in spans)
                        sizes[round(size, 1)] += len(text)
                        lines.append((text, size, all(_is_bold(s) for s in spans), l["bbox"]))
                    if lines:
                        blocks.append(lines)
                pages.append((i + 1, page.rect.height, blocks))
        if not sizes:
            return []
        body_size = sizes.most_common(1)[0][0]

        def in_margin(bbox, height):
            return bbox[1] < _MARGIN * height or bbox[3] > (1 - _MARGIN) * height

        def key(text):
            return re.sub(r"\d+", "#", " ".join(text.split()))

        # A line that recurs on many pages is a running header or footer when it sits in
        # the margins or, if short, in the page's first or last block (some journals set
        # them lower). "Proof." or "where" between equations mid-page is left alone.
        def running(i, n, text, bbox, height):
            return in_margin(bbox, height) or (len(text) <= 60 and i in (0, n - 1))

        seen = collections.Counter()
        for _, height, blocks in pages:
            seen.update({key(t) for i, lines in enumerate(blocks) for t, _, _, bb in lines
                         if running(i, len(blocks), t, bb, height)})
        repeated = {k for k, n in seen.items() if n >= max(3, 0.3 * len(pages))}

        out = []
        for page_num, height, blocks in pages:
            for i, lines in enumerate(blocks):
                kept = [ln for ln in lines
                        if not (running(i, len(blocks), ln[0], ln[3], height) and (key(ln[0]) in repeated or ln[0].isdigit()))]
                if not kept:
                    continue
                out.append({"page": page_num, "text": " ".join(t for t, _, _, _ in kept),
                            "heading": _is_heading(kept, body_size)})
        return out
