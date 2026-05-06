"""
Embedding provider registry for cloud and local embedding backends.

Cloud providers use the model ID prefix convention: "openai:model-name".
Local (SentenceTransformers) models use unprefixed IDs: "bge-base", etc.

Usage:
    from backend.embedding_providers import get_embedding_provider, CLOUD_EMBEDDING_MODELS

    provider = get_embedding_provider("openai")
    vectors = provider.embed_batch(texts, credentials={"api_key": "..."})
"""

from .base import EmbeddingProvider, EmbeddingProviderError, EmbeddingCredentialError
from .openai import OpenAIEmbeddingProvider

# Registry of cloud embedding providers keyed by provider prefix
_PROVIDERS: dict[str, EmbeddingProvider] = {
    "openai": OpenAIEmbeddingProvider(),
}

# Catalogue of cloud embedding models surfaced to the UI.
# model_id must follow the "<provider_prefix>:<model_name>" convention.
CLOUD_EMBEDDING_MODELS: dict[str, dict] = {
    "openai:text-embedding-3-small": {
        "provider": "openai",
        "name": "text-embedding-3-small",
        "dimension": 1536,
        "description": "OpenAI — fast and affordable (1536 dim)",
        "cloud": True,
        "requires_provider": "openai",   # must have OpenAI credentials saved
    },
    "openai:text-embedding-3-large": {
        "provider": "openai",
        "name": "text-embedding-3-large",
        "dimension": 3072,
        "description": "OpenAI — highest accuracy (3072 dim)",
        "cloud": True,
        "requires_provider": "openai",
    },
}


def get_embedding_provider(provider_prefix: str) -> EmbeddingProvider:
    """Return the EmbeddingProvider for the given prefix (e.g. 'openai').

    Raises KeyError if the prefix is not registered.
    """
    if provider_prefix not in _PROVIDERS:
        raise KeyError(
            f"Unknown embedding provider '{provider_prefix}'. "
            f"Available: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider_prefix]


def is_cloud_model(model_id: str) -> bool:
    """Return True if model_id refers to a cloud embedding model."""
    return model_id in CLOUD_EMBEDDING_MODELS


def parse_cloud_model_id(model_id: str) -> tuple[str, str]:
    """Split 'openai:text-embedding-3-small' into ('openai', 'text-embedding-3-small').

    Raises ValueError if the model_id is not a valid cloud model ID.
    """
    if ":" not in model_id:
        raise ValueError(f"Not a cloud model ID: '{model_id}'")
    provider_prefix, model_name = model_id.split(":", 1)
    return provider_prefix, model_name


__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingCredentialError",
    "OpenAIEmbeddingProvider",
    "CLOUD_EMBEDDING_MODELS",
    "get_embedding_provider",
    "is_cloud_model",
    "parse_cloud_model_id",
]
