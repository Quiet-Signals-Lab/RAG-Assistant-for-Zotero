"""
Unit tests for metadata migration (MetadataMigration in metadata_migration.py).

The library is read once and keyed by item id; Chroma is paged.
"""

import pytest
from unittest.mock import Mock
from backend.metadata_migration import MetadataMigration


def _item(item_id, **meta):
    m = Mock()
    m.metadata = {"item_id": str(item_id), "title": f"Paper {item_id}", "authors": "", "tags": "",
                  "collections": "", "date": "2020", **meta}
    return m


def _chroma(ids=(), metadatas=()):
    mock = Mock()
    mock.collection = Mock()
    mock.collection.get.return_value = {"ids": list(ids), "metadatas": list(metadatas)}
    return mock


@pytest.fixture
def zotero():
    return Mock()


@pytest.fixture
def migration(zotero):
    return MetadataMigration(_chroma(), zotero)


class TestFetchUpdatedMetadata:
    def test_initialization(self, migration):
        assert migration.progress["total_chunks"] == 0
        assert migration.progress["failed_chunks"] == 0

    def test_lookup_is_by_item_id_not_first_row(self, migration, zotero):
        """Regression: every chunk used to receive the first library item's metadata."""
        zotero.search_parent_items_with_pdfs.return_value = [
            _item(1, title="First", authors="Adams"),
            _item(2, title="Second", authors="Baker", tags="NLP|ML", date="2021-03-10"),
        ]
        assert migration._fetch_updated_metadata("2") == {
            "title": "Second", "authors": "Baker", "tags": "NLP|ML", "collections": "",
            "year": 2021, "item_type": "",
        }
        assert migration._fetch_updated_metadata("1")["title"] == "First"

    def test_library_is_read_once(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.return_value = [_item(1), _item(2)]
        migration._fetch_updated_metadata("1")
        migration._fetch_updated_metadata("2")
        migration._fetch_updated_metadata("1")
        assert zotero.search_parent_items_with_pdfs.call_count == 1

    def test_year_parsing(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.return_value = [
            _item(1, date="2021-03-10"), _item(2, date="2022"), _item(3, date="unknown"), _item(4, date=""),
        ]
        assert migration._fetch_updated_metadata("1")["year"] == 2021
        assert migration._fetch_updated_metadata("2")["year"] == 2022
        assert migration._fetch_updated_metadata("3")["year"] is None
        assert migration._fetch_updated_metadata("4")["year"] is None

    def test_not_found(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.return_value = [_item(1)]
        assert migration._fetch_updated_metadata("99999") is None

    def test_zotero_error_returns_none(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.side_effect = Exception("database is locked")
        assert migration._fetch_updated_metadata("1") is None

    def test_special_characters(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.return_value = [_item(
            1, title='Paper with "quotes"', authors="O'Brien, J. & Smith-Jones, K.",
            tags="C++|C#|.NET", collections="Research (2020/2021)")]
        result = migration._fetch_updated_metadata("1")
        assert "quotes" in result["title"]
        assert "O'Brien" in result["authors"]


class TestNeedsUpdate:
    def test_year_format_change(self, migration):
        assert migration._needs_update({"year": "2020", "tags": "NLP"}, {"year": 2020, "tags": "NLP"})

    def test_tags_changed(self, migration):
        assert migration._needs_update({"year": 2020, "tags": ""}, {"year": 2020, "tags": "NLP|ML"})

    def test_collections_changed(self, migration):
        assert migration._needs_update({"year": 2020, "collections": ""}, {"year": 2020, "collections": "R"})

    def test_no_change(self, migration):
        meta = {"year": 2020, "tags": "NLP", "collections": "Research"}
        assert not migration._needs_update(meta, dict(meta))


class TestMigrateBatch:
    def test_each_chunk_gets_its_own_items_metadata(self, zotero):
        chroma = _chroma()
        migration = MetadataMigration(chroma, zotero)
        zotero.search_parent_items_with_pdfs.return_value = [
            _item(1, title="One", tags="NLP"), _item(2, title="Two", tags="ML")]
        chunk_ids = ["1:0", "2:0"]
        old = [
            {"item_id": "1", "year": "2020", "chunk_idx": 0, "page": 1, "pdf_path": "/p1.pdf"},
            {"item_id": "2", "year": "2021", "chunk_idx": 0, "page": 1, "pdf_path": "/p2.pdf"},
        ]
        migration._migrate_batch(chunk_ids, old, {})
        assert migration.progress["processed_chunks"] == 2
        assert migration.progress["updated_chunks"] == 2
        ids = chroma.collection.update.call_args[1]["ids"]
        metas = chroma.collection.update.call_args[1]["metadatas"]
        assert ids == ["1:0", "2:0"]
        assert [m["title"] for m in metas] == ["One", "Two"]
        assert [m["tags"] for m in metas] == ["NLP", "ML"]
        assert metas[0]["pdf_path"] == "/p1.pdf"  # chunk-specific fields preserved

    def test_missing_item_counts_as_failed(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.return_value = [_item(1)]
        old = [
            {"item_id": "1", "year": "2020", "chunk_idx": 0, "page": 1, "pdf_path": "/p1.pdf"},
            {"item_id": "2", "year": "2021", "chunk_idx": 0, "page": 1, "pdf_path": "/p2.pdf"},
        ]
        migration._migrate_batch(["1:0", "2:0"], old, {})
        assert migration.progress["processed_chunks"] == 2
        assert migration.progress["failed_chunks"] == 1

    def test_missing_item_id(self, migration):
        migration._migrate_batch(["orphan:0"], [{"year": "2020"}], {})
        assert migration.progress["failed_chunks"] == 1

    def test_cache_avoids_repeated_lookups(self, migration, zotero):
        zotero.search_parent_items_with_pdfs.return_value = [_item(1)]
        metas = [{"item_id": "1", "year": "2020", "chunk_idx": i, "page": i + 1, "pdf_path": "/p1.pdf"}
                 for i in range(3)]
        cache = {}
        migration._migrate_batch(["1:0", "1:1", "1:2"], metas, cache)
        assert "1" in cache
        assert zotero.search_parent_items_with_pdfs.call_count == 1

    def test_apply_updates_calls_chroma(self, migration):
        updates = [("1:0", {"item_id": "1", "year": 2020}), ("2:0", {"item_id": "2", "year": 2021})]
        migration._apply_metadata_updates(updates)
        migration.chroma.collection.update.assert_called_once()
        assert migration.chroma.collection.update.call_args[1]["ids"] == ["1:0", "2:0"]

    def test_apply_updates_propagates_chroma_error(self, migration):
        migration.chroma.collection.update.side_effect = Exception("ChromaDB error")
        with pytest.raises(Exception, match="ChromaDB error"):
            migration._apply_metadata_updates([("1:0", {"item_id": "1", "year": 2020})])


class TestMigrateAll:
    def test_small_library(self, zotero):
        chroma = _chroma(
            ["1:0", "1:1", "2:0"],
            [{"item_id": "1", "year": "2020", "chunk_idx": 0, "page": 1, "pdf_path": "/p1.pdf"},
             {"item_id": "1", "year": "2020", "chunk_idx": 1, "page": 2, "pdf_path": "/p1.pdf"},
             {"item_id": "2", "year": "2021", "chunk_idx": 0, "page": 1, "pdf_path": "/p2.pdf"}])
        zotero.search_parent_items_with_pdfs.return_value = [_item(1), _item(2, date="2021")]
        summary = MetadataMigration(chroma, zotero).migrate_all_metadata(batch_size=10)
        assert summary["total_chunks"] == 3
        assert summary["unique_items"] == 2
        assert summary["success"] is True
        assert "elapsed_seconds" in summary

    def test_pages_through_chroma(self, zotero):
        """Chroma is read with limit/offset until a short page comes back."""
        chroma = Mock(); chroma.collection = Mock()
        page1 = {"ids": [f"{i}:0" for i in range(3)],
                 "metadatas": [{"item_id": str(i), "year": "2020", "chunk_idx": 0, "page": 1, "pdf_path": ""}
                               for i in range(3)]}
        page2 = {"ids": ["3:0"], "metadatas": [{"item_id": "3", "year": "2020", "chunk_idx": 0, "page": 1, "pdf_path": ""}]}
        chroma.collection.get.side_effect = [page1, page2]
        zotero.search_parent_items_with_pdfs.return_value = [_item(i) for i in range(4)]
        migration = MetadataMigration(chroma, zotero)
        migration.PAGE_SIZE = 3
        summary = migration.migrate_all_metadata(batch_size=2)
        assert summary["total_chunks"] == 4
        assert summary["unique_items"] == 4
        offsets = [c.kwargs["offset"] for c in chroma.collection.get.call_args_list]
        assert offsets == [0, 3]

    def test_batching_updates_in_chunks(self, zotero):
        ids = [f"{i}:0" for i in range(25)]
        metas = [{"item_id": str(i), "year": "2020", "chunk_idx": 0, "page": 1, "pdf_path": f"/p{i}.pdf"}
                 for i in range(25)]
        chroma = _chroma(ids, metas)
        zotero.search_parent_items_with_pdfs.return_value = [_item(i) for i in range(25)]
        summary = MetadataMigration(chroma, zotero).migrate_all_metadata(batch_size=10)
        assert summary["total_chunks"] == 25
        assert summary["updated_chunks"] == 25
        assert chroma.collection.update.call_count == 3

    def test_empty_database(self, zotero):
        summary = MetadataMigration(_chroma(), zotero).migrate_all_metadata()
        assert summary == {"total_chunks": 0, "updated_chunks": 0, "failed_chunks": 0,
                           "unique_items": 0, "elapsed_seconds": 0, "success": True}

    def test_success_flag_reflects_failures(self, zotero):
        migration = MetadataMigration(_chroma(), zotero)
        migration.progress["failed_chunks"] = 5
        assert migration.migrate_all_metadata()["success"] is False
