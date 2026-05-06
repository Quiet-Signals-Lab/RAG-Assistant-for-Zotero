"""
OpenAI cloud embedding backend.

Uses the openai SDK (already a project dependency via model_providers/openai.py).
Implements batched embedding with exponential-backoff retry on rate limits.

Max batch size per OpenAI docs: 2048 inputs per request.
"""

from __future__ import annotations

import logging
import time
import random
from typing import Any

from .base import (
    EmbeddingProvider,
    EmbeddingCredentialError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
)

logger = logging.getLogger(__name__)

# Dimension table for all OpenAI embedding models.
# Update this dict when OpenAI releases new models.
_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,   # legacy, kept for completeness
}

# OpenAI allows up to 2048 inputs per embedding request.
_MAX_BATCH_SIZE = 2048

# Retry configuration for rate-limit errors.
_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0   # seconds
_BACKOFF_JITTER = 1.0 # seconds of random jitter added to each wait


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by the OpenAI Embeddings API."""

    id = "openai"

    def get_dimension(self, model_name: str) -> int:
        if model_name not in _DIMENSIONS:
            raise EmbeddingProviderError(
                f"Unknown OpenAI embedding model '{model_name}'. "
                f"Known models: {list(_DIMENSIONS.keys())}"
            )
        return _DIMENSIONS[model_name]

    def embed_batch(
        self,
        texts: list[str],
        model_name: str,
        credentials: dict[str, Any],
    ) -> list[list[float]]:
        """Embed texts using the OpenAI Embeddings API.

        Splits large batches into sub-batches of up to _MAX_BATCH_SIZE and
        retries on rate-limit errors with exponential back-off.
        """
        api_key = credentials.get("api_key", "").strip()
        if not api_key:
            raise EmbeddingCredentialError(
                "OpenAI API key is required for cloud embeddings. "
                "Configure it in Settings → Providers → OpenAI."
            )

        try:
            from openai import OpenAI, RateLimitError, AuthenticationError
        except ImportError:
            raise EmbeddingProviderError(
                "openai package is not installed. Run: pip install openai"
            )

        base_url = credentials.get("base_url", "").strip() or None
        client = OpenAI(api_key=api_key, base_url=base_url)

        all_vectors: list[list[float]] = []

        # Process in sub-batches
        for batch_start in range(0, len(texts), _MAX_BATCH_SIZE):
            sub_batch = texts[batch_start : batch_start + _MAX_BATCH_SIZE]
            vectors = self._embed_with_retry(
                client=client,
                texts=sub_batch,
                model_name=model_name,
            )
            all_vectors.extend(vectors)

        return all_vectors

    def _embed_with_retry(
        self,
        client: Any,
        texts: list[str],
        model_name: str,
    ) -> list[list[float]]:
        """Call the API with exponential-backoff retry on rate limits."""
        try:
            from openai import RateLimitError, AuthenticationError
        except ImportError:
            raise EmbeddingProviderError("openai package is not installed. Run: pip install openai")

        for attempt in range(_MAX_RETRIES):
            try:
                response = client.embeddings.create(
                    input=texts,
                    model=model_name,
                )
                # OpenAI returns embeddings in the same order as input
                return [item.embedding for item in response.data]

            except AuthenticationError as exc:
                raise EmbeddingCredentialError(
                    f"OpenAI rejected the API key: {exc}"
                ) from exc

            except RateLimitError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise EmbeddingRateLimitError(
                        f"OpenAI rate limit exceeded after {_MAX_RETRIES} retries: {exc}"
                    ) from exc

                wait = (_BACKOFF_BASE ** attempt) + random.uniform(0, _BACKOFF_JITTER)
                logger.warning(
                    "[OpenAI Embeddings] Rate limited. Retrying in %.1fs "
                    "(attempt %d/%d)...",
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(wait)

            except Exception as exc:
                raise EmbeddingProviderError(
                    f"OpenAI embedding request failed: {exc}"
                ) from exc

        # Should be unreachable
        raise EmbeddingProviderError("Embedding failed after all retries.")
