"""The reference desk's model jobs. See backend/clerk.py for how a job runs.

READ_QUERY  reads a request into topic and scope, choosing from the library's vocabulary.
NOTE        writes one indicative sentence about an item's passages, checked by entailment.
ALSO_TRY    picks next searches from terms on the results; their relation comes from their words.
THEMES      names clusters of results, with a label drawn from their titles.

Each prompt is short, with a few plain rules and at most one example, because
small models follow those better than long instructions. Each guard checks the
answer against the job's own input; docs/DESK_CLERK.md records why each rule exists.
"""

import re
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend import query_reader
from backend.clerk import GuardFailure, Job
from backend.desk import query_terms, stem, title_words

_STRINGS = {"type": "array", "items": {"type": "string"}}


def _choice(values: List[str], many: bool, limit: int = 6) -> Dict[str, Any]:
    """A field restricted to `values`, so constrained decoding cannot invent a name."""
    if many:
        if not values:
            return {"type": "array", "maxItems": 0, "items": {"type": "string"}}
        return {"type": "array", "maxItems": limit, "items": {"type": "string", "enum": values}}
    if not values:
        return {"type": "null"}
    return {"type": ["string", "null"], "enum": values + [None]}


def _words(text: str) -> set:
    # stem() keeps "example" but cuts "examples" to "exampl": dropping a final "e" lets them meet.
    return {stem(w).rstrip("e") for w in title_words(text)}


# ---------------------------------------------------------------------- #
# READ_QUERY                                                               #
# ---------------------------------------------------------------------- #

# Date phrases. "Recent" is not one: it sets no year, so it stays in the topic.
_TIME_WORDS = re.compile(
    r"\d{4}|\b\d0['’]?s\b|decades?|century|centuries|\byears?\b|this year|"
    r"\b(?:twen|thir|for|fif|six|seven|eigh|nine)ties\b|\b(?:pre|post)-?\d|\b(?:older|oldest|newest|latest|earliest)\b", re.I)
_TYPE_WORDS = re.compile(
    r"\b(books?|monographs?|chapters?|thes[ie]s|dissertations?|conference|proceedings|preprints?|reports?|"
    r"working papers?|journal articles?|livres?|thèses|chapitres?|bücher|buch|kapitel|libros?|tesis|capítulos?)\b", re.I)
_COLLECTION_WORDS = re.compile(r"\b(?:collections?|folders?)\b|\bin \"", re.I)
_TAG_WORDS = re.compile(r"\btag(?:ged|s)?\b|#\w", re.I)
# Exclusion markers. Bare "not" and "without" are left out: "why workers do not join
# unions" and "organising without unions" are about unions, not against them.
_EXCLUDE_MARKER = (r"(?:(?:,\s*|\b(?:but|and)\s+)not\b|(?:,\s*|\b(?:but|and)\s+)?(?:\bnot (?:about|on|in|from)|"
                   r"\bnothing (?:about|on|from|in)|\bno more|\bexcluding|\bexcept(?: for)?|\bother than|\bleaving out|"
                   r"\bapart from|\baside from|\bignoring|\bminus))")


def _scope_hint(text: str, authors: List[str]) -> bool:
    """Whether text still holds something that may limit the search: a date phrase,
    a kind of document, a collection or tag, an exclusion, or a library author."""
    if _TIME_WORDS.search(text) or _TYPE_WORDS.search(text) or _COLLECTION_WORDS.search(text) or _TAG_WORDS.search(text) or \
            re.search(_EXCLUDE_MARKER, text, re.I):
        return True
    return any(re.search(rf"\b{re.escape(a)}\b", text, re.I) for a in authors)


