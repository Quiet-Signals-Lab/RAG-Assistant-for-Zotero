"""Citation hydration and known-item lookups against a small Zotero-shaped database."""

import sqlite3
from unittest.mock import patch

import pytest

from backend.zotero_dbase import ZoteroLibrary

SCHEMA = """
CREATE TABLE items (itemID INTEGER PRIMARY KEY, itemTypeID INT, libraryID INT, key TEXT);
CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value);
CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT, fieldMode INT);
CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
CREATE TABLE itemCreators (itemID INT, creatorID INT, creatorTypeID INT, orderIndex INT);
CREATE TABLE groups (groupID INTEGER PRIMARY KEY, libraryID INT, name TEXT);
CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, contentType TEXT, path TEXT);
"""


class Library:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT INTO creatorTypes VALUES (1, 'author'), (2, 'editor')")
        self.conn.execute("INSERT INTO groups VALUES (555, 2, 'Lab group')")

    def _id(self, table, id_col, name_col, name):
        row = self.conn.execute(f"SELECT {id_col} FROM {table} WHERE {name_col} = ?", (name,)).fetchone()
        if row:
            return row[0]
        return self.conn.execute(f"INSERT INTO {table} ({name_col}) VALUES (?)", (name,)).lastrowid

    def add(self, item_id, type_name, key, fields=None, creators=(), library=1):
        type_id = self._id("itemTypes", "itemTypeID", "typeName", type_name)
        self.conn.execute("INSERT INTO items VALUES (?, ?, ?, ?)", (item_id, type_id, library, key))
        for name, value in (fields or {}).items():
            field_id = self._id("fields", "fieldID", "fieldName", name)
            value_id = self.conn.execute("INSERT INTO itemDataValues (value) VALUES (?)", (value,)).lastrowid
            self.conn.execute("INSERT INTO itemData VALUES (?, ?, ?)", (item_id, field_id, value_id))
        for order, (first, last, role) in enumerate(creators):
            creator_id = self.conn.execute(
                "INSERT INTO creators (firstName, lastName, fieldMode) VALUES (?, ?, 0)", (first, last)).lastrowid
            self.conn.execute("INSERT INTO itemCreators VALUES (?, ?, ?, ?)",
                              (item_id, creator_id, 1 if role == "author" else 2, order))
        self.conn.commit()


@pytest.fixture
def zlib(tmp_path):
    path = tmp_path / "zotero.sqlite"
    lib = Library(path)
    lib.add(1, "book", "QX7PL2M4", {
        "title": "The gig economy: A critical introduction", "date": "2020-00-00 2020",
        "publisher": "Polity", "place": "Cambridge", "ISBN": "978-1-5095-3636-8",
    }, [("Jamie", "Woodcock", "author"), ("Mark", "Graham", "author")])
    lib.add(2, "journalArticle", "RIDERS01", {
        "title": "Riders on the storm", "date": "2020-02-00 February 2020",
        "publicationTitle": "Work, Employment and Society", "volume": "34", "issue": "1",
        "pages": "35-54", "DOI": "10.1177/0950017019862954",
    }, [("Arianna", "Tassinari", "author"), ("Vincenzo", "Maccarrone", "author")])
    lib.add(3, "bookSection", "SECTION1", {"title": "Trade union responses", "bookTitle": "A modern guide",
                                           "date": "2021"}, [("Jane", "Editor", "editor")])
    lib.add(4, "attachment", "ATTACH01", {"title": "The gig economy full text PDF"})
    lib.conn.execute("INSERT INTO itemAttachments VALUES (4, 1, 'application/pdf', 'storage:gig.pdf')")
    lib.add(7, "attachment", "SNAPSHOT", {"title": "Snapshot"})
    lib.conn.execute("INSERT INTO itemAttachments VALUES (7, 2, 'text/html', 'storage:page.html')")
    lib.add(5, "book", "GONE0001", {"title": "The gig economy deleted copy", "date": "2020"})
    lib.conn.execute("INSERT INTO deletedItems VALUES (5)")
    lib.add(6, "journalArticle", "GROUP001", {"title": "Group paper 100% real", "date": "2019"},
            [("Ann", "Woodcock", "author")], library=2)
    lib.conn.commit()
    return ZoteroLibrary(str(path))


