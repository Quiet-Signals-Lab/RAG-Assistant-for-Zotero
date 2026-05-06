# embed_utils.py

from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np
import os
import threading
from typing import Optional
from pathlib import Path

# Set persistent cache directory for sentence-transformers models
# This prevents re-downloading models on every startup
MODELS_CACHE_DIR = os.path.expanduser("~/.cache/sentence_transformers")
Path(MODELS_CACHE_DIR).mkdir(parents=True, exist_ok=True)
os.environ['SENTENCE_TRANSFORMERS_HOME'] = MODELS_CACHE_DIR

# Available local embedding models with different speed/quality tradeoffs
EMBEDDING_MODELS = {
    'bge-base': {
        'name': 'BAAI/bge-base-en-v1.5',
        'dimension': 768,
        'description': 'High quality, state-of-the-art (768 dim, ~400MB)',
        'speed': 'medium',
        'quality': 'excellent',
        'cloud': False,
    },
    'specter': {
        'name': 'allenai/specter',
        'dimension': 768,
        'description': 'Optimized for scientific documents (768 dim, ~440MB)',
        'speed': 'medium',
        'quality': 'excellent-scientific',
        'cloud': False,
    },
    'minilm-l6': {
        'name': 'all-MiniLM-L6-v2',
        'dimension': 384,
        'description': 'Balanced quality and speed (384 dim, ~90MB)',
        'speed': 'fast',
        'quality': 'good',
        'cloud': False,
    },
    'minilm-l3': {
        'name': 'paraphrase-MiniLM-L3-v2',
        'dimension': 384,
        'description': 'Fastest, lowest memory (384 dim, ~60MB)',
        'speed': 'fastest',
        'quality': 'moderate',
        'cloud': False,
    },
}

# Default model configuration
DEFAULT_MODEL_ID = 'bge-base'
_current_model_id = DEFAULT_MODEL_ID
_current_model: Optional[SentenceTransformer] = None

# ---------------------------------------------------------------------------
# Cloud credential store
# ---------------------------------------------------------------------------
# Populated at chatbot initialisation time via set_embedding_credentials().
# Keyed by provider prefix (e.g. "openai").  Thread-safe via _creds_lock.
_embedding_credentials: dict[str, dict] = {}
_creds_lock = threading.Lock()


def set_embedding_credentials(provider: str, credentials: dict) -> None:
    """Store API credentials for a cloud embedding provider.

    Must be called before any cloud embedding request.  Typically invoked by
    main.py / ZoteroChatbot at startup.
    """
    with _creds_lock:
        _embedding_credentials[provider] = dict(credentials)


def _get_embedding_credentials(provider: str) -> dict:
    with _creds_lock:
        return dict(_embedding_credentials.get(provider, {}))


def get_model_config(model_id: Optional[str] = None) -> dict:
    """Get configuration for a specific embedding model (local or cloud)."""
    from backend.embedding_providers import CLOUD_EMBEDDING_MODELS
    mid = model_id or _current_model_id
    if mid in EMBEDDING_MODELS:
        return EMBEDDING_MODELS[mid]
    if mid in CLOUD_EMBEDDING_MODELS:
        return CLOUD_EMBEDDING_MODELS[mid]
    raise ValueError(
        f"Unknown embedding model: '{mid}'. "
        f"Local: {list(EMBEDDING_MODELS.keys())}. "
        f"Cloud: {list(CLOUD_EMBEDDING_MODELS.keys())}."
    )

def get_current_model_id() -> str:
    """Get the currently active model ID."""
    return _current_model_id

def get_embedding_dimension(model_id: Optional[str] = None) -> int:
    """Get the embedding dimension for a specific model (local or cloud)."""
    return get_model_config(model_id)['dimension']

