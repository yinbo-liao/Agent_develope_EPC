"""
Embedding generator — creates vector embeddings for text using configured provider.

Supports DeepSeek (primary) with fallback to simple TF-IDF-like keyword vectors.
"""

import logging
from config import settings

logger = logging.getLogger(__name__)


class Embedder:
    """Generate embeddings for text using the configured AI provider."""

    def __init__(self):
        self._provider = None

    @property
    def provider(self):
        if self._provider is None:
            from services.llm_provider import llm_provider
            self._provider = llm_provider
        return self._provider

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into vectors."""
        if self.provider.enabled:
            try:
                return await self.provider.embed(texts)
            except Exception as e:
                logger.warning(f"Provider embedding failed: {e}")

        # Fallback: keyword-based pseudo-embedding
        logger.info("Using keyword-based pseudo-embedding (no AI provider configured)")
        return self._keyword_embed(texts)

    def _keyword_embed(self, texts: list[str]) -> list[list[float]]:
        """Simple keyword-based pseudo-embedding. Not suitable for production use."""
        # Build a vocabulary from all texts
        vocab: dict[str, int] = {}
        for text in texts:
            for word in text.lower().split():
                word = word.strip(".,;:!?()[]{}\"'")
                if word and word not in vocab:
                    vocab[word] = len(vocab)

        dim = max(128, len(vocab))
        vectors = []
        for text in texts:
            vec = [0.0] * dim
            words = text.lower().split()
            for word in words:
                word = word.strip(".,;:!?()[]{}\"'")
                if word in vocab:
                    idx = vocab[word] % dim
                    vec[idx] += 1.0
            # Normalize
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed([query])
        return results[0]


# Singleton
embedder = Embedder()
