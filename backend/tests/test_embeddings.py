"""
Test script to verify embedding dimension consistency.
Run this to ensure the database and embedding model are properly configured.

Usage:
    python -m backend.tests.test_embeddings
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.embed_utils import get_embedding, get_current_model_id, get_embedding_dimension
from backend.vector_db import ChromaClient
import tempfile
import shutil


def test_embedding_dimension():
    """Test that embeddings have the correct dimension."""
    model_id = get_current_model_id()
    expected_dim = get_embedding_dimension()
    print(f"Testing embedding model: {model_id}")
    print(f"Expected dimension: {expected_dim}")
    
    # Test with sample text
    test_text = "This is a test document about machine learning and artificial intelligence."
    embedding = get_embedding(test_text)
    
    print(f"Actual dimension: {len(embedding)}")
    
    assert len(embedding) == expected_dim, \
        f"Dimension mismatch! Expected {expected_dim}, got {len(embedding)}"
    
    print("✓ Embedding dimension is correct")


def test_chromadb_consistency():
    """Test that ChromaDB queries work with manual embeddings."""
    print("\nTesting ChromaDB integration...")
    
    # Create temporary database
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Initialize ChromaClient
        client = ChromaClient(db_path=temp_dir, collection_name="test_collection")
        
        # Add sample documents with manual embeddings
        docs = [
            "Machine learning is a subset of artificial intelligence.",
            "Deep learning uses neural networks with multiple layers.",
            "Natural language processing enables computers to understand text."
        ]
        
        embeddings = [get_embedding(doc) for doc in docs]
        ids = [f"doc_{i}" for i in range(len(docs))]
        metadatas = [{"index": i} for i in range(len(docs))]
        
        print(f"Adding {len(docs)} documents with {len(embeddings[0])}-dimensional embeddings...")
        client.add_chunks(
            ids=ids,
            documents=docs,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        # Test querying
        query = "What is deep learning?"
        print(f"Querying: '{query}'")
        
        results = client.query_hybrid_rrf(query=query, k=2, embedding_model_id=get_current_model_id())
        
        assert results is not None, "Query returned None"
        assert 'documents' in results, "Query missing 'documents' key"
        assert len(results['documents'][0]) > 0, "Query returned no results"
        
        print(f"✓ Query returned {len(results['documents'][0])} results")
        print(f"  Top result: {results['documents'][0][0][:80]}...")
        
        # Validate dimensions
        validation = client.validate_embedding_dimension()
        print(f"✓ Database validation: {validation['status']}")
        print(f"  Expected dimension: {validation['expected_dimension']}")
        print(f"  Actual dimension: {validation['actual_dimension']}")
        
        assert validation['status'] == 'ok', f"Validation failed: {validation}"
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("✓ Temporary database cleaned up")


def test_query_methods():
    """Test that all query methods use manual embeddings."""
    print("\nTesting query method implementations...")
    
    import inspect
    from backend.vector_db import ChromaClient
    
    # Check query_hybrid_rrf source
    rrf_source = inspect.getsource(ChromaClient.query_hybrid_rrf)
    assert 'query_embeddings' in rrf_source, \
        "query_hybrid_rrf should use query_embeddings, not query_texts!"
    assert 'query_texts' not in rrf_source or 'not query_texts' in rrf_source, \
        "query_hybrid_rrf should NOT use query_texts parameter!"
    print("✓ query_hybrid_rrf uses manual embeddings")
    


def test_local_embeddings_take_the_lock_one_batch_at_a_time(monkeypatch):
    import numpy as np
    """A whole book under one lock made a search wait ~17 s for its query embedding."""
    from backend import embed_utils
    calls = []

    class FakeModel:
        def encode(self, texts):
            assert embed_utils._inference_lock.locked()
            calls.append(len(texts))
            return np.zeros((len(texts), 384), dtype=np.float32)

    monkeypatch.setattr(embed_utils, "load_embedding_model", lambda mid=None: FakeModel())
    monkeypatch.setattr(embed_utils, "_touch", lambda: None)
    out = embed_utils.get_embeddings_batch(["t"] * 70, "minilm-l3")
    assert len(out) == 70 and calls == [32, 32, 6]


def test_unload_models_drops_every_loaded_model(monkeypatch):
    from backend import embed_utils
    monkeypatch.setattr(embed_utils, "_current_model", object())
    monkeypatch.setattr(embed_utils, "_reranker", object())
    monkeypatch.setattr(embed_utils, "_nli", object())
    embed_utils.unload_models()
    assert embed_utils._current_model is embed_utils._reranker is embed_utils._nli is None


def main():
    """Run all tests."""
    print("=" * 70)
    print("EMBEDDING CONSISTENCY TEST SUITE")
    print("=" * 70)
    
    try:
        test_embedding_dimension()
        test_query_methods()
        test_chromadb_consistency()
        
        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED")
        print("=" * 70)
        print("\nYour embedding configuration is correct!")
        print(f"Model: {get_current_model_id()}")
        print(f"Dimension: {get_embedding_dimension()}")
        print("\nYou can now safely re-index your library.")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


def test_release_memory_is_safe_to_call_anywhere(monkeypatch):
    from backend import embed_utils
    embed_utils.release_memory()
    monkeypatch.setattr(embed_utils.sys, "platform", "win32")
    embed_utils.release_memory()
