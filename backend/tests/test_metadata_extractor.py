"""
Unit tests for LLM-based metadata extraction.

MetadataExtractor now delegates entirely to an LLM; there is no regex
fallback.  All tests therefore use a mock provider_manager and verify that:
  1. The LLM is always called when a provider is configured.
  2. The full set of fields (author, title, item_types, …) is correctly
     parsed from the LLM response.
  3. Error paths (missing provider, bad JSON, LLM exception) return safe
     empty-filter dicts.
"""

import pytest
from unittest.mock import Mock
from backend.metadata_extractor import MetadataExtractor, extract_metadata_filters


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_provider(json_str: str) -> Mock:
    """Return a mock ProviderManager whose .chat() returns a ChatResponse-like object."""
    response = Mock()
    response.content = json_str
    m = Mock()
    m.chat.return_value = response
    return m


def _empty_response() -> str:
    return '{"year_min": null, "year_max": null, "tags": [], "collections": [], "author": null, "title": null, "item_types": []}'


# ── TestMetadataExtractorLLM ──────────────────────────────────────────────────

class TestMetadataExtractorLLM:
    """LLM is always invoked when a provider_manager is present."""

    def test_year_min_extracted(self):
        provider = _make_provider('{"year_min": 2020, "year_max": null, "tags": [], "collections": [], "author": null, "title": null, "item_types": []}')
        filters = MetadataExtractor(provider).extract_filters("Papers after 2020")
        assert filters["year_min"] == 2020
        assert filters["year_max"] is None
        assert filters["has_filters"] is True

    def test_year_range_extracted(self):
        provider = _make_provider('{"year_min": 2018, "year_max": 2022, "tags": [], "collections": [], "author": null, "title": null, "item_types": []}')
        filters = MetadataExtractor(provider).extract_filters("Papers from 2018 to 2022")
        assert filters["year_min"] == 2018
        assert filters["year_max"] == 2022

    def test_tags_extracted(self):
        provider = _make_provider('{"year_min": null, "year_max": null, "tags": ["transformers", "attention"], "collections": [], "author": null, "title": null, "item_types": []}')
        filters = MetadataExtractor(provider).extract_filters("Papers about transformers")
        assert "transformers" in filters["tags"]
        assert "attention" in filters["tags"]

    def test_collections_extracted(self):
        provider = _make_provider('{"year_min": null, "year_max": null, "tags": [], "collections": ["PhD Research"], "author": null, "title": null, "item_types": []}')
        filters = MetadataExtractor(provider).extract_filters('Papers in "PhD Research" collection')
        assert "PhD Research" in filters["collections"]

    def test_author_extracted(self):
        provider = _make_provider('{"year_min": null, "year_max": null, "tags": [], "collections": [], "author": "Messelaar", "title": null, "item_types": []}')
        filters = MetadataExtractor(provider).extract_filters("What does Sara Messelaar write about?")
        assert filters["author"] == "Messelaar"
        assert filters["has_filters"] is True

    def test_title_extracted(self):
        provider = _make_provider('{"year_min": null, "year_max": null, "tags": [], "collections": [], "author": null, "title": "Sex and the Machine", "item_types": []}')
        filters = MetadataExtractor(provider).extract_filters("Tell me about Sex and the Machine")
        assert filters["title"] == "Sex and the Machine"

    def test_item_types_extracted(self):
        provider = _make_provider('{"year_min": null, "year_max": null, "tags": [], "collections": [], "author": null, "title": null, "item_types": ["thesis"]}')
        filters = MetadataExtractor(provider).extract_filters("What does Messelaar argue in her thesis?")
        assert "thesis" in filters["item_types"]
        assert filters["has_filters"] is True

    def test_author_and_item_type_combined(self):
        provider = _make_provider('{"year_min": null, "year_max": null, "tags": [], "collections": [], "author": "Messelaar", "title": null, "item_types": ["thesis"]}')
        filters = MetadataExtractor(provider).extract_filters("What does Sara Messelaar talk about in her thesis?")
        assert filters["author"] == "Messelaar"
        assert "thesis" in filters["item_types"]

    def test_all_fields_combined(self):
        provider = _make_provider('{"year_min": 2019, "year_max": 2023, "tags": ["deep learning"], "collections": ["Research"], "author": null, "title": null, "item_types": ["journalArticle"]}')
        filters = MetadataExtractor(provider).extract_filters('Journal articles tagged "deep learning" from 2019-2023 in Research collection')
        assert filters["year_min"] == 2019
        assert filters["year_max"] == 2023
        assert "deep learning" in filters["tags"]
        assert "Research" in filters["collections"]
        assert "journalArticle" in filters["item_types"]

    def test_no_filters_query(self):
        provider = _make_provider(_empty_response())
        filters = MetadataExtractor(provider).extract_filters("What is machine learning?")
        assert filters["has_filters"] is False
        assert filters["year_min"] is None
        assert filters["author"] is None
        assert filters["item_types"] == []

    def test_llm_always_called(self):
        """LLM is invoked for every query, simple or complex."""
        provider = _make_provider(_empty_response())
        MetadataExtractor(provider).extract_filters("Papers after 2020")
        provider.chat.assert_called_once()

    def test_json_in_code_block(self):
        """Handles LLM response wrapped in markdown code fences."""
        json_body = '{"year_min": 2021, "year_max": null, "tags": ["NLP"], "collections": [], "author": null, "title": null, "item_types": []}'
        provider = _make_provider(f"```json\n{json_body}\n```")
        filters = MetadataExtractor(provider).extract_filters("NLP papers after 2021")
        assert filters["year_min"] == 2021
        assert "NLP" in filters["tags"]

    def test_llm_exception_returns_empty(self):
        """LLM throwing an exception → empty filters, no crash."""
        provider = Mock()
        provider.chat.side_effect = Exception("connection error")
        filters = MetadataExtractor(provider).extract_filters("Some query")
        assert filters["has_filters"] is False

    def test_invalid_json_returns_empty(self):
        """Unparseable LLM response → empty filters, no crash."""
        provider = _make_provider("Sorry, I cannot help with that.")
        filters = MetadataExtractor(provider).extract_filters("Some query")
        assert filters["has_filters"] is False