def _read_query_prompt(d: Dict[str, Any]) -> str:
    c = d["candidates"]

    def listed(values):
        return ", ".join(f'"{v}"' for v in values) if values else "none"

    return f"""Find the limits in a library search request.

Request: "{d['query']}"
Today's date: {d['today']}

Fields:
- year_min, year_max: only when the request limits dates ("since 2015", "the nineties", "pre-2000", "the last five years"). Otherwise null. An open end is null, not today's year.
- author: only when the request asks for someone's own work ("by X", "X's books", "anything X wrote", "X on beauty"). Choose from: {listed(c['authors'])}. A person the request asks about is not an author limit.
- tags: only tags the request names after "tagged" or "#". Choose from: {listed(c['tags'])}.
- collections: only a collection or folder the request names, even loosely ("my thesis folder"). Choose from: {listed(c['collections'])}.
- item_types: only when the request asks for a kind of document ("books", "theses", "chapters"). Choose from: {listed(c['item_types'])}.
- exclude: what the request rules out ("not X", "excluding X", "nothing on X"), copied from the request.
Leave a field empty or null unless the request says it.

Example: "chapters on river trade in the 1800s, not about canals" gives year_min 1800, year_max 1899, item_types ["bookSection"], exclude ["canals"], and empty or null everything else."""


def _read_query_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    c = d["candidates"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["year_min", "year_max", "author", "tags", "collections", "item_types", "exclude"],
        "properties": {
            "year_min": {"type": ["integer", "null"]},
            "year_max": {"type": ["integer", "null"]},
            "author": _choice(c["authors"], many=False),
            "tags": _choice(c["tags"], many=True),
            "collections": _choice(c["collections"], many=True),
            "item_types": _choice(c["item_types"], many=True, limit=3),
            "exclude": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        },
    }


def _read_query_skip(d: Dict[str, Any]) -> str:
    """Ask the model only when the library reader left a possible limit in the topic."""
    if _scope_hint(d["library_reading"]["topic"], d["candidates"]["authors"]):
        return ""
    return "the library reader found every limit"


_COLLECTION_PHRASE = r"\b(?:in|from|of)\s+(?:my|the|our)?\s*((?:[\w\-]+\s+){0,4}?)(?:collection|folder)s?\b|\bin \"([^\"]+)\""
_TAG_PHRASE = r"(?:\bwith\s+(?:the\s+)?)?(?:\btagged|\btags?|#)\s*(?:as |with )?\"?((?:[\w\-]+\"?\s*){1,3})"
_DATE_PHRASE = (r"\b(?:(?:from|in|during|since|before|after|over|until)\s+)?(?:the\s+)?(?:early\s+|late\s+|mid-?)?"
                r"(?:(?:pre|post)-?\d{4}|\d{4}s?|\d0['’]?s|(?:twen|thir|for|fif|six|seven|eigh|nine)ties|"
                r"(?:last|past)\s+(?:\w+\s+)?(?:years?|decades?)|this year)\b")


def _window(query: str, pattern: str) -> str:
    """The words the request uses to name a collection or tag."""
    return " ".join(next((g for g in m.groups() if g), "") for m in re.finditer(pattern, query, re.I))


def _spans(query: str, pattern: str) -> List[Tuple[int, int]]:
    return [m.span() for m in re.finditer(pattern, query, re.I)]


def _authored(name: str, query: str) -> Optional[Tuple[int, int]]:
    """Where the request asks for the person's own work, not about the person."""
    n = re.escape(name)
    work = r"(?:works?|writings?|books?|papers?|articles?|essays?|chapters?|thes[ie]s|texts?)"
    for p in (
        rf"\bby\s+(?:[\w.'’\-]+\s+){{0,2}}?{n}\b",
        rf"\b{n}['’]s?\s+(?:\w+\s+)?{work}\b",
        rf"\b{n},?\s+(?:et al\.?|and (?:colleagues|co-?authors|collaborators))",
        rf"\b{n}\s+(?:has |have |had )?(?:wrote|written|writes|published)\b",
        rf"\b{work} of\s+(?:[\w.'’\-]+\s+){{0,2}}?{n}\b",
        rf"^{n}(?=\s+on\b)",
    ):
        m = re.search(p, query, re.I)
        if m:
            return m.span()
    return None


