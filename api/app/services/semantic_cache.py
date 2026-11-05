from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_redis_available: bool = False

# Simple stopwords for query normalization
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "than", "too",
    "very", "just", "about", "above", "after", "again", "before",
    "between", "down", "up", "out", "off", "over", "under", "what",
    "which", "who", "whom", "this", "that", "these", "those",
})

# Responses for these risk levels are never reused: a high-stakes answer must be
# produced for the specific run, not served from another user's cache entry.
_UNCACHEABLE_RISK_LEVELS = frozenset({"high", "critical"})


def _normalize_query(query: str) -> str:
    """Normalize a query for caching: lowercase, strip punctuation, remove stopwords."""
    lowered = query.lower().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    words = lowered.split()
    meaningful = [w for w in words if w not in _STOPWORDS and len(w) > 1]
    return " ".join(meaningful)


def _query_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _scope_hash(scope: str) -> str:
    """Hash the tenant/user scope so cache keys cannot be guessed or injected."""
    return hashlib.sha256(scope.encode()).hexdigest()[:16]


def cache_key(scope: str, model: str, query: str) -> str:
    """Return the tenant-scoped cache key for a query/model pair."""
    return f"semantic:{_scope_hash(scope)}:{model}:{_query_hash(_normalize_query(query))}"


async def _ensure_redis() -> bool:
    global _redis, _redis_available
    if _redis is not None:
        return _redis_available
    try:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis.ping()
        _redis_available = True
    except Exception:
        _redis_available = False
        logger.debug("Semantic cache Redis unavailable")
    return _redis_available


async def check_cache(
    query: str,
    model: str,
    scope: str,
    risk_level: str = "low",
) -> dict[str, Any] | None:
    """Check the caller-scoped semantic cache. High-risk runs bypass it entirely."""
    if risk_level in _UNCACHEABLE_RISK_LEVELS:
        return None
    if not await _ensure_redis():
        return None

    normalized = _normalize_query(query)
    if len(normalized) < 5:
        return None

    key = cache_key(scope, model, query)
    try:
        cached = await _redis.get(key)  # type: ignore[union-attr]
        if cached:
            logger.info("Semantic cache HIT for scope %s", _scope_hash(scope))
            return json.loads(cached)
    except Exception:
        logger.debug("Semantic cache read error")

    return None


async def store_cache(
    query: str,
    model: str,
    response: dict[str, Any],
    scope: str,
    risk_level: str = "low",
    ttl: int = 3600,
) -> None:
    """Store a query-response pair under the caller's scope."""
    if risk_level in _UNCACHEABLE_RISK_LEVELS:
        return
    if not await _ensure_redis():
        return

    normalized = _normalize_query(query)
    if len(normalized) < 5:
        return

    try:
        await _redis.set(cache_key(scope, model, query), json.dumps(response, default=str), ex=ttl)  # type: ignore[union-attr]
        logger.debug("Semantic cache stored for scope %s", _scope_hash(scope))
    except Exception:
        logger.debug("Semantic cache write error")


# Track cache statistics
_cache_hits: int = 0
_cache_misses: int = 0


def record_hit() -> None:
    global _cache_hits
    _cache_hits += 1


def record_miss() -> None:
    global _cache_misses
    _cache_misses += 1


def get_stats() -> dict[str, int]:
    return {"hits": _cache_hits, "misses": _cache_misses, "total": _cache_hits + _cache_misses}