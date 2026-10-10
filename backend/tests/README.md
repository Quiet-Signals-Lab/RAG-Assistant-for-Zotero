# Metadata Filtering System - Testing Guide

## Overview

This directory contains comprehensive tests for the metadata filtering system. The test suite covers:
- **Unit tests**: Individual components (version detection, extraction, utilities, migration)
- **Integration tests**: Full pipeline workflows from query to filtered results
- **Fixtures**: Shared mocks and test data
- **Real-world scenarios**: Academic research use cases

## Test Files

### Unit Tests

#### `test_metadata_version.py` (229 lines, 27 tests)
Tests for metadata version detection and compatibility checking.

**Classes:**
- `TestMetadataVersionManager`: 18 tests for version detection
  - Empty database handling
  - v1 format detection (string year)
  - v2 format detection (int year + tags/collections)
  - Mixed format detection
  - Migration requirement checks
  - Result caching

- `TestEdgeCases`: 3 tests for error handling
  - Malformed metadata
  - Empty ChromaDB responses
  - ChromaDB errors

**Run:**
```bash
pytest backend/tests/test_metadata_version.py -v
```

#### `test_metadata_extractor.py` (373 lines, 40+ tests)
Tests for metadata extraction from natural language queries.

**Classes:**
- `TestMetadataExtractorRegex`: 25+ tests for regex patterns
  - Year patterns: "after 2020", "before 2018", "from 2015 to 2020"
  - Tag patterns: 'tagged "NLP"', "about transformers"
  - Collection patterns: 'in "Research"', "from PhD collection"
  - Edge cases: multiple quotes, special characters

- `TestMetadataExtractorLLM`: 8 tests for LLM fallback
  - LLM extraction when regex fails
  - JSON parsing from LLM responses
  - Empty/malformed responses
  - Provider errors

- `TestExtractMetadataFiltersFunction`: 2 tests for main function
- `TestRealWorldQueries`: 5 tests with academic queries

**Run:**
```bash
pytest backend/tests/test_metadata_extractor.py -v
```

#### `test_metadata_utils.py` (367 lines, 35+ tests)
Tests for utility functions (where clause building, validation, merging).

**Classes:**
- `TestBuildMetadataWhereClause`: 12 tests for building ChromaDB where clauses
  - Simple conditions (year_min, year_max, single tag)
  - Combined filters (year + tags, year + collections)
  - Multiple tags/collections
  - Empty/None handling

- `TestValidateWhereClause`: 9 tests for validation
  - Valid clauses
  - Invalid operators
  - Type checking
  - Complex nested structures

- `TestMergeWhereClauses`: 5 tests for merging filters
  - Two simple clauses
  - Nested $and clauses
  - None handling

- `TestFormatFiltersForDisplay`: 8 tests for display formatting
- `TestEdgeCases`: 6 tests for edge cases
- `TestRealWorldScenarios`: 4 tests with research scenarios

**Run:**
```bash
pytest backend/tests/test_metadata_utils.py -v
```

#### `test_metadata_migration.py` (347 lines, 25+ tests)
Tests for metadata migration from v1 to v2.

**Classes:**
- `TestMetadataMigration`: 15 tests for migration process
  - Fetch updated metadata from Zotero
  - Update detection (year change, tags added)
  - Batch processing (small/large libraries)
  - Year parsing from various date formats
  - ChromaDB update operations

- `TestMigrationCaching`: 1 test for duplicate fetch prevention
- `TestMigrationSummary`: 2 tests for summary structure
- `TestEdgeCases`: 6 tests for error handling

**Run:**
```bash
pytest backend/tests/test_metadata_migration.py -v
```

