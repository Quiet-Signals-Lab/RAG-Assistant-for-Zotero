"""Reference desk: turn reranked passages into a ranked bibliography.

Pure functions with no I/O, so the ranking rules live in one place and can be
tested and tuned. The reasoning behind each rule is in docs/REFERENCE_DESK_PLAN.md.
"""

import math
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence

# Bands replace numbers in the UI: the reranker's score is system relevance, not
# the reader's judgement, and a percentage invites false precision.
# shortcut: fixed cut-offs on the raw cross-encoder logit (ms-marco-MiniLM-L-6-v2
# has no output activation); replace with per-reranker calibration fitted on the
# test collection (roadmap Stage 4).
BAND_CUTOFFS = ((3.0, "strong"), (0.0, "good"), (-4.0, "weak"))
SEE_ALSO = "see_also"

# Bonus for items with several good passages. Off: MaxP alone is the
# evidence-backed default, and the bonus waits for a paired win on the test collection.
COVERAGE_BONUS = 0.0

# A passage whose words are mostly inside an already-kept passage of the same
# item is the same text indexed twice, not extra evidence.
DUPLICATE_CONTAINMENT = 0.6

MAX_PASSAGES_PER_ITEM = 6
EXTRACT_MAX_CHARS = 240

# A title counts as the item the reader means when this share of words overlaps
# in both directions (query in title and title in query). 0.6 pinned generic
# titles such as "Adversarial machine learning" for topical queries on a real
# library; quoted titles use a lower bar because the reader marked them as titles.
TITLE_MATCH_MIN = 0.8

_STOPWORDS = frozenset(
    """a about after again against all also am an and any are as at be because been
    before being between both but by can could did do does doing during each few for
    from further had has have having how i if in into is it its itself just me more
    most my no nor not of off on once only or other our out over own same she should
    so some such than that the their them then there these they this those through
    to too under until up very was we were what when where which while who whom why
    will with would you your since among within via per paper papers article articles
    library find show""".split()
)

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")
_SUFFIXES = ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?。！？])\s+")


# --------------------------------------------------------------------------- #
# Terms and highlighting                                                       #
# --------------------------------------------------------------------------- #

def stem(word: str) -> str:
    """Strip one common English suffix. Light on purpose: matching also allows prefixes."""
    w = word.lower()
    for suffix in _SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def _same_term(a: str, b: str) -> bool:
    if a == b:
        return True
    return min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))


def query_terms(query: str) -> List[str]:
    """Content terms of a query, stemmed. CJK runs are kept whole and matched as substrings."""
    terms: List[str] = []
    for token in _WORD.findall(query or ""):
        if _CJK.search(token):
            term = token
        else:
            low = token.lower()
            if len(low) < 3 or low in _STOPWORDS or low.isdigit():
                continue
            term = stem(low)
        if term not in terms:
            terms.append(term)
    return terms


def term_spans(text: str, terms: Sequence[str]) -> List[List[int]]:
    """Character spans [start, end) in `text` of words that match a query term."""
    if not text or not terms:
        return []
    latin = [t for t in terms if not _CJK.search(t)]
    cjk = [t for t in terms if _CJK.search(t)]
    spans: List[List[int]] = []
    if latin:
        for m in _WORD.finditer(text):
            token = m.group(0)
            if not _CJK.search(token) and any(_same_term(stem(token), t) for t in latin):
                spans.append([m.start(), m.end()])
    for term in cjk:
        start = text.find(term)
        while start != -1:
            spans.append([start, start + len(term)])
            start = text.find(term, start + len(term))
    spans.sort()
    return spans


def _terms_matched(text: str, terms: Sequence[str]) -> int:
    found = set()
    for start, end in term_spans(text, terms):
        word = text[start:end]
        found.add(next((t for t in terms if t == word or _same_term(stem(word), t)), word))
    return len(found)


# --------------------------------------------------------------------------- #
# Extracts                                                                     #
# --------------------------------------------------------------------------- #

