"""
Unit tests for metadata utilities.
Tests functions from metadata_utils.py
"""

import pytest
from backend.metadata_utils import (
    build_metadata_where_clause,
    validate_where_clause,
    merge_where_clauses,
    format_filters_for_display,
    separate_where_clauses,
    _matches_where_clause,
)


class TestBuildMetadataWhereClause:
    """Test where clause construction."""
    
    def test_year_min_only(self):
        """Test year minimum filter."""
        where = build_metadata_where_clause(year_min=2020)
        
        assert where == {"year": {"$gte": 2020}}
    
    def test_year_max_only(self):
        """Test year maximum filter."""
        where = build_metadata_where_clause(year_max=2023)
        
        assert where == {"year": {"$lte": 2023}}
    
    def test_year_range(self):
        """Test year range filter."""
        where = build_metadata_where_clause(year_min=2018, year_max=2022)
        
        assert where == {
            "$and": [
                {"year": {"$gte": 2018}},
                {"year": {"$lte": 2022}}
            ]
        }
    
    def test_single_tag(self):
        """Test single tag filter."""
        where = build_metadata_where_clause(tags=["NLP"])
        
        assert where == {"tags": {"$contains_item": "NLP"}}
    
    def test_multiple_tags(self):
        """Test multiple tags filter (OR logic)."""
        where = build_metadata_where_clause(tags=["NLP", "ML", "CV"])
        
        assert where == {
            "$or": [
                {"tags": {"$contains_item": "NLP"}},
                {"tags": {"$contains_item": "ML"}},
                {"tags": {"$contains_item": "CV"}}
            ]
        }
    
    def test_single_collection(self):
        """Test single collection filter."""
        where = build_metadata_where_clause(collections=["Research"])
        
        assert where == {"collections": {"$contains_item": "Research"}}
    
    def test_multiple_collections(self):
        """Test multiple collections filter (OR logic)."""
        where = build_metadata_where_clause(collections=["Research", "Papers"])
        
        assert where == {
            "$or": [
                {"collections": {"$contains_item": "Research"}},
                {"collections": {"$contains_item": "Papers"}}
            ]
        }
    
    def test_combined_year_and_tags(self):
        """Test combined year and tags filter."""
        where = build_metadata_where_clause(
            year_min=2020,
            tags=["NLP", "ML"]
        )
        
        assert where == {
            "$and": [
                {"year": {"$gte": 2020}},
                {"$or": [
                    {"tags": {"$contains_item": "NLP"}},
                    {"tags": {"$contains_item": "ML"}}
                ]}
            ]
        }
    
    def test_combined_all_filters(self):
        """Test all filters combined."""
        where = build_metadata_where_clause(
            year_min=2018,
            year_max=2022,
            tags=["Transformers"],
            collections=["PhD Research"]
        )
        
        expected = {
            "$and": [
                {"year": {"$gte": 2018}},
                {"year": {"$lte": 2022}},
                {"tags": {"$contains_item": "Transformers"}},
                {"collections": {"$contains_item": "PhD Research"}}
            ]
        }
        
        assert where == expected
    
    def test_no_filters(self):
        """Test with no filters."""
        where = build_metadata_where_clause()
        
        assert where is None
    
    def test_empty_lists(self):
        """Test with empty lists."""
        where = build_metadata_where_clause(tags=[], collections=[])
        
        assert where is None


class TestValidateWhereClause:
    """Test where clause validation."""
    
    def test_validate_none(self):
        """Test validation of None."""
        assert validate_where_clause(None) == True
    
    def test_validate_simple_condition(self):
        """Test validation of simple condition."""
        where = {"year": {"$gte": 2020}}
        assert validate_where_clause(where) == True
    
    def test_validate_and_condition(self):
        """Test validation of AND condition."""
        where = {
            "$and": [
                {"year": {"$gte": 2020}},
                {"tags": {"$contains_item": "NLP"}}
            ]
        }
        assert validate_where_clause(where) == True
    
    def test_validate_or_condition(self):
        """Test validation of OR condition."""
        where = {
            "$or": [
                {"tags": {"$contains_item": "NLP"}},
                {"tags": {"$contains_item": "ML"}}
            ]
        }
        assert validate_where_clause(where) == True
    
    def test_validate_nested_conditions(self):
        """Test validation of nested conditions."""
        where = {
            "$and": [
                {"year": {"$gte": 2020}},
                {
                    "$or": [
                        {"tags": {"$contains_item": "NLP"}},
                        {"tags": {"$contains_item": "ML"}}
                    ]
                }
            ]
        }
        assert validate_where_clause(where) == True
    
    def test_validate_invalid_type(self):
        """Test validation of invalid type."""
        assert validate_where_clause("not a dict") == False
        assert validate_where_clause(123) == False
    
    def test_validate_invalid_logical_op(self):
        """Test validation of invalid logical operator value."""
        where = {"$and": "not a list"}
        assert validate_where_clause(where) == False
    
    def test_validate_all_operators(self):
        """Test validation with all comparison operators."""
        where = {
            "$and": [
                {"field1": {"$eq": 1}},
                {"field2": {"$ne": 2}},
                {"field3": {"$gt": 3}},
                {"field4": {"$gte": 4}},
                {"field5": {"$lt": 5}},
                {"field6": {"$lte": 6}},
                {"field7": {"$contains": "test"}},
                {"field8": {"$in": [1, 2, 3]}},
                {"field9": {"$nin": [4, 5, 6]}}
            ]
        }
        assert validate_where_clause(where) == True


