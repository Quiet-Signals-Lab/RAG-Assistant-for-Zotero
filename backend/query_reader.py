"""Reading a search request: its topic, and the scope around it.

read() is the reader that needs no model. It matches the request against the
library's own vocabulary (author surnames, tags, collections, item types) and a
small set of date phrases, so everything it returns exists in the library.
candidates() shortlists the vocabulary a model may choose from when the clerk
reads the request instead (backend/clerk_jobs.py, READ_QUERY).

A reading is a dict: topic, year_min, year_max, author, tags, collections,
item_types, exclude.
"""

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.desk import stem, title_words

# The request words that name a kind of document, by Zotero item type. Only used
# when the word heads the request ("books on …", "Berlant's books"), never when it
# is part of the topic ("reports of police violence").
TYPE_WORDS = {
    "book": r"books?|monographs?",
    "bookSection": r"(?:book )?chapters?",
    "thesis": r"thes[ie]s|dissertations?",
    "conferencePaper": r"conference papers?|proceedings papers?",
    "preprint": r"preprints?",
    "report": r"reports?|working papers?",
    "journalArticle": r"journal articles?",
}
_TYPE_ANY = "|".join(f"(?:{p})" for p in TYPE_WORDS.values())
_TYPE_HEAD = re.compile(
    rf"(?:\b(?:find|show|list|get)(?: me)? |['’]s )(?:the |all |some )?({_TYPE_ANY})\b"
    rf"|\b({_TYPE_ANY})\s+(?=on|about|by|from|that|which|concerning|regarding|dealing)\b",
    re.I,
)

_YEAR = r"(1[5-9]\d{2}|20\d{2})"
_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}
_DECADES = {"twen": 20, "thir": 30, "for": 40, "fif": 50, "six": 60, "seven": 70, "eigh": 80, "nine": 90}
_SINCE = r"since|from|depuis|seit|desde|dal|sinds|vanaf"
_BEFORE = r"before|prior to|avant|vor|antes de|prima del|voor"
_UNTIL = r"until|till|up to|through|jusqu['’]en|bis"

# Request wording around the topic. A request verb is never part of a topic; a
# word such as "research" or "work" is filler only when a preposition follows it
# ("work on riders", but "research ethics", "work-life balance").
_REQUEST = re.compile(r"^(?:please\s+)?(?:find|search for|look(?:ing)? for|show me|i need|i want|i'?m looking for)\s+", re.I)
_WORKS_ON = re.compile(
    r"^(?:(?:all |any |some |the )?(?:papers?|articles?|works?|items?|sources?|literature|research|readings?|texts?|"
    r"writings?|stuff|anything|everything)\s+)(?:on|about|regarding|concerning|dealing with|that discuss(?:es)?)\s+",
    re.I,
)
# A preposition left at either end once a limit is cut out ("Kant on beauty" → "on beauty").
_LEAD = re.compile(r"^(?:on|about|regarding|concerning)\s+", re.I)
_TRAIL = re.compile(r"\s*\b(?:by|from|in|on|about|since|of|published|written)\s*$", re.I)

# A decade or century, with the word before it: "the 1990s", "before the 90s",
# "since the nineties", "the early 2000s", "the 1800s" (a century).
_PERIOD = (r"\b(?:(?P<rel>before|until|till|through|up to|since|after|from|in|during)\s+)?"
           r"(?:the\s+)?(?:(?P<part>early|mid|late)[-\s]?)?(?:(?P<century>1[5-9]|20)?(?P<digit>\d)0['’]?s|(?P<word>twen|thir|for|fif|six|seven|eigh|nine)ties)\b")


def _period(m: "re.Match") -> Tuple[Optional[int], Optional[int]]:
    if m["word"]:
        start = 1900 + _DECADES[m["word"].lower()]
        end = start + 9
    else:
        start = int((m["century"] or ("19" if int(m["digit"]) >= 3 else "20")) + m["digit"] + "0")
        end = start + 99 if m["century"] and m["digit"] == "0" and start < 2000 else start + 9
    part = (m["part"] or "").lower()
    if part:  # thirds of the period: the early 1990s are 1990-1993
        third = (end - start + 1) // 3
        start, end = {"early": (start, start + third), "mid": (start + third, end - third), "late": (end - third, end)}[part]
    word = (m["rel"] or "").lower()
    if word == "before":
        return None, start - 1
    if word in ("until", "till", "through", "up to"):
        return None, end
    if word == "since":
        return start, None
    if word == "after":
        return end + 1, None
    return start, end


