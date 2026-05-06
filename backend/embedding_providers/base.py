"""
Abstract base class for cloud embedding providers.

All providers must implement embed_batch(), which is the only method
called by embed_utils.py. The embed_batch interface accepts a list of
strings and returns a list of float vectors, mirroring the SentenceTransformer
.encode() interface so the dispatch layer stays thin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingProviderError(Exception):
    """Base error for embedding provider failures."""


class EmbeddingCredentialError(EmbeddingProviderError):
    """Raised when credentials are missing or invalid."""


class EmbeddingRateLimitError(EmbeddingProviderError):
    """Raised when the provider rate-limits the request."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EmbeddingProvider(ABC):
    """Interface that all cloud embedding backends must implement."""

    #: Provider prefix used in model IDs, e.g. "openai"
    id: str

    @abstractmethod
    def embed_batch(
        self,
        texts: list[str],
        model_name: str,
        credentials: dict[str, Any],
    ) -> list[list[float]]:
        """Embed a batch of texts and return a list of float vectors.

        Args:
            texts: Non-empty list of strings to embed.
            model_name: The bare model name (without provider prefix),
                        e.g. "text-embedding-3-small".
            credentials: Provider-specific credential dict, e.g. {"api_key": "sk-..."}.

        Returns:
            List of float vectors, one per input text, in the same order.

        Raises:
            EmbeddingCredentialError: API key missing or rejected.
            EmbeddingRateLimitError: Rate limit hit.
            EmbeddingProviderError: Any other provider-level failure.
        """

    @abstractmethod
    def get_dimension(self, model_name: str) -> int:
        """Return the vector dimension for the given model name."""