class TestMergeWhereClauses:
    """Test where clause merging."""
    
    def test_merge_both_none(self):
        """Test merging two None clauses."""
        result = merge_where_clauses(None, None)
        assert result is None
    
    def test_merge_first_none(self):
        """Test merging with first clause None."""
        clause2 = {"year": {"$gte": 2020}}
        result = merge_where_clauses(None, clause2)
        assert result == clause2
    
    def test_merge_second_none(self):
        """Test merging with second clause None."""
        clause1 = {"year": {"$gte": 2020}}
        result = merge_where_clauses(clause1, None)
        assert result == clause1
    
    def test_merge_two_simple(self):
        """Test merging two simple clauses."""
        clause1 = {"year": {"$gte": 2020}}
        clause2 = {"tags": {"$contains_item": "NLP"}}
        result = merge_where_clauses(clause1, clause2)
        
        expected = {
            "$and": [
                {"year": {"$gte": 2020}},
                {"tags": {"$contains_item": "NLP"}}
            ]
        }
        assert result == expected
    
    def test_merge_complex_clauses(self):
        """Test merging complex clauses."""
        clause1 = {
            "$and": [
                {"year": {"$gte": 2018}},
                {"year": {"$lte": 2022}}
            ]
        }
        clause2 = {
            "$or": [
                {"tags": {"$contains_item": "NLP"}},
                {"tags": {"$contains_item": "ML"}}
            ]
        }
        result = merge_where_clauses(clause1, clause2)
        
        expected = {
            "$and": [clause1, clause2]
        }
        assert result == expected