def load_embedding_model(model_id: Optional[str] = None) -> SentenceTransformer:
    """Load the local SentenceTransformer model, reusing cached instance if same model."""
    global _current_model, _current_model_id

    target_model_id = model_id or DEFAULT_MODEL_ID

    # Return cached model if already loaded and same
    if _current_model is not None and _current_model_id == target_model_id:
        return _current_model

    # Load new model with explicit cache directory
    config = get_model_config(target_model_id)
    print(f"Loading embedding model: {config['name']} ({config['description']})")
    _current_model = SentenceTransformer(config['name'], cache_folder=MODELS_CACHE_DIR)
    _current_model_id = target_model_id

    return _current_model

# Cross-encoder for re-ranking retrieved passages
# This is much more accurate than cosine similarity for relevance scoring
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', cache_folder=MODELS_CACHE_DIR)


def get_embeddings_batch(texts: list[str], model_id: Optional[str] = None) -> list[np.ndarray]:
    """Embed a batch of texts, dispatching to cloud or local backend.

    Preferred over calling get_embedding() in a loop because:
    - For local models: a single model.encode() call is faster.
    - For cloud models: inputs are sent in one (or few) API request(s),
      reducing round-trips and staying within rate-limit headroom.

    Args:
        texts: Non-empty list of strings to embed.
        model_id: Embedding model ID (local or cloud). Defaults to current.

    Returns:
        List of numpy float32 arrays, one per input text.
    """
    from backend.embedding_providers import (
        is_cloud_model,
        get_embedding_provider,
        parse_cloud_model_id,
        CLOUD_EMBEDDING_MODELS,
    )
    from backend.embedding_providers.base import EmbeddingCredentialError

    if not texts:
        return []

    mid = model_id or _current_model_id
    max_chars = 512 * 4  # rough char ceiling matching per-text truncation

    if is_cloud_model(mid):
        provider_prefix, model_name = parse_cloud_model_id(mid)
        credentials = _get_embedding_credentials(provider_prefix)
        if not credentials.get('api_key'):
            raise EmbeddingCredentialError(
                f"No API key found for '{provider_prefix}'. "
                "Configure it in Settings → Providers."
            )
        provider = get_embedding_provider(provider_prefix)
        truncated = [t[:max_chars] for t in texts]
        vectors = provider.embed_batch(truncated, model_name, credentials)
        return [np.array(v, dtype=np.float32) for v in vectors]

    # Local SentenceTransformer path
    model = load_embedding_model(mid)
    config = get_model_config(mid)
    expected_dim = config['dimension']
    truncated = [t[:max_chars] for t in texts]
    embeddings = model.encode(truncated)

    # Validate the first embedding to catch model misconfigurations early
    if len(embeddings) > 0 and len(embeddings[0]) != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch! Expected {expected_dim}, got {len(embeddings[0])}. "
            f"Model: {config['name']}"
        )

    return [np.array(e, dtype=np.float32) for e in embeddings]


def get_embedding(text: str, model_id: Optional[str] = None) -> np.ndarray:
    """Generate an embedding for a single text (local or cloud).

    Thin wrapper around get_embeddings_batch() for single-text call sites
    (query time, etc.).  For indexing many chunks, prefer get_embeddings_batch().

    Args:
        text: Text to embed.
        model_id: Optional model ID to use (defaults to current model).

    Returns:
        numpy.ndarray: Embedding vector (dimension depends on model).
    """
    results = get_embeddings_batch([text], model_id)
    return results[0]

def rerank_passages(query: str, passages: list[str], top_k: Optional[int] = None) -> list[tuple[int, float]]:
    """Re-rank passages using cross-encoder for better relevance scoring.
    
    Args:
        query: The user's query
        passages: List of text passages to rank
        top_k: Optional limit on number of results to return
    
    Returns:
        List of (index, score) tuples sorted by relevance score (descending)
    """
    if not passages:
        return []
    
    # Create query-passage pairs for the cross-encoder
    pairs = [[query, passage] for passage in passages]
    
    # Get relevance scores
    scores = reranker.predict(pairs)
    
    # Sort by score (descending) and return indices with scores
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    
    if top_k:
        ranked = ranked[:top_k]
    
    return ranked