def _read_query_guard(out: Dict[str, Any], d: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the model's reading into the library reader's.

    Measured on the evaluation set (docs/DESK_CLERK.md), the library reader is right
    about every phrase it recognises and the model is not: it misses date phrases and
    reads people the request asks about as authors. So the library reading wins on
    every field it filled, and the model may fill only the fields it left empty, each
    value tied to a phrase in the request. The topic is the request without those
    phrases: asked to write it, a 4B model copied the whole request back.
    """
    q = d["query"]
    this_year = int(d["today"][:4])
    library = d["library_reading"]
    added: Dict[str, Any] = {}
    spans: List[Tuple[int, int]] = []

    # Dates: a date phrase, plausible years, and no "until today" upper limit.
    lo, hi = out["year_min"], out["year_max"]
    if hi is not None and hi >= this_year:
        hi = None
    lo = lo if lo is not None and 1000 <= lo <= this_year else None
    hi = hi if hi is not None and 1000 <= hi else None
    years = [int(y) for y in re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", q)]
    if years:  # stated years are copied, give or take the one that "before"/"after" moves
        lo = lo if lo is None or any(abs(lo - y) <= 1 for y in years) else None
        hi = hi if hi is None or any(abs(hi - y) <= 1 for y in years) else None
    if (lo or hi) and _TIME_WORDS.search(q) and library["year_min"] is None and library["year_max"] is None:
        if lo and hi and lo > hi:
            lo, hi = hi, lo
        added.update(year_min=lo, year_max=hi)
        spans += _spans(q, _DATE_PHRASE)

    if out["author"] and not library["author"]:
        where = _authored(out["author"], q)
        if where:
            added["author"] = out["author"]
            spans.append(where)

    # A tag or collection that shares words with the request must share them with the
    # phrase that names it ("readings from my thesis folder" is not the "Reading group").
    tag_words = _words(_window(q, _TAG_PHRASE))
    tags = [t for t in out["tags"] if _TAG_WORDS.search(q) and _words(t) & tag_words]
    if tags and not library["tags"]:
        added["tags"] = tags
        spans += _spans(q, _TAG_PHRASE)
    coll_phrase = _window(q, _COLLECTION_PHRASE)
    # A loose name ("my thesis folder" for "PhD Research") needs a phrase that names a
    # collection: "the folder structure of digital archives" names none.
    named = _words(coll_phrase)
    colls = [c for c in out["collections"]
             if _COLLECTION_WORDS.search(q) and (_words(c) & named or (named and not _words(c) & _words(q)))]
    if colls and not library["collections"]:
        added["collections"] = colls
        spans += _spans(q, _COLLECTION_PHRASE)

    # A kind of document: a type word used as the thing asked for ("chapters on …",
    # "surveillance chapters before 2000"), not part of the topic ("reports of …",
    # "books as objects") or of a collection's name.
    asked_for = (r"(?=\s+(?:on|about|by|from|that|which|concerning|regarding|before|after|since|until|in|"
                 r"published|written|between)\b|\s*[,.;?!]|\s*$)")
    type_spans = [sp for sp in _spans(q, _TYPE_WORDS.pattern + asked_for)
                  if not any(a <= sp[0] < b for a, b in _spans(q, _COLLECTION_PHRASE))]
    if out["item_types"] and not library["item_types"] and type_spans:
        added["item_types"] = out["item_types"]
        spans += type_spans

    for term in (t.strip() for t in out["exclude"]):
        m = term and re.search(_EXCLUDE_MARKER + r"\s+(?:[\w'’\-]+\s+){0,3}?" + re.escape(term), q, re.I)
        if m and not library["exclude"] and len(added.get("exclude", [])) < 3:
            added.setdefault("exclude", []).append(term)
            spans.append(m.span())

    if not added:
        return dict(library)
    reading = {**library, **added}
    reading["topic"] = query_reader.topic_without(q, [tuple(sp) for sp in d["library_spans"]] + spans)
    return reading


READ_QUERY = Job(
    name="read_query",
    prompt=_read_query_prompt,
    schema=_read_query_schema,
    guard=_read_query_guard,
    fallback=lambda d: d["library_reading"],
    skip=_read_query_skip,
    max_tokens=160,
    timeout=8.0,
)


def read_query_input(query: str, vocab: Dict[str, Any], today: date) -> Dict[str, Any]:
    """Everything READ_QUERY needs: the request, the library reading and the shortlist to choose from."""
    library_reading, spans = query_reader.read(query, vocab, today, with_spans=True)
    return {
        "query": query,
        "today": today.isoformat(),
        "library_reading": library_reading,
        "library_spans": [list(sp) for sp in spans],
        "candidates": query_reader.candidates(query, vocab, library_reading),
    }


# ---------------------------------------------------------------------- #
# NOTE                                                                     #
# ---------------------------------------------------------------------- #

# Indicative, not informative or evaluative (ANSI/NISO Z39.14; annotated-bibliography
# practice): the note says what the passages cover, never whether they are right.
_EVALUATIVE = re.compile(
    r"\b(convincing(?:ly)?|compelling(?:ly)?|important|groundbreaking|seminal|excellent|flawed|insightful|"
    r"valuable|crucial|definitive(?:ly)?|brilliant|persuasive(?:ly)?|landmark|"
    r"prove[sd]?|proves|proving|shows? that|showing|demonstrat(?:es|ed|ing) that|demonstrating|establish(?:es|ed) that|"
    r"confirms? that|it is clear)\b",
    re.I,
)
_INDICATIVE = re.compile(
    r"^(?:describes|discusses|reports|compares|examines|outlines|explains|argues|notes|presents|analy[sz]es|"
    r"considers|reviews|introduces|defines|traces|explores|sets out|summari[sz]es)\s+(?:how|that|why|whether|what)?\s*", re.I)
NOTE_MIN_ENTAILMENT = 0.5
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _windows(texts: List[str], size: int) -> List[str]:
    """Runs of `size` consecutive sentences in each text (texts shorter than that are already premises)."""
    out = []
    for text in texts:
        sentences = _SENTENCE.split(text)
        out += [" ".join(sentences[i:i + size]) for i in range(len(sentences) - size + 1)]
    return out


def _note_prompt(d: Dict[str, Any]) -> str:
    passages = "\n".join(f"[p. {p['page'] or '?'}] {p['text']}" for p in d["passages"])
    return f"""Write a one-sentence note that tells a researcher what this item's passages say about their search, so they can decide whether to open it.

Search: "{d['query']}"
Item: {d['title']}
Passages:
{passages}

Rules:
- Say what the passages discuss, describe or report, starting with a verb such as "Describes", "Discusses", "Compares" or "Reports".
- Use only what the passages say. Add no names, numbers or claims that are not in them.
- Do not judge the work: no "important", "convincing", "shows that" or "proves".
- At most 30 words.
- page: the page of the passage the note relies on most, or null if unknown."""


def _note_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    pages = sorted({p["page"] for p in d["passages"] if p.get("page")})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["note", "page"],
        "properties": {
            "note": {"type": "string", "maxLength": 300},
            "page": {"type": ["integer", "null"], "enum": pages + [None]} if pages else {"type": "null"},
        },
    }


def _note_guard(out: Dict[str, Any], d: Dict[str, Any]) -> Dict[str, Any]:
    from backend.embed_utils import entailment

    note = " ".join(out["note"].split()).strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", note) if s]
    if not sentences:
        raise GuardFailure("empty note")
    note = sentences[0]
    if len(note.split()) > 40:
        raise GuardFailure("longer than 40 words")
    if _EVALUATIVE.search(note):
        raise GuardFailure(f"evaluative: {_EVALUATIVE.search(note)[0]}")

    source = " ".join([d["title"], d["query"]] + [p["text"] for p in d["passages"]]).lower()
    # Capitalised words after the first, and numbers, must come from the input: the
    # cheapest hallucinations are invented names, places and figures.
    for token in re.findall(r"(?<!^)(?<![.!?]\s)\b([A-Z][\w'’\-]+|\d[\d.,]*)", note[1:]):
        t = token.lower().rstrip(".,")
        # "CNNs" for "CNN" and "MCMC-based" for "MCMC" add no name of their own.
        named = [part.lower() for part in token.rstrip(".,").split("-") if part[:1].isupper() or part[:1].isdigit()]
        if t not in source and t.rstrip("s") not in source and not (len(named) < len(token.split("-")) and all(n in source for n in named)):
            raise GuardFailure(f"not in the passages: {token}")

    # The check reads the note's content, without the indicative verb ("Describes how"),
    # against each passage, all of them together (a note may join two), and windows of
    # three sentences (SummaC, Laban et al. 2022): a long premise is cut at the NLI
    # model's 512 tokens, and on real abstracts the windows passed 22 of 30 notes
    # against 18, while no known-bad note scored above 0.34 either way.
    texts = [p["text"] for p in d["passages"]]
    claim = _INDICATIVE.sub("", note)
    premises = texts + ([" ".join(texts)] if len(texts) > 1 else []) + _windows(texts, 3)
    score = entailment(premises, claim[:1].upper() + claim[1:])
    if score < NOTE_MIN_ENTAILMENT:
        raise GuardFailure(f"not supported by the passages ({score:.2f})")

    page = out.get("page")
    if page is None:
        page = d["passages"][0].get("page")
    return {"note": note if note.endswith((".", "!", "?")) else note + ".", "page": page, "support": round(score, 2)}


NOTE = Job(
    name="note",
    prompt=_note_prompt,
    schema=_note_schema,
    guard=_note_guard,
    fallback=lambda d: None,  # keep the query-biased extract the bibliography already shows
    max_tokens=120,
    timeout=20.0,
)


def note_input(query: str, item: Dict[str, Any], limit_chars: int = 2400) -> Dict[str, Any]:
    """The item's best passages, up to about 600 tokens, for one NOTE call."""
    passages, used = [], 0
    for p in item.get("passages", [])[:3]:
        text = " ".join((p.get("text") or "").split()).lstrip("…")
        if used + len(text) > limit_chars and passages:
            break
        passages.append({"page": p.get("page"), "text": text[: limit_chars - used]})
        used += len(text)
    return {"query": query, "title": item.get("title") or "Untitled", "passages": passages}


# ---------------------------------------------------------------------- #
# ALSO_TRY                                                                 #
# ---------------------------------------------------------------------- #

def relation(term: str, query: str) -> str:
    """Broader, narrower or related, from the words alone (ISO 25964's generic relation
    read lexically): a term inside the search is broader, one that contains it is
    narrower. A model's guess at hierarchy is world knowledge, which small models lack."""
    t, q = _words(term), _words(query)
    if t and q and t < q:
        return "broader"
    if t and q and q < t:
        return "narrower"
    return "related"


def _also_try_prompt(d: Dict[str, Any]) -> str:
    return f"""A researcher searched their library for: "{d['query']}"
These subject terms appear on the items that came back: {", ".join(f'"{t}"' for t in d['candidates'])}

Choose up to four terms that would make useful next searches, most useful first. Choose only from the list, and skip terms that mean the same as the search."""


def _also_try_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["terms"],
        "properties": {"terms": {"type": "array", "maxItems": 4, "items": {"type": "string", "enum": d["candidates"]}}},
    }