# ── TestNoProvider ────────────────────────────────────────────────────────────

class TestNoProvider:
    """Without a provider_manager, regex extraction still works for explicit patterns."""

    def test_no_provider_extracts_via_regex(self):
        # Regex can pull year from explicit patterns even with no LLM configured
        filters = MetadataExtractor(provider_manager=None).extract_filters("Papers after 2020")
        assert filters["year_min"] == 2020
        assert filters["has_filters"] is True
        assert filters["tags"] == []

    def test_no_provider_returns_empty_for_generic_query(self):
        # A query with no explicit metadata patterns yields empty filters
        filters = MetadataExtractor(provider_manager=None).extract_filters("What are the main findings?")
        assert filters["has_filters"] is False
        assert filters["year_min"] is None

    def test_no_provider_all_fields_present(self):
        """Empty result still contains all expected keys."""
        filters = MetadataExtractor(provider_manager=None).extract_filters("anything")
        for key in ("year_min", "year_max", "tags", "collections", "author", "title", "item_types", "has_filters"):
            assert key in filters


# ── TestExtractMetadataFiltersFunction ───────────────────────────────────────

class TestExtractMetadataFiltersFunction:
    """Convenience function mirrors MetadataExtractor behaviour."""

    def test_no_provider_returns_empty_for_generic_query(self):
        # Generic query with no explicit metadata pattern → empty
        filters = extract_metadata_filters("What are the main findings?")
        assert filters["has_filters"] is False

    def test_with_provider_calls_llm(self):
        provider = _make_provider('{"year_min": 2020, "year_max": null, "tags": [], "collections": [], "author": null, "title": null, "item_types": []}')
        filters = extract_metadata_filters("Papers after 2020", provider_manager=provider)
        assert filters["year_min"] == 2020
        assert filters["has_filters"] is True
        provider.chat.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
