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
    """
    Handles PDF file operations for Zotero library items, including text extraction, metadata access, and page/annotation utilities.

    This class can be instantiated with either a ZoteroItem object or a direct file path. All standard PDF operations (extracting full or chunked text, reading metadata, counting pages, and fetching annotations) are available. When a ZoteroItem is provided, richer metadata and integration with the library are supported.

    Attributes:
        filepath (str): Path to the PDF file on disk.
        metadata (dict): Optional metadata from Zotero or PDF.
        zitem (ZoteroItem, optional): If provided, the ZoteroItem associated with this file.

    Methods:
        open(): Opens the PDF file for further operations.
        extract_text(max_chars=2000): Extracts up to `max_chars` of the PDF's text content.
        num_pages(): Returns the number of pages in the PDF.
        extract_text_by_page(page_number): Extracts text from the specified page.
        get_metadata(): Returns metadata from the ZoteroItem (preferred) or directly from the PDF file.
        extract_all_text(): Extracts and returns text of all pages in the PDF as a list of strings.
        get_annotations(): Returns a list of annotations present in the PDF.

    Typical usage:
        pdf = PDF(zotero_item)
        text = pdf.extract_text()
        meta = pdf.get_metadata()
    """

    def __init__(self, zotero_item_or_path):
        if hasattr(zotero_item_or_path, "filepath"):
            self.filepath = zotero_item_or_path.filepath
            self.metadata = getattr(zotero_item_or_path, "metadata", {})
            self.zitem = zotero_item_or_path
        else:
            self.filepath = zotero_item_or_path
            self.metadata = {}
            self.zitem = None
        self.doc = None

    def open(self):
        self.doc = fitz.open(self.filepath)

    def extract_text(self, max_chars=2000):
        self.doc = fitz.open(self.filepath)
        text = ""
        for page in self.doc:
            text += page.get_text()
            if len(text) >= max_chars:
                break
        self.doc.close()
        return text[:max_chars]
    
    def num_pages(self):
        self.doc = fitz.open(self.filepath)
        count = len(self.doc)
        self.doc.close()
        return count

    def extract_text_by_page(self, page_number):
        self.doc = fitz.open(self.filepath)
        text = self.doc[page_number].get_text()
        self.doc.close()
        return text
    
    def get_metadata(self):
        if self.zitem and self.zitem.metadata:
            return self.zitem.metadata
        self.doc = fitz.open(self.filepath)
        metadata = self.doc.metadata
        self.doc.close()
        return metadata  # return a dict
    
    def extract_all_text(self):
        """Retrieves all the text of the PDF by page. stored by page too."""
        self.doc = fitz.open(self.filepath)
        text_chunks = [page.get_text() for page in self.doc]
        self.doc.close()
        return text_chunks  # list of strings, one per page
    
    def extract_text_with_pages(self):
        """Extract text from PDF with page numbers preserved.
        
        Returns:
            List of dicts with 'page_num' and 'text' keys
        """
        self.doc = fitz.open(self.filepath)
        pages_data = []
        for i, page in enumerate(self.doc):
            text = page.get_text()
            if text.strip():  # Only include pages with text
                pages_data.append({
                    'page_num': i + 1,  # 1-indexed page numbers
                    'text': text
                })
        self.doc.close()
        return pages_data
    
    def extract_blocks(self):
        """Paragraph blocks in reading order: [{"page", "text", "heading"}].

        Reads each page's layout once. Lines are normalised (NFKC, soft hyphens
        dropped); rotated text (arXiv stamps), boilerplate lines, page numbers and
        lines repeated in the page margins across the document (running headers
        and footers) are left out. Headings are told by font size and weight.
        """
        doc = fitz.open(self.filepath)
        pages = []  # (page_num, height, [[(text, size, bold, bbox), ...] per block])
        sizes = collections.Counter()
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
        doc.close()
        if not sizes:
            return []
        body_size = sizes.most_common(1)[0][0]

        def in_margin(bbox, height):
            return bbox[1] < _MARGIN * height or bbox[3] > (1 - _MARGIN) * height

        def key(text):
            return re.sub(r"\d+", "#", " ".join(text.split()))

        # A line that recurs on many pages is a running header or footer: any line in
        # the margins, or a short one wherever it sits (some journals set them lower).
        seen = collections.Counter()
        for _, height, blocks in pages:
            seen.update({key(t) for lines in blocks for t, _, _, bb in lines if len(t) <= 60 or in_margin(bb, height)})
        repeated = {k for k, n in seen.items() if n >= max(3, 0.3 * len(pages))}

        out = []
        for page_num, height, blocks in pages:
            for lines in blocks:
                kept = [ln for ln in lines
                        if key(ln[0]) not in repeated and not (in_margin(ln[3], height) and ln[0].isdigit())]
                if not kept:
                    continue
                out.append({"page": page_num, "text": " ".join(t for t, _, _, _ in kept),
                            "heading": _is_heading(kept, body_size)})
        return out

    def get_annotations(self):
        self.doc = fitz.open(self.filepath)
        annots = []
        for page in self.doc:
            for annot in page.annots():
                annots.append(annot.info)
        self.doc.close()
        return annots  # list of annotation dicts

    def extract_text_for_items(items):
        enriched_items = []
        for zitem in items:
            if hasattr(zitem, "filepath"):  # Ensure it's a ZoteroItem
                pdf = PDF(zitem)
                text = pdf.extract_text()
                if text:
                    zitem.metadata['text'] = text
                    enriched_items.append(zitem)
        return enriched_items

    