def _also_try_guard(out: Dict[str, Any], d: Dict[str, Any]) -> List[Dict[str, str]]:
    query = _words(d["query"])
    seen, kept = set(), []
    for term in out["terms"]:
        if term in seen or term not in d["candidates"] or (_words(term) and _words(term) == query):
            continue
        seen.add(term)
        kept.append({"term": term, "relation": relation(term, d["query"])})
    return kept


ALSO_TRY = Job(
    name="also_try",
    prompt=_also_try_prompt,
    schema=_also_try_schema,
    guard=_also_try_guard,
    fallback=lambda d: [{"term": t, "relation": relation(t, d["query"])} for t in d["candidates"][:3]],
    max_tokens=160,
    timeout=12.0,
)


def also_try_input(query: str, items: List[Dict[str, Any]], limit: int = 20) -> Dict[str, Any]:
    """Next-search candidates from the results: their tags, else phrases their titles share.

    Drawn from the library so every suggestion leads somewhere; ordered by how many
    results carry them, so the fallback is the most common ones.
    """
    query_words = _words(query)
    counts: Counter = Counter()
    for item in items:
        for tag in set(item.get("tags") or []):
            if not (_words(tag) and _words(tag) == query_words):
                counts[tag] += 1
    if len(counts) < 5:  # a library with few tags: use two-word phrases the titles share
        for item in items:
            words = re.findall(r"[a-z][a-z\-]+", (item.get("title") or "").lower())
            phrases = {f"{a} {b}" for a, b in zip(words, words[1:]) if title_words(a) and title_words(b)}
            for phrase in phrases:
                if not _words(phrase) <= query_words:  # a phrase from the search itself leads nowhere new
                    counts[phrase] += 1
    terms = [t for t, n in counts.most_common() if n >= 2 or len(items) < 4][:limit]
    return {"query": query, "candidates": terms}