def _years(query: str, today: date) -> Tuple[Optional[int], Optional[int], List[Tuple[int, int]]]:
    """Year limits in the request and the spans of text that set them."""
    q = query
    patterns: List[Tuple[str, Any]] = [
        (rf"\b(?:between|from)\s+{_YEAR}\s+(?:and|to|until)\s+{_YEAR}\b",
         lambda m: (min(int(m[1]), int(m[2])), max(int(m[1]), int(m[2])))),
        (rf"\b{_YEAR}\s*[-–]\s*{_YEAR}\b", lambda m: (min(int(m[1]), int(m[2])), max(int(m[1]), int(m[2])))),
        (_PERIOD, _period),
        (r"\b(?:(?:in|from|over|during) the )?(?:last|past)\s+(\d+|" + "|".join(_NUMBERS) + r")\s+years?\b",
         lambda m: (today.year - (int(m[1]) if m[1].isdigit() else _NUMBERS[m[1].lower()]), None)),
        (r"\b(?:(?:in|from|over|during) the )?(?:last|past)\s+decade\b", lambda m: (today.year - 10, None)),
        (r"\bthis year\b", lambda m: (today.year, today.year)),
        (rf"\bpre-?{_YEAR}\b", lambda m: (None, int(m[1]) - 1)),
        (rf"\bpost-?{_YEAR}\b", lambda m: (int(m[1]) + 1, None)),
        (rf"\bafter\s+{_YEAR}\b", lambda m: (int(m[1]) + 1, None)),
        (rf"\b(?:{_SINCE})\s+{_YEAR}\b", lambda m: (int(m[1]), None)),
        (rf"\b(?:{_BEFORE})\s+{_YEAR}\b", lambda m: (None, int(m[1]) - 1)),
        (rf"\b(?:{_UNTIL})\s+{_YEAR}\b", lambda m: (None, int(m[1]))),
        (rf"\b(?:in|during|published in)\s+{_YEAR}\b", lambda m: (int(m[1]), int(m[1]))),
    ]
    lo = hi = None
    spans: List[Tuple[int, int]] = []
    for pattern, read in patterns:
        for m in re.finditer(pattern, q, re.I):
            if any(a < m.end() and m.start() < b for a, b in spans):
                continue  # part of a phrase already read ("in 1990" inside "in 1990-2000")
            a, b = read(m)
            lo = a if a is not None else lo
            hi = b if b is not None else hi
            spans.append((m.start(), m.end()))
    if lo and hi and lo > hi:
        lo = hi = None  # "before 1990 or after 2000": no single range says that
    return lo, hi, spans


def _match_name(words: List[str], names: Dict[str, str]) -> Optional[str]:
    """The library name at the start of `words`: two words first ("de Beauvoir"), then one."""
    for n in (3, 2, 1):
        key = " ".join(words[:n]).lower().strip("'’.,;:")
        if key in names:
            return names[key]
    return None


def _best_match(phrase: str, names: Iterable[str]) -> Optional[str]:
    """A collection or tag named loosely: exact first, then all words of one inside the other."""
    p = phrase.lower().strip()
    names = list(names)
    for n in names:
        if n.lower() == p:
            return n
    pw = title_words(p)
    if not pw:
        return None
    hits = [n for n in names if pw and (pw <= title_words(n) or title_words(n) <= pw) and title_words(n)]
    return min(hits, key=len) if hits else None