def query_biased_extract(text: str, terms: Sequence[str], max_chars: int = EXTRACT_MAX_CHARS) -> Dict[str, Any]:
    """The sentence of `text` that matches the most query terms (Tombros & Sanderson 1998).

    Faithful by construction: every character comes from the passage. Long
    sentences are cut to a window around the first match, marked with an ellipsis.
    """
    clean = " ".join((text or "").split())
    sentences = [s for s in _SENTENCE_BREAK.split(clean) if s.strip()] or [clean]
    best = max(range(len(sentences)), key=lambda i: (_terms_matched(sentences[i], terms), -i))
    sentence = sentences[best]

    lead = "…" if best == 0 and sentence[:1].islower() else ""
    tail = "…" if best == len(sentences) - 1 and sentence[-1:] not in ".!?。！？" else ""

    if len(sentence) > max_chars:
        spans = term_spans(sentence, terms)
        anchor = spans[0][0] if spans else 0
        start = max(0, anchor - max_chars // 3)
        if start > 0:
            space = sentence.find(" ", start)
            start = space + 1 if 0 <= space < anchor else start
        end = min(len(sentence), start + max_chars)
        if end < len(sentence):
            space = sentence.rfind(" ", start, end)
            end = space if space > start else end
        lead = "…" if start > 0 else lead
        tail = "…" if end < len(sentence) else tail
        sentence = sentence[start:end]

    sentence = lead + sentence.strip() + tail
    return {"text": sentence, "highlights": term_spans(sentence, terms)}


# --------------------------------------------------------------------------- #
# Ranking                                                                      #
# --------------------------------------------------------------------------- #

def band_for(score: float) -> str:
    for cutoff, band in BAND_CUTOFFS:
        if score >= cutoff:
            return band
    return SEE_ALSO


def _token_set(text: str) -> set:
    return {w.lower() for w in _WORD.findall(text or "")}


def dedupe_passages(passages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop passages that repeat one already kept. Expects passages sorted best first."""
    kept: List[Dict[str, Any]] = []
    kept_tokens: List[set] = []
    for passage in passages:
        tokens = _token_set(passage["text"])
        if tokens and any(len(tokens & k) / len(tokens) >= DUPLICATE_CONTAINMENT for k in kept_tokens):
            continue
        kept.append(passage)
        kept_tokens.append(tokens)
    return kept


def _strip_shared_prefix(before: str, text: str, min_words: int = 8) -> str:
    """Drop the words `text` repeats from the end of `before`.

    Chunks overlap by about 40 words, so a passage that follows another one in
    the same item would otherwise show that text twice.
    """
    a, b = before.split(), text.split()
    for k in range(min(len(a), len(b) - 1, 80), min_words - 1, -1):
        if a[-k:] == b[:k]:
            return "…" + " ".join(b[k:])
    return text


def trim_overlaps(passages: List[Dict[str, Any]]) -> None:
    """Trim each passage that directly follows another kept passage of the same item."""
    by_idx = {p["chunk_idx"]: p["text"] for p in passages if isinstance(p.get("chunk_idx"), int)}
    for p in passages:
        idx = p.get("chunk_idx")
        if isinstance(idx, int) and idx - 1 in by_idx:
            p["text"] = _strip_shared_prefix(by_idx[idx - 1], p["text"])


def _item_key(meta: Dict[str, Any]) -> str:
    item_id = str(meta.get("item_id") or "").strip()
    if item_id and item_id != "None":
        return item_id
    return "|".join(str(meta.get(k) or "") for k in ("title", "year", "pdf_path"))


def _positive_int(value: Any) -> Optional[int]:
    """Page and year are stored as ints with 0 meaning unknown."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _split_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in re.split(r"[|,]", str(value or "")) if v.strip()]


def build_bibliography(
    docs: Sequence[str],
    metas: Sequence[Dict[str, Any]],
    scores: Sequence[float],
    query: str,
    max_items: int = 30,
) -> List[Dict[str, Any]]:
    """Group reranked passages by item and rank items by their best passage (MaxP).

    `docs`, `metas` and `scores` are parallel lists from the reranker. Items keep
    up to MAX_PASSAGES_PER_ITEM passages after duplicates are dropped, each with a
    band and highlight spans, plus a query-biased extract from the best passage.
    """
    terms = query_terms(query)
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for doc, meta, score in zip(docs, metas, scores):
        meta = meta or {}
        group = groups.setdefault(_item_key(meta), {"meta": meta, "passages": []})
        group["passages"].append({
            "text": doc or "",
            "page": _positive_int(meta.get("page")),
            "score": float(score),
            "chunk_idx": meta.get("chunk_idx"),
        })

    items: List[Dict[str, Any]] = []
    for key, group in groups.items():
        ordered = sorted(group["passages"], key=lambda p: p["score"], reverse=True)
        passages = dedupe_passages(ordered)[:MAX_PASSAGES_PER_ITEM]
        trim_overlaps(passages)
        best = passages[0]
        good = sum(1 for p in passages if p["score"] >= BAND_CUTOFFS[1][0])
        score = best["score"] + COVERAGE_BONUS * math.log1p(good)
        for p in passages:
            p["band"] = band_for(p["score"])
            p["highlights"] = term_spans(p["text"], terms)
            p["score"] = round(p["score"], 4)
        extract = query_biased_extract(best["text"], terms)
        extract["page"] = best["page"]
        pages = sorted({p["page"] for p in passages if p["page"]})
        meta = group["meta"]
        items.append({
            "item_id": key,
            "score": round(score, 4),
            "band": band_for(best["score"]),
            "title": meta.get("title") or "Untitled",
            "authors": meta.get("authors") or "",
            "year": _positive_int(meta.get("year")),
            "item_type": meta.get("item_type") or "",
            "tags": _split_list(meta.get("tags")),
            "collections": _split_list(meta.get("collections")),
            "pdf_path": meta.get("pdf_path") or "",
            "pages": pages,
            "extract": extract,
            "passages": passages,
        })

    items.sort(key=lambda it: it["score"], reverse=True)
    items = _fold_duplicates(items)[:max_items]
    for rank, item in enumerate(items, 1):
        item["rank"] = rank
    return items


def _fold_duplicates(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Show an item stored twice in Zotero as one row.

    Same title (case and punctuation aside), same year and same authors, so two
    different chapters called "Introduction" stay apart. Expects items sorted
    best first; the best copy stays and lists the others.
    """
    kept: List[Dict[str, Any]] = []
    seen: Dict[Any, Dict[str, Any]] = {}
    for item in items:
        title = " ".join(_WORD.findall(item["title"].lower()))
        authors = frozenset(a.strip().lower() for a in re.split(r"[,;]", item["authors"]) if a.strip())
        key = (title, item["year"], authors) if title else None
        if key is not None and key in seen:
            seen[key]["duplicates"].append(item["item_id"])
            continue
        item["duplicates"] = []
        if key is not None:
            seen[key] = item
        kept.append(item)
    return kept


# The phrases backend/metadata_extractor.py reads as scope. Keep the two in step.
_SCOPE_PHRASES = re.compile(
    r"\b(?:from|between)\s+\d{4}\s+(?:to|and)\s+\d{4}\b"
    r"|\b\d{4}\s*[-\u2013]\s*\d{4}\b"
    r"|\b(?:after|since|from|before|until)\s+\d{4}\b"
    r"|\btagged\s+\"[^\"]+\""
    r"|\bin\s+\"[^\"]+\"",
    re.I,
)


def topic_of(query: str) -> str:
    """The query without the phrases read as scope ("since 2015", 'in "PhD"').

    Scope is applied as a filter; left in the text it also skews retrieval and
    the reranker (on a real library "since 2010" took the best score from 5.3 to -4.2).
    """
    topic = " ".join(_SCOPE_PHRASES.sub(" ", query or "").split())
    return topic or (query or "").strip()


def excluded(text: str, terms: Sequence[str]) -> bool:
    """True when `text` mentions any excluded term: every content word of the term, by stem."""
    if not terms:
        return False
    words = {stem(w) for w in _WORD.findall((text or "").lower())}
    for term in terms:
        stems = {stem(w) for w in title_words(term)}
        if stems and stems <= words:
            return True
    return False


def extracted_scope(extracted: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The parts of an extracted filter worth showing as chips, without empty keys."""
    if not extracted:
        return {}
    keys = ("year_min", "year_max", "tags", "collections", "author", "title", "item_types", "exclude")
    return {k: extracted[k] for k in keys if extracted.get(k)}


# --------------------------------------------------------------------------- #
# Known-item detection (Cutter's first object: find the item you already know) #
# --------------------------------------------------------------------------- #

_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
_ARXIV = re.compile(r"(?:\barxiv:\s*|\b)(\d{4}\.\d{4,5})(?:v\d+)?\b", re.I)
_ISBN = re.compile(r"\b((?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx])\b")
_QUOTED = re.compile(r"[\"“”]([^\"“”]{4,})[\"“”]")
_YEAR = re.compile(r"^\(?(1[5-9]\d{2}|20\d{2})[a-z]?\)?[.,]?$")
_NAME = re.compile(r"^[^\W\d_][\w'’\-]*$", re.UNICODE)
_JOINERS = {"and", "&", "et", "al", "al.", "et al.", ","}


def _valid_isbn(raw: str) -> Optional[str]:
    digits = re.sub(r"[-\s]", "", raw).upper()
    if len(digits) == 10 and digits[:9].isdigit() and (digits[9].isdigit() or digits[9] == "X"):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
        return digits if total % 11 == 0 else None
    if len(digits) == 13 and digits.isdigit():
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits))
        return digits if total % 10 == 0 else None
    return None


def title_words(text: str) -> set:
    """Stemmed content words of a title or title-like query."""
    return {stem(w) for w in _WORD.findall(text or "") if w.lower() not in _STOPWORDS and len(w) > 1}


def title_match_score(query: str, title: str) -> float:
    """Word overlap in both directions; 1.0 when query and title name the same words."""
    q, t = title_words(query), title_words(title)
    if not q or not t:
        return 0.0
    shared = len(q & t)
    return min(shared / len(q), shared / len(t))


def detect_known_item(query: str) -> Optional[Dict[str, Any]]:
    """Recognise a query that names one item. Deterministic and high precision.

    Returns a hint for the metadata lookup, or None for a subject query. The
    lookup decides whether anything in the library actually matches, so a hint
    that matches nothing costs one cheap query and shows nothing.
    """
    q = (query or "").strip()
    if not q:
        return None

    m = _DOI.search(q)
    if m:
        return {"kind": "doi", "doi": m.group(1).rstrip(".,;)").lower()}
    m = _ARXIV.search(q)
    if m and ("arxiv" in q.lower() or q.replace(m.group(0), "").strip() == ""):
        return {"kind": "arxiv", "arxiv": m.group(1)}
    for m in _ISBN.finditer(q):
        isbn = _valid_isbn(m.group(1))
        if isbn:
            return {"kind": "isbn", "isbn": isbn}
    m = _QUOTED.search(q)
    if m and len(title_words(m.group(1))) >= 1:
        return {"kind": "title", "title": m.group(1).strip(), "quoted": True}

    tokens = q.replace(",", " , ").split()
    years = [t for t in tokens if _YEAR.match(t)]
    if len(years) == 1 and len(tokens) <= 7:
        names = [t for t in tokens if not _YEAR.match(t) and t.lower() not in _JOINERS]
        if 1 <= len(names) <= 3 and all(_NAME.match(n) for n in names):
            year = int(re.sub(r"\D", "", years[0])[:4])
            return {"kind": "author_year", "authors": names, "year": year}

    if len(title_words(q)) >= 2 and len(q.split()) <= 25:
        return {"kind": "title", "title": q, "quoted": False}
    return None


def _title_key(title: str) -> str:
    return " ".join(re.findall(r"\w+", (title or "").lower()))


def mark_owned(entries: List[Dict[str, Any]], dois: Dict[str, str], titles: Dict[str, str]) -> List[Dict[str, Any]]:
    """Mark the works a reader already has in Zotero, by DOI, else by exact title (case and
    punctuation aside). Owned works come first; otherwise the source's order is kept."""
    by_title = {_title_key(t): i for t, i in titles.items()}
    for entry in entries:
        doi = (entry.get("doi") or "").lower()
        entry["owned_item_id"] = dois.get(doi) if doi else None
        entry["owned_item_id"] = entry["owned_item_id"] or by_title.get(_title_key(entry.get("title", "")))
    return sorted(entries, key=lambda e: e["owned_item_id"] is None)