# ---------------------------------------------------------------------- #
# THEMES                                                                   #
# ---------------------------------------------------------------------- #

def _themes_prompt(d: Dict[str, Any]) -> str:
    groups = "\n".join(f"Group {g['id']}: " + "; ".join(g["titles"][:8]) for g in d["groups"])
    return f"""These are groups of items from one search in a research library. Give each group a label of two to four words naming what its titles have in common. Use words from the titles where you can.

{groups}"""


def _themes_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    ids = [g["id"] for g in d["groups"]]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["labels"],
        "properties": {
            "labels": {
                "type": "array",
                "minItems": len(ids),
                "maxItems": len(ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "label"],
                    "properties": {"id": {"type": "integer", "enum": ids}, "label": {"type": "string", "maxLength": 40}},
                },
            }
        },
    }


def _fallback_label(group: Dict[str, Any]) -> str:
    """The tag most of the group shares, else its most common title word."""
    tags = Counter(t for tags in group.get("tags", []) for t in set(tags))
    common = [t for t, n in tags.most_common(1) if n >= 2]
    if common:
        return common[0]
    # Whole words in title order, so ties go to the first one and no stem is shown.
    words = Counter(w.lower() for title in group["titles"] for w in re.findall(r"[\w\-]+", title)
                    if len(w) > 3 and title_words(w))
    return words.most_common(1)[0][0].capitalize() if words else "Other"