def read(query: str, vocab: Dict[str, Any], today: Optional[date] = None, with_spans: bool = False):
    """Read a request without a model. vocab: authors, tags, collections, item_types (lists of names).

    with_spans also returns the (start, end) spans of the phrases read as limits.
    """
    today = today or date.today()
    q = " ".join((query or "").split())
    year_min, year_max, spans = _years(q, today)

    authors = {a.lower(): a for a in vocab.get("authors", []) if a}
    types_present = set(vocab.get("item_types", []))
    reading: Dict[str, Any] = {
        "topic": q, "year_min": year_min, "year_max": year_max, "author": None,
        "tags": [], "collections": [], "item_types": [], "exclude": [],
    }

    # Item type heading the request: "books on…", "Berlant's books", "theses about…".
    for m in _TYPE_HEAD.finditer(q):
        word = (m[1] or m[2] or "").lower()
        for type_name, pattern in TYPE_WORDS.items():
            if type_name in types_present and re.fullmatch(pattern, word, re.I) and type_name not in reading["item_types"]:
                reading["item_types"].append(type_name)
                start = m.start(1) if m[1] else m.start(2)
                spans.append((start, start + len(word)))

    # Author: "by Berlant", "written by de Beauvoir", or "Berlant's books" (possessive + a work word).
    for m in re.finditer(r"\b(?:written |authored |edited )?by\s+((?:[\w'’\-]+\s*){1,3})", q, re.I):
        name = _match_name(m[1].split(), authors)
        if name:
            reading["author"] = name
            spans.append((m.start(), m.start(1) + len(name)))
            break
    if not reading["author"]:
        work = rf"(?:{_TYPE_ANY}|works?|writings?|papers?|articles?|essays?)"
        m = re.search(rf"\b([\w\-]+(?:\s[\w\-]+)?)['’]s\s+{work}\b", q, re.I)
        if m:
            name = _match_name(m[1].split()[-1:], authors) or _match_name(m[1].split(), authors)
            if name:
                reading["author"] = name
                spans.append((m.start(1), m.end(1) + 2))

    # Collections: 'in "PhD Research"', "in my PhD collection", "from my thesis folder".
    for m in re.finditer(r'\bin\s+"([^"]+)"|\b(?:in|from)\s+(?:my|the)\s+([\w\s\-]{2,40}?)\s+(?:collection|folder)\b', q, re.I):
        name = _best_match(m[1] or m[2], vocab.get("collections", []))
        if name and name not in reading["collections"]:
            reading["collections"].append(name)
            spans.append(m.span())

    # Tags: 'tagged "Labour"', "tagged labour", "#labour".
    for m in re.finditer(r'\btagged\s+(?:"([^"]+)"|([\w\-]+))|#([\w\-]+)', q, re.I):
        name = _best_match(m[1] or m[2] or m[3], vocab.get("tags", []))
        if name and name not in reading["tags"]:
            reading["tags"].append(name)
            spans.append(m.span())

    # Exclusions, only with an explicit marker: "but not X", ", not X", "not about X", "excluding X".
    for m in re.finditer(r"(?:,\s*|\bbut\s+)not\s+(?:about\s+|on\s+)?([^,.;]+)|\bnot\s+(?:about|on)\s+([^,.;]+)|\b(?:excluding|except(?: for)?|other than)\s+([^,.;]+)", q, re.I):
        phrase = (m[1] or m[2] or m[3]).strip()
        phrase = re.split(r"\s+(?:and|or|but|in|from|since|by|before|after)\s+", phrase)[0].strip()
        words = phrase.split()[:4]
        if words:
            reading["exclude"].append(" ".join(words))
            spans.append(m.span())

    reading["topic"] = topic_without(q, spans)
    return (reading, spans) if with_spans else reading


def topic_without(query: str, spans: List[Tuple[int, int]]) -> str:
    """The request with the scope phrases cut out and the request wording trimmed."""
    keep, at = [], 0
    for a, b in sorted(spans):  # spans may overlap: the library's and the model's evidence for one phrase
        if a > at:
            keep.append(query[at:a])
        at = max(at, b)
    keep.append(query[at:])
    topic = " ".join(" ".join(keep).split())
    topic = _WORKS_ON.sub("", _REQUEST.sub("", topic))
    if spans:
        topic = _LEAD.sub("", _TRAIL.sub("", topic.strip(" ,.;:-")))
    topic = topic.strip(" ,.;:-")
    return topic or query.strip()


def candidates(query: str, vocab: Dict[str, Any], found: Optional[Dict[str, Any]] = None, limit: int = 12) -> Dict[str, List[str]]:
    """The vocabulary a model may choose from for this request, kept short enough for a small prompt.

    Authors whose surname appears in the request; tags and collections that share a
    word with it, or every collection when the request mentions one; every item
    type in the library; plus whatever read() found.
    """
    found = found or {}
    tokens = {re.sub(r"['’]s?$", "", t.lower()) for t in re.findall(r"[\w'’\-]+", query or "")}
    words = title_words(query or "")
    stems = {stem(w) for w in words}

    def overlap(name: str) -> int:
        return len({stem(w) for w in title_words(name)} & stems)

    authors = [a for a in vocab.get("authors", []) if a and a.lower() in tokens]
    tags = sorted((t for t in vocab.get("tags", []) if overlap(t)), key=lambda t: (-overlap(t), len(t)))[:limit]
    colls = sorted((c for c in vocab.get("collections", []) if overlap(c)), key=lambda c: (-overlap(c), len(c)))[:limit]
    if re.search(r"\b(?:collections?|folders?)\b", query or "", re.I):
        # A collection named loosely ("my thesis folder") may share no word with its name.
        colls += [c for c in vocab.get("collections", []) if c not in colls][: 40 - len(colls)]
    out = {
        "authors": sorted(set(authors) | ({found["author"]} if found.get("author") else set())),
        "tags": sorted(set(tags) | set(found.get("tags", []))),
        "collections": sorted(set(colls) | set(found.get("collections", []))),
        "item_types": sorted(vocab.get("item_types", [])),
    }
    return out
