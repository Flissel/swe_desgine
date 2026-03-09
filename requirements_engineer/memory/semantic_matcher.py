"""Semantic Matcher — in-memory vector index for artifact matching.

Uses OpenAI text-embedding-3-small via REST API with numpy cosine similarity.
Falls back gracefully when no API key is available.

Pattern adapted from external/arch_team/backend/core/embeddings.py.
"""

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional deps — graceful degradation
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536
DEFAULT_BATCH_SIZE = 64
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.5  # seconds


class SemanticMatcher:
    """In-memory semantic matching using OpenAI embeddings + numpy cosine similarity.

    Usage:
        matcher = SemanticMatcher(api_key="sk-...")
        if matcher.available:
            await matcher.build_index([("REQ-001", "User registration"), ...])
            results = await matcher.find_similar("login authentication", top_k=3)
            # results = [("REQ-001", 0.87), ("REQ-005", 0.72), ...]
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.batch_size = max(1, batch_size)

        # Embedding cache: text_hash -> vector
        self._cache: Dict[str, List[float]] = {}

        # In-memory index
        self._index_ids: List[str] = []
        self._index_texts: List[str] = []
        self._index_vectors: Any = None  # np.ndarray (N, dim) or None
        self._index_built = False

        # Stats
        self.embed_calls = 0
        self.embed_tokens_approx = 0
        self.cache_hits = 0

    @property
    def available(self) -> bool:
        """Check if semantic matching is available."""
        return bool(self.api_key and HAS_NUMPY and HAS_HTTPX)

    @property
    def cost_usd(self) -> float:
        """Estimated cost for embedding calls ($0.02 per 1M tokens)."""
        return self.embed_tokens_approx * 0.00002 / 1000

    # ------------------------------------------------------------------
    # Embedding API
    # ------------------------------------------------------------------

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed texts via OpenAI REST API.

        Features:
        - Batched requests (default 64 per batch)
        - In-memory caching by text hash
        - Retry with exponential backoff
        """
        if not texts:
            return []
        if not self.available:
            raise RuntimeError("SemanticMatcher not available (missing API key or deps)")

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []

        # Check cache first
        for i, text in enumerate(texts):
            key = self._cache_key(text)
            if key in self._cache:
                results[i] = self._cache[key]
                self.cache_hits += 1
            else:
                uncached_indices.append(i)

        # Batch embed uncached texts
        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            vectors = await self._embed_via_api(uncached_texts)

            for idx, vec in zip(uncached_indices, vectors):
                key = self._cache_key(texts[idx])
                self._cache[key] = vec
                results[idx] = vec

        return results  # type: ignore[return-value]

    async def _embed_via_api(self, texts: List[str]) -> List[List[float]]:
        """Call OpenAI embeddings API with batching and retry."""
        all_vectors: List[List[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            vectors = await self._embed_batch_with_retry(batch)
            all_vectors.extend(vectors)

            # Approximate token count (4 chars ≈ 1 token)
            self.embed_tokens_approx += sum(len(t) // 4 + 1 for t in batch)
            self.embed_calls += 1

        return all_vectors

    async def _embed_batch_with_retry(self, texts: List[str]) -> List[List[float]]:
        """Single batch API call with retry."""
        import asyncio

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        OPENAI_EMBEDDINGS_URL,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "input": texts,
                        },
                    )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"OpenAI embeddings HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )

                data = response.json()
                items = data.get("data", [])
                if len(items) != len(texts):
                    raise RuntimeError(
                        f"Expected {len(texts)} embeddings, got {len(items)}"
                    )

                return [item["embedding"] for item in items]

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Embedding API attempt %d failed: %s. Retrying in %.1fs...",
                        attempt + 1, e, delay
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(f"Embedding API failed after {MAX_RETRIES} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Index operations
    # ------------------------------------------------------------------

    async def build_index(self, items: List[Tuple[str, str]]) -> int:
        """Build in-memory index from (id, text) pairs.

        Returns number of items indexed.
        """
        if not items:
            return 0
        if not self.available:
            logger.info("Semantic matcher not available. Index not built.")
            return 0

        ids = [item[0] for item in items]
        texts = [item[1] for item in items]

        vectors = await self.embed_batch(texts)

        self._index_ids = ids
        self._index_texts = texts
        self._index_vectors = np.array(vectors, dtype=np.float32)

        # Normalize for cosine similarity (dot product on unit vectors)
        norms = np.linalg.norm(self._index_vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # avoid division by zero
        self._index_vectors = self._index_vectors / norms

        self._index_built = True
        logger.info(
            "Semantic index built: %d items, %d embed calls, ~%d tokens",
            len(ids), self.embed_calls, self.embed_tokens_approx
        )
        return len(ids)

    async def find_similar(
        self, query: str, top_k: int = 5, threshold: float = 0.0
    ) -> List[Tuple[str, float]]:
        """Find top-K similar items from index.

        Returns [(id, cosine_score), ...] sorted by descending score.
        """
        if not self._index_built or self._index_vectors is None:
            return []

        query_vec = await self.embed_batch([query])
        if not query_vec or not query_vec[0]:
            return []

        q = np.array(query_vec[0], dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

        # Cosine similarity = dot product of normalized vectors
        scores = self._index_vectors @ q  # (N,)

        # Get top-K indices
        if top_k >= len(scores):
            top_indices = np.argsort(scores)[::-1]
        else:
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score >= threshold:
                results.append((self._index_ids[idx], score))

        return results[:top_k]

    async def find_best_match(
        self, query: str, threshold: float = 0.5
    ) -> Optional[Tuple[str, float]]:
        """Find the single best match above threshold. Returns (id, score) or None."""
        results = await self.find_similar(query, top_k=1, threshold=threshold)
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        """Hash text for cache lookup."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def clear_cache(self):
        """Clear embedding cache."""
        self._cache.clear()

    def clear_index(self):
        """Clear the in-memory index."""
        self._index_ids.clear()
        self._index_texts.clear()
        self._index_vectors = None
        self._index_built = False

    def stats(self) -> Dict[str, Any]:
        """Return usage statistics."""
        return {
            "available": self.available,
            "index_size": len(self._index_ids),
            "cache_size": len(self._cache),
            "cache_hits": self.cache_hits,
            "embed_calls": self.embed_calls,
            "embed_tokens_approx": self.embed_tokens_approx,
            "cost_usd": self.cost_usd,
        }