def _themes_guard(out: Dict[str, Any], d: Dict[str, Any]) -> Dict[int, str]:
    by_id = {g["id"]: g for g in d["groups"]}
    labels = {}
    for entry in out["labels"]:
        group = by_id.get(entry["id"])
        label = " ".join(entry["label"].split()).strip(" .")
        vocabulary = set().union(*(_words(t) for t in group["titles"]), *(_words(t) for tags in group.get("tags", []) for t in tags))
        # A label names what the titles share: it must reuse at least one of their words.
        if not label or len(label.split()) > 5 or not (_words(label) & vocabulary):
            label = _fallback_label(group)
        labels[entry["id"]] = label
    for gid, group in by_id.items():
        labels.setdefault(gid, _fallback_label(group))
    return labels


THEMES = Job(
    name="themes",
    prompt=_themes_prompt,
    schema=_themes_schema,
    guard=_themes_guard,
    fallback=lambda d: {g["id"]: _fallback_label(g) for g in d["groups"]},
    max_tokens=200,
    timeout=15.0,
)


def cluster_items(items: List[Dict[str, Any]], embed) -> List[Dict[str, Any]]:
    """Group results by their titles' meaning. embed(texts) returns vectors.

    Three groups from nine items, four from sixteen; fewer items are not grouped.
    """
    if len(items) < 9:
        return []
    import numpy as np
    from sklearn.cluster import KMeans

    k = 4 if len(items) >= 16 else 3
    titles = [it.get("title") or "" for it in items]
    vectors = np.asarray(embed(titles), dtype=float)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    labels = KMeans(n_clusters=k, n_init=4, random_state=0).fit_predict(vectors)
    groups = []
    for gid in range(k):
        members = [it for it, lab in zip(items, labels) if lab == gid]
        if members:
            groups.append({
                "id": gid + 1,
                "item_ids": [m["item_id"] for m in members],
                "titles": [m.get("title") or "" for m in members],
                "tags": [m.get("tags") or [] for m in members],
            })
    return groups
