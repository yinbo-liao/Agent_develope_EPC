"""
Unified Database Pool — single asyncpg pool for all routers.

This module replaces the split-pool pattern where:
- Some routers used `main.pool` (raw asyncpg)
- Others used `database.get_db()` (SQLAlchemy AsyncSession)

After consolidation, all routers use `get_pool()` for raw SQL performance.
The SQLAlchemy engine in database.py is kept ONLY for Alembic migrations and ORM model metadata.

Usage:
    from db import get_pool

    @router.get("/items/{project_id}")
    async def list_items(project_id: str, pool = Depends(get_pool)):
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM items WHERE project_id = $1", project_id)
        return [dict(r) for r in rows]
"""

import asyncpg
from config import settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """Initialize the global asyncpg connection pool. Called once at app startup."""
    global _pool
    if _pool is not None:
        return _pool
    dsn = settings.database_url.replace("+asyncpg", "")
    _pool = await asyncpg.create_pool(dsn)
    return _pool


async def close_pool():
    """Close the global pool. Called at app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    """FastAPI dependency — yields the asyncpg pool for use in route handlers.

    Returns the pre-initialized global pool directly. Asyncpg pools are
    thread-safe and connection-safe; acquiring a connection from the pool
    is handled by each route via `async with pool.acquire() as conn:`.

    Example:
        @router.get("/items/{project_id}")
        async def get_items(project_id: str, pool = Depends(get_pool)):
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT ...")
            return [dict(r) for r in rows]
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. "
            "Ensure init_pool() is called during application startup."
        )
    return _pool
