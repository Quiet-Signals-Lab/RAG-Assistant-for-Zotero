"""Tests for ZoteroChatbot's indexing worker: progress accounting, incremental
filtering and full-reindex replacement. Chroma, Zotero, PDF extraction and
embeddings are all mocked."""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from backend.interface import ZoteroChatbot
from backend.zoteroitem import ZoteroItem


def _item(item_id, pdf_path="/pdfs/x.pdf"):
    return ZoteroItem(filepath=pdf_path, metadata={
        "item_id": str(item_id), "title": f"T{item_id}", "authors": "A", "tags": "", "collections": "",
        "date": "2020", "item_type": "journalArticle", "pdf_path": pdf_path,
    })


@pytest.fixture
def bot():
    b = ZoteroChatbot.__new__(ZoteroChatbot)
    b.zlib = Mock()
    b.chroma = Mock()
    b.chroma.get_indexed_item_ids.return_value = set()
    b.embedding_model_id = "test"
    b.is_indexing = False
    b._cancel_indexing = False
    b.excluded_collections = b.excluded_tags = b.excluded_item_types = []
    b.index_progress = {"processed_items": 0, "total_items": 0, "start_time": None, "elapsed_seconds": 0,
                        "eta_seconds": None, "skipped_items": 0, "mode": "full", "skip_reasons": [], "error": None}
    return b


def _run(bot, incremental, pages_by_path, exists=lambda p: True):
    """Run the worker synchronously with PDF text and embeddings mocked."""
    def pdf_factory(path):
        m = Mock()
        pages = pages_by_path[path]
        if isinstance(pages, Exception):
            m.extract_text_with_pages.side_effect = pages
        else:
            m.extract_text_with_pages.return_value = pages
        return m

    with patch("backend.interface.PDF", side_effect=pdf_factory), \
         patch("backend.interface.os.path.exists", side_effect=exists), \
         patch("backend.interface.get_embeddings_batch",
               side_effect=lambda chunks, mid: [np.zeros(4, dtype=np.float32) for _ in chunks]), \
         patch("backend.interface.get_embedding_dimension", return_value=4):
        bot._index_library_worker(incremental)


def test_every_item_is_counted_once_including_textless_pdfs(bot):
    bot.zlib.search_parent_items_with_pdfs.return_value = [
        _item(1, "/a.pdf"), _item(2, "/b.pdf"), _item(3, "/c.pdf"), _item(4, "/missing.pdf"),
    ]
    _run(bot, incremental=False, pages_by_path={
        "/a.pdf": [{"page_num": 1, "text": "Hello world. This is a test."}],
        "/b.pdf": [],                        # scanned PDF, no text layer
        "/c.pdf": RuntimeError("corrupt"),   # extraction failure
    }, exists=lambda p: p != "/missing.pdf")
    p = bot.index_progress
    assert p["processed_items"] == p["total_items"] == 4
    assert len(p["skip_reasons"]) == 3
    assert any("no extractable text" in r for r in p["skip_reasons"])
    assert any("PDF not found" in r for r in p["skip_reasons"])
    assert any("corrupt" in r for r in p["skip_reasons"])
    assert p["error"] is None
    assert bot.is_indexing is False
    bot.chroma.add_chunks.assert_called_once()
    kwargs = bot.chroma.add_chunks.call_args.kwargs
    assert kwargs["ids"] == ["1:0"]
    assert kwargs["metadatas"][0]["item_id"] == "1"
    assert kwargs["metadatas"][0]["year"] == 2020
    assert kwargs["metadatas"][0]["page"] == 1
    bot.chroma.build_bm25_index.assert_called_once()


def test_full_mode_replaces_existing_chunks(bot):
    bot.zlib.search_parent_items_with_pdfs.return_value = [_item(1, "/a.pdf")]
    _run(bot, incremental=False, pages_by_path={"/a.pdf": [{"page_num": 1, "text": "x y z."}]})
    bot.chroma.delete_item.assert_called_once_with("1")


def test_incremental_mode_skips_indexed_items(bot):
    bot.zlib.search_parent_items_with_pdfs.return_value = [_item(1, "/a.pdf"), _item(2, "/b.pdf")]
    bot.chroma.get_indexed_item_ids.return_value = {"1"}
    _run(bot, incremental=True, pages_by_path={"/b.pdf": [{"page_num": 3, "text": "new text."}]})
    p = bot.index_progress
    assert p["total_items"] == 1 and p["processed_items"] == 1
    assert p["skipped_items"] == 1
    bot.chroma.delete_item.assert_not_called()
    assert bot.chroma.add_chunks.call_args.kwargs["ids"] == ["2:0"]


def test_all_items_failing_sets_error(bot):
    bot.zlib.search_parent_items_with_pdfs.return_value = [_item(1, "/a.pdf")]
    _run(bot, incremental=False, pages_by_path={"/a.pdf": []})
    assert "All 1 items failed" in bot.index_progress["error"]
    bot.chroma.build_bm25_index.assert_not_called()


def test_locked_database_is_reported(bot):
    bot.zlib.search_parent_items_with_pdfs.side_effect = Exception("database is locked")
    _run(bot, incremental=True, pages_by_path={})
    assert "close Zotero" in bot.index_progress["error"]
    assert bot.is_indexing is False


def test_cancellation_stops_the_loop(bot):
    bot.zlib.search_parent_items_with_pdfs.return_value = [_item(1, "/a.pdf"), _item(2, "/b.pdf")]
    bot._cancel_indexing = True
    _run(bot, incremental=False, pages_by_path={})
    assert bot.index_progress["processed_items"] == 0
    assert bot._cancel_indexing is False
