"""
Database engine and session configuration.

IMPORTANT — Pool Architecture (Phase 0 consolidation):
- `db.get_pool()` (asyncpg.Pool): PRIMARY pool for all raw SQL queries. All routers
  should use this via `from db import get_pool` for best performance.
- `engine` (SQLAlchemy): Kept ONLY for Alembic migrations and ORM model metadata.
  `get_db()` provides SQLAlchemy AsyncSession for backward compatibility with
  code that hasn't been migrated to the unified pool yet.

Pool sizes:
- asyncpg pool: configured in db.py (defaults from asyncpg)
- SQLAlchemy engine: pool_size=20, max_overflow=10 (below, used only for Alembic/ORM)
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings

# Lazy engine initialization — avoids import-time failures when DATABASE_URL is unset
engine = None


def _get_engine():
    global engine
    if engine is None:
        if not settings.database_url:
            # Create a SQLite in-memory engine as fallback for testing/import validation
            engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
        else:
            engine = create_async_engine(
                settings.database_url,
                pool_size=20,
                max_overflow=10,
                pool_timeout=30,
                echo=False,
            )
    return engine


def _get_async_session():
    return async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)


async_session = None


class Base(DeclarativeBase):
    pass


async def get_db():
    """Yield a SQLAlchemy AsyncSession.

    NOTE: For new code, prefer using `get_pool()` from main.py which returns
    the primary asyncpg pool connection for raw SQL performance.
    """
    global async_session
    if async_session is None:
        async_session = _get_async_session()
    async with async_session() as session:
        yield session