class TestFormatFiltersForDisplay:
    """Test filter display formatting."""
    
    def test_format_year_range(self):
        """Test formatting year range."""
        display = format_filters_for_display(year_min=2018, year_max=2022)
        assert display == "Year: 2018-2022"
    
    def test_format_year_single(self):
        """Test formatting single year."""
        display = format_filters_for_display(year_min=2020, year_max=2020)
        assert display == "Year: 2020"
    
    def test_format_year_min_only(self):
        """Test formatting year minimum only."""
        display = format_filters_for_display(year_min=2020)
        assert display == "Year: 2020+"
    
    def test_format_year_max_only(self):
        """Test formatting year maximum only."""
        display = format_filters_for_display(year_max=2023)
        assert display == "Year: ≤2023"
    
    def test_format_tags(self):
        """Test formatting tags."""
        display = format_filters_for_display(tags=["NLP", "ML", "CV"])
        assert display == "Tags: NLP, ML, CV"
    
    def test_format_collections(self):
        """Test formatting collections."""
        display = format_filters_for_display(collections=["Research", "Papers"])
        assert display == "Collections: Research, Papers"
    
    def test_format_combined(self):
        """Test formatting combined filters."""
        display = format_filters_for_display(
            year_min=2018,
            year_max=2022,
            tags=["NLP"],
            collections=["Research"]
        )
        
        assert "Year: 2018-2022" in display
        assert "Tags: NLP" in display
        assert "Collections: Research" in display
        assert " | " in display  # Parts separated by pipe
    
    def test_format_no_filters(self):
        """Test formatting with no filters."""
        display = format_filters_for_display()
        assert display == "No filters"
    
    def test_format_empty_lists(self):
        """Test formatting with empty lists."""
        display = format_filters_for_display(tags=[], collections=[])
        assert display == "No filters"


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_where_clause_with_special_characters(self):
        """Test where clause with special characters in strings."""
        where = build_metadata_where_clause(
            tags=["C++", "C#", ".NET"],
            collections=["Papers (2020-2023)"]
        )
        
        # Should handle special characters
        assert where is not None
        assert validate_where_clause(where)
    
    def test_where_clause_with_unicode(self):
        """Test where clause with unicode characters."""
        where = build_metadata_where_clause(
            tags=["深度学习", "機械学習"]
        )
        
        assert where is not None
        assert validate_where_clause(where)
    
    def test_year_boundary_values(self):
        """Test year boundary values."""
        where = build_metadata_where_clause(year_min=1900, year_max=2100)
        
        assert where == {
            "$and": [
                {"year": {"$gte": 1900}},
                {"year": {"$lte": 2100}}
            ]
        }
    
    def test_single_item_lists(self):
        """Test single-item lists don't create unnecessary OR."""
        where = build_metadata_where_clause(tags=["NLP"])
        
        # Should be simple, not wrapped in $or
        assert where == {"tags": {"$contains_item": "NLP"}}
        assert "$or" not in where
    
    def test_large_tag_list(self):
        """Test handling of large tag list."""
        tags = [f"tag{i}" for i in range(100)]
        where = build_metadata_where_clause(tags=tags)
        
        assert where is not None
        assert "$or" in where
        assert len(where["$or"]) == 100
    
    def test_validation_deeply_nested(self):
        """Test validation of deeply nested conditions."""
        where = {
            "$and": [
                {
                    "$or": [
                        {
                            "$and": [
                                {"field1": {"$gte": 1}},
                                {"field2": {"$lte": 2}}
                            ]
                        },
                        {"field3": {"$eq": 3}}
                    ]
                },
                {"field4": {"$contains": "test"}}
            ]
        }
        assert validate_where_clause(where) == True


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""
    
    def test_scenario_phd_research(self):
        """Scenario: PhD student researching NLP papers from last 5 years."""
        where = build_metadata_where_clause(
            year_min=2019,
            tags=["NLP", "Natural Language Processing", "Transformers"],
            collections=["PhD Research", "Literature Review"]
        )
        
        assert where is not None
        assert validate_where_clause(where)
        
        display = format_filters_for_display(
            year_min=2019,
            tags=["NLP", "Natural Language Processing", "Transformers"],
            collections=["PhD Research", "Literature Review"]
        )
        assert "2019+" in display
    
    def test_scenario_survey_paper(self):
        """Scenario: Writing survey paper on recent CV advances."""
        where = build_metadata_where_clause(
            year_min=2020,
            year_max=2024,
            tags=["Computer Vision", "Deep Learning"],
            collections=["Survey Papers"]
        )
        
        assert where is not None
        assert validate_where_clause(where)
    
    def test_scenario_historical_analysis(self):
        """Scenario: Analyzing historical papers before deep learning era."""
        where = build_metadata_where_clause(
            year_max=2012,
            tags=["Machine Learning", "Neural Networks"]
        )
        
        assert where is not None
        display = format_filters_for_display(
            year_max=2012,
            tags=["Machine Learning", "Neural Networks"]
        )
        assert "≤2012" in display
    
    def test_scenario_merge_user_and_auto_filters(self):
        """Scenario: Merge user-specified and auto-extracted filters."""
        # User manually set collections
        user_where = build_metadata_where_clause(
            collections=["Research Papers"]
        )
        
        # Auto-extracted from query
        auto_where = build_metadata_where_clause(
            year_min=2020,
            tags=["Transformers"]
        )
        
        # Merge both
        merged = merge_where_clauses(user_where, auto_where)
        
        assert merged is not None
        assert validate_where_clause(merged)
        assert "$and" in merged


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestScopeFiltering:
    """Regression tests for issue #75 (Scope collection/tag filtering)."""

    METAS = [
        {"item_id": "1", "tags": "Religion,Sociology", "collections": "Faith Studies"},
        {"item_id": "2", "tags": "unique-tag", "collections": "Faith Studies,Religion and Society"},
        {"item_id": "3", "tags": "", "collections": "Other"},
        {"item_id": "4", "collections": "Faith"},  # no tags key at all
    ]

    def _matching(self, **filters):
        where = build_metadata_where_clause(**filters)
        _, client_where = separate_where_clauses(where)
        assert client_where is not None, "tag/collection filters must reach client-side matching"
        return {m["item_id"] for m in self.METAS if _matches_where_clause(m, client_where)}

    def test_collection_matches_whole_entry_not_substring(self):
        # "Faith" must not select items whose only collection is "Faith Studies"
        assert self._matching(collections=["Faith"]) == {"4"}
        assert self._matching(collections=["Faith Studies"]) == {"1", "2"}

    def test_tag_matching_is_case_insensitive(self):
        assert self._matching(tags=["religion"]) == {"1"}
        assert self._matching(tags=["Religion"]) == {"1"}

    def test_tag_matches_one_entry_of_a_joined_list(self):
        assert self._matching(tags=["Sociology"]) == {"1"}
        assert self._matching(tags=["unique-tag"]) == {"2"}

    def test_missing_or_empty_field_never_matches(self):
        assert self._matching(tags=["anything"]) == set()

    def test_vector_db_matcher_agrees(self):
        """ChromaClient kept its own case-sensitive copy that returned 0 items
        for a tag the UI matched fine — it must delegate here now."""
        import inspect
        from backend import vector_db
        src = inspect.getsource(vector_db.ChromaClient._matches_where_clause)
        assert "from backend.metadata_utils import _matches_where_clause" in src