#### `test_vector_db.py`
ChromaClient against a real on-disk Chroma + FTS5 index in a temp dir: batch
splitting, id-only inventory, paged filter counts, delete, keyword ranking
(including CJK), index reconciliation (issue #86).

#### `test_indexing_worker.py`
The background indexing worker with Zotero, PDF extraction, embeddings and
Chroma mocked: progress accounting, incremental filtering, full-mode
replacement, cancellation.

#### `test_api.py`
HTTP smoke tests through FastAPI's TestClient with the chatbot mocked: status
codes, error `detail`, guards, PDF path validation, settings masking.

### Integration Tests

#### `test_metadata_integration.py` (450+ lines, 35+ tests)
End-to-end tests for the full metadata filtering pipeline.

**Classes:**
- `TestEndToEndQueryFlow`: Query → Extract → Build Where → Search
- `TestVersionDetectionIntegration`: Version check → Migration workflow
- `TestSearchWorkflow`: Where clause in ChromaDB queries
- `TestRRFIntegration`: Hybrid search with metadata filters
- `TestFullChatPipeline`: Complete chat flow with filters
- `TestAPIEndpointIntegration`: API endpoint testing
- `TestErrorHandlingIntegration`: Error propagation across pipeline
- `TestPerformanceIntegration`: Performance benchmarks
- `TestRealWorldScenarios`: End-to-end research scenarios

**Run:**
```bash
pytest backend/tests/test_metadata_integration.py -v
```

### Shared Fixtures

#### `conftest.py` (400+ lines)
Shared fixtures and utilities for all tests.

**ChromaDB Fixtures:**
- `mock_chroma_empty`: Empty database
- `mock_chroma_v1`: v1 metadata (string year)
- `mock_chroma_v2`: v2 metadata (int year + tags)
- `mock_chroma_mixed`: Mixed v1/v2 data
- `mock_chroma_filterable`: Responds to where clause queries

**Zotero Fixtures:**
- `mock_zotero_library`: Library with sample papers
- `mock_zotero_collection_map`: Collection ID → name mapping

**LLM Fixtures:**
- `mock_llm_provider`: LLM provider for extraction
- `mock_provider_manager`: Provider manager

**Helper Functions:**
- Data generators: `create_metadata_v1()`, `create_metadata_v2()`, `create_zotero_item()`
- Assertions: `assert_metadata_v1_format()`, `assert_valid_where_clause()`
- Mock factories: `create_mock_chroma_with_data()`
- Sample queries: `SAMPLE_QUERIES` dict

## Running Tests

### Run All Tests
```bash
cd /Users/aahepburn/Projects/zotero-rag-assistant
pytest backend/tests/ -v
```

### Run Specific Test File
```bash
pytest backend/tests/test_metadata_version.py -v
```

### Run Specific Test Class
```bash
pytest backend/tests/test_metadata_extractor.py::TestMetadataExtractorRegex -v
```

### Run Specific Test
```bash
pytest backend/tests/test_metadata_utils.py::TestBuildMetadataWhereClause::test_year_min_only -v
```

### Run with Coverage
```bash
pytest backend/tests/ --cov=backend --cov-report=html
open htmlcov/index.html
```

### Run with Markers
```bash
# Run only fast tests (if markers are added)
pytest backend/tests/ -m "not slow"

# Run only integration tests
pytest backend/tests/test_metadata_integration.py -v
```

## Test Coverage

### Current Coverage
- **Total test files**: 6 (5 test files + 1 fixtures file)
- **Total lines of test code**: ~2,100+
- **Total test cases**: ~160+

### Coverage by Module

| Module | Test File | Tests | Coverage |
|--------|-----------|-------|----------|
| `metadata_version.py` | `test_metadata_version.py` | 27 | Version detection, migration checks, caching |
| `metadata_extractor.py` | `test_metadata_extractor.py` | 40+ | Regex patterns, LLM fallback, real queries |
| `metadata_utils.py` | `test_metadata_utils.py` | 35+ | Where clause building, validation, merging |
| `metadata_migration.py` | `test_metadata_migration.py` | 25+ | Batch processing, year parsing, updates |
| Pipeline | `test_metadata_integration.py` | 35+ | End-to-end workflows, API endpoints |

### What's Tested

✅ **Version Detection:**
- Empty database
- v1 format (string year)
- v2 format (int year + tags/collections)
- Mixed formats
- Migration requirement detection

✅ **Metadata Extraction:**
- Year patterns: after, before, from-to, in
- Tag patterns: tagged, about, on
- Collection patterns: in, from
- LLM fallback when regex fails
- Real-world academic queries

✅ **Where Clause Building:**
- Simple conditions (year_min, year_max, tags, collections)
- Combined filters
- Complex nested structures
- Validation and error handling

✅ **Metadata Migration:**
- Fetching metadata from Zotero
- Update detection
- Batch processing
- Year string → int conversion
- Caching to prevent duplicate fetches

✅ **Integration:**
- Full query pipeline
- Version check → migration workflow
- RRF hybrid search with filters
- API endpoints
- Error handling across pipeline

### What Could Be Added

⚠️ **Future Enhancements:**
- Performance benchmarks with large datasets
- Stress testing (10k+ papers)
- Concurrent query testing
- Real Zotero API integration tests
- UI/frontend integration tests
- Trial queries script/notebook

## Writing New Tests

### Example: Adding a Unit Test

```python
# In test_metadata_utils.py

def test_new_feature(self):
    """Test description."""
    # Arrange
    filters = {'year_min': 2020, 'tags': ['NLP']}
    
    # Act
    result = build_metadata_where_clause(**filters)
    
    # Assert
    assert result is not None
    assert 'year' in result
```

### Example: Adding an Integration Test

```python
# In test_metadata_integration.py

def test_new_workflow(self, mock_chroma_v2):
    """Test complete workflow."""
    # Step 1: Extract
    extractor = MetadataExtractor(provider_manager=None)
    filters = extractor.extract_filters("Papers after 2020")
    
    # Step 2: Build where clause
    where = build_metadata_where_clause(year_min=filters['year_min'])
    
    # Step 3: Query with filters
    mock_chroma_v2.collection.query(where=where)
    
    # Assert
    assert mock_chroma_v2.collection.query.called
```

### Example: Using Fixtures

```python
def test_with_fixture(self, mock_chroma_v1, mock_zotero_library):
    """Test using shared fixtures."""
    # Fixtures are automatically injected
    result = check_metadata_compatibility(mock_chroma_v1)
    assert result['version'] == 1
```

## Debugging Tests

### Run with Verbose Output
```bash
pytest backend/tests/test_metadata_version.py -v -s
```

### Run with PDB on Failure
```bash
pytest backend/tests/test_metadata_version.py --pdb
```

### Run Last Failed Tests
```bash
pytest backend/tests/ --lf
```

### Show Print Statements
```bash
pytest backend/tests/ -v -s --capture=no
```

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: |
          pytest backend/tests/ --cov=backend --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Trial Queries

### Running Trial Queries (Future)

Create a trial queries script:

```python
# scripts/run_trial_queries.py
import sys
sys.path.append('backend')

from metadata_extractor import MetadataExtractor
from metadata_utils import build_metadata_where_clause

queries = [
    "Papers after 2020 about transformers",
    "Recent NLP papers in my PhD collection",
    "Survey papers from 2019 to 2023",
]

extractor = MetadataExtractor(provider_manager=None)

for query in queries:
    print(f"\nQuery: {query}")
    filters = extractor.extract_filters(query)
    where = build_metadata_where_clause(**filters)
    print(f"Filters: {filters}")
    print(f"Where: {where}")
```

Run with:
```bash
python scripts/run_trial_queries.py
```

## Test Data

### Sample Metadata (v1)
```python
{
    'item_id': '1',
    'title': 'Attention Is All You Need',
    'year': '2017',  # String
    'authors': 'Vaswani et al.'
}
```

### Sample Metadata (v2)
```python
{
    'item_id': '1',
    'title': 'Attention Is All You Need',
    'year': 2017,  # Integer
    'authors': 'Vaswani et al.',
    'tags': 'NLP|Transformers|Deep Learning',
    'collections': 'Research|Important Papers'
}
```

### Sample Where Clause
```python
{
    "$and": [
        {"year": {"$gte": 2020}},
        {"year": {"$lte": 2023}},
        {"tags": {"$contains": "NLP"}},
        {"collections": {"$contains": "Research"}}
    ]
}
```

## Troubleshooting

### Import Errors
```bash
# Ensure backend is in PYTHONPATH
export PYTHONPATH=/Users/aahepburn/Projects/zotero-rag-assistant:$PYTHONPATH
pytest backend/tests/ -v
```

### Fixture Not Found
- Ensure `conftest.py` is in the tests directory
- Check fixture name matches usage
- pytest auto-discovers `conftest.py`

### Mock Not Working
- Ensure using `unittest.mock.patch` correctly
- Check mock target path (use where it's imported, not defined)
- Use `return_value` for simple values, `side_effect` for functions

### Test Isolation
- Each test should be independent
- Use fixtures to create fresh mocks
- Avoid global state

## Best Practices

1. **Test Naming**: Use descriptive names (`test_year_min_creates_gte_filter`)
2. **Arrange-Act-Assert**: Structure tests clearly
3. **One Assertion per Test**: Focus on single behavior (when practical)
4. **Use Fixtures**: Share setup code via fixtures
5. **Mock External Dependencies**: Avoid real API calls in tests
6. **Test Edge Cases**: Empty strings, None values, invalid input
7. **Document Complex Tests**: Add docstrings explaining what's tested

## Performance Benchmarks

### Expected Test Performance
- **Unit tests**: < 5ms per test
- **Integration tests**: < 50ms per test
- **Full suite**: < 5 seconds

### Current Performance (as of creation)
```bash
# Run with timing
pytest backend/tests/ -v --durations=10
```

## Contact & Support

For questions about tests:
1. Review this README
2. Check existing test examples
3. Review `conftest.py` for available fixtures
4. Run tests with `-v -s` for debugging

## License

Same as parent project (see root LICENSE file).
