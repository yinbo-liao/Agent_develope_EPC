"""
Simple Redis-backed response cache for expensive endpoints.

Usage:
    from cache import cached

    @router.get("/expensive-endpoint/{project_id}")
    @cached(ttl_seconds=300, key_prefix="dashboard")
    async def expensive_endpoint(project_id: str): ...

Cache invalidation happens automatically on TTL expiry.
For manual invalidation, publish to Redis channel: cache:invalidate:<key_prefix>
"""

import functools
import hashlib
import json
import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[object] = None
_redis_available: bool = False


async def _get_redis():
    """Lazy Redis connection for caching."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client if _redis_available else None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis_client.ping()
        _redis_available = True
        logger.info("Cache: Redis connected")
        return _redis_client
    except Exception:
        _redis_available = False
        _redis_client = False
        logger.info("Cache: Redis unavailable, caching disabled")
        return None


def _make_cache_key(prefix: str, args, kwargs) -> str:
    """Generate a deterministic cache key from function arguments."""
    raw = json.dumps({"args": args, "kwargs": {k: str(v) for k, v in kwargs.items()}}, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"cache:{prefix}:{digest}"


def cached(ttl_seconds: int = 300, key_prefix: str = "default"):
    """Decorator: cache async function results in Redis for `ttl_seconds`.

    Skips cache if Redis is unavailable (no-op passthrough).
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            redis = await _get_redis()
            if not redis:
                return await func(*args, **kwargs)

            cache_key = _make_cache_key(key_prefix, args, kwargs)
            try:
                cached_value = await redis.get(cache_key)
                if cached_value is not None:
                    return json.loads(cached_value)
            except Exception:
                pass  # Cache read failure — fall through to compute

            result = await func(*args, **kwargs)

            try:
                await redis.setex(cache_key, ttl_seconds, json.dumps(result, default=str))
            except Exception:
                pass  # Cache write failure — return result anyway

            return result
        return wrapper
    return decorator


async def invalidate_cache(key_prefix: str):
    """Invalidate all cached entries for a given prefix.

    Call after mutations that affect the cached data.
    """
    redis = await _get_redis()
    if not redis:
        return
    try:
        # Scan and delete keys matching the prefix
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"cache:{key_prefix}:*", count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        logger.warning(f"Cache invalidation failed for '{key_prefix}': {e}")