def test_bibliographic_flattens_fields_and_keeps_creator_order(zlib):
    bib = zlib.get_bibliographic(["1", "2", "3", "999", "not-an-id"])
    assert set(bib) == {"1", "2", "3"}
    book = bib["1"]
    assert book["item_key"] == "QX7PL2M4" and book["item_type"] == "book"
    assert book["year"] == 2020 and book["date"] == "2020"
    assert book["publisher"] == "Polity" and book["place"] == "Cambridge"
    assert [c["last"] for c in book["creators"]] == ["Woodcock", "Graham"]
    assert book["group_id"] is None
    assert book["pdf_key"] == "ATTACH01"
    assert bib["2"]["pdf_key"] is None  # an HTML snapshot is not a PDF
    article = bib["2"]
    assert article["container"] == "Work, Employment and Society"
    assert (article["volume"], article["issue"], article["pages"]) == ("34", "1", "35-54")
    assert article["date"] == "February 2020" and article["doi"] == "10.1177/0950017019862954"
    section = bib["3"]
    assert section["container"] == "A modern guide" and section["creators"][0]["role"] == "editor"


def test_bibliographic_reports_the_group_of_group_items(zlib):
    assert zlib.get_bibliographic([6])["6"]["group_id"] == 555


def test_bibliographic_with_no_ids_does_not_query(zlib):
    assert zlib.get_bibliographic([]) == {}


def test_field_search_skips_attachments_and_deleted_items(zlib):
    found = {item_id for item_id, _ in zlib.find_items_by_field(("title",), "gig economy")}
    assert found == {"1"}


def test_field_search_normalises_isbns(zlib):
    assert zlib.find_items_by_field(("ISBN",), "9781509536368", normalise=True) == [("1", "978-1-5095-3636-8")]
    assert zlib.find_items_by_field(("ISBN",), "9781509536368") == []


def test_field_search_treats_wildcards_literally(zlib):
    assert zlib.find_items_by_field(("title",), "100% real")[0][0] == "6"
    # Only the title that really contains "%", not every title.
    assert [i for i, _ in zlib.find_items_by_field(("title",), "%")] == ["6"]
    assert zlib.find_items_by_field(("title",), "Group_paper") == []


def test_creator_year_search_is_a_case_insensitive_prefix(zlib):
    assert set(zlib.find_items_by_creator_year("woodc", 2020)) == {"1"}
    assert set(zlib.find_items_by_creator_year("Woodcock", 2019)) == {"6"}
    assert zlib.find_items_by_creator_year("Woodcock", 1999) == []


@pytest.fixture
def bot(zlib):
    from backend.interface import ZoteroChatbot
    with patch("backend.interface.ChromaClient"), patch("backend.interface.ConversationStore"), \
            patch("backend.interface.QueryCondenser"):
        bot = ZoteroChatbot(db_path=zlib.db_path, chroma_path="/nowhere")
    bot.zlib = zlib
    bot.chroma.item_exists.side_effect = lambda item_id: item_id == "1"
    return bot


@pytest.mark.parametrize("query, expected", [
    ("Woodcock 2020", ["1"]),
    ("woodcock & graham (2020)", ["1"]),
    ("Woodcock & Tassinari 2020", []),
    ("10.1177/0950017019862954", ["2"]),
    ("isbn 978-1-5095-3636-8", ["1"]),
    ("the gig economy a critical introduction", ["1"]),
    ('"Riders on the storm"', ["2"]),
    ("how do platform workers organise collectively", []),
])
def test_known_items(bot, query, expected):
    found = bot._known_items(query)
    assert [k["item_id"] for k in found] == expected
    for k in found:
        assert k["indexed"] == (k["item_id"] == "1")
