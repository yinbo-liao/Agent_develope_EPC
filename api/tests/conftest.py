from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Ensure api/ is on the path so `from app...` imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Test database — file-based for cross-connection sharing
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Return a file-based SQLite path shared across the test session."""
    db_dir = tmp_path_factory.mktemp("test_db")
    return str(db_dir / "test_workflow.db")


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_db_path: str) -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped engine pointing at a shared SQLite file."""
    url = f"sqlite+aiosqlite:///{test_db_path}"
    engine = create_async_engine(url, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test settings
# ---------------------------------------------------------------------------

@pytest.fixture
def test_settings(test_db_path: str) -> Any:
    from app.core.config import Settings  # noqa: E402

    return Settings(
        ENVIRONMENT="test",
        DEBUG=False,
        SECRET_KEY="test-secret-key-at-least-16-chars",
        DATABASE_URL=f"sqlite+aiosqlite:///{test_db_path}",
        REDIS_URL="redis://:test@localhost:6379/0",
        OPA_URL="http://opa:8181",
        ENABLE_METRICS=False,
        ENABLE_TRACING=False,
        REQUESTS_PER_MINUTE=1000,
        MCP_POSTGRES_ENABLED=False,
        MCP_GITHUB_ENABLED=False,
        MCP_PUPPETEER_ENABLED=False,
        MCP_SLACK_ENABLED=False,
    )


# ---------------------------------------------------------------------------
# Helper: create tables on a test engine
# ---------------------------------------------------------------------------

async def _create_tables(engine: AsyncEngine) -> None:
    from app.models import Base  # noqa: E402

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(test_settings: Any, test_db_path: str) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client pointed at the FastAPI app."""
    import app.core.config as config_module  # noqa: E402

    # Build a real engine with shared file DB so connections see the same tables
    url = f"sqlite+aiosqlite:///{test_db_path}"
    shared_engine = create_async_engine(url, echo=False)
    await _create_tables(shared_engine)
    shared_sessionmaker = async_sessionmaker(shared_engine, expire_on_commit=False, class_=AsyncSession)

    with patch.object(config_module, "settings", test_settings), patch.object(
        config_module, "get_settings", return_value=test_settings
    ), patch(
        "app.core.database.engine", shared_engine
    ), patch(
        "app.core.database.SessionLocal", shared_sessionmaker
    ), patch(
        "app.core.database.init_db", new_callable=AsyncMock
    ), patch(
        "app.core.database.close_db", new_callable=AsyncMock
    ), patch(
        "app.core.mcp_client.mcp_tool_manager.initialize", new_callable=AsyncMock
    ), patch(
        "app.core.mcp_client.mcp_tool_manager.close", new_callable=AsyncMock
    ), patch(
        "app.core.websocket_manager.ws_manager.connect", new_callable=AsyncMock
    ), patch(
        "app.core.websocket_manager.ws_manager.disconnect", new_callable=AsyncMock
    ):

        from app.main import create_application  # noqa: E402

        app = create_application()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    await shared_engine.dispose()


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis() -> MagicMock:
    """Return a MagicMock standing in for a Redis client."""
    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.publish = AsyncMock(return_value=1)
    redis.incrby = AsyncMock(return_value=1)
    redis.incrbyfloat = AsyncMock(return_value=0.0)
    redis.pipeline = MagicMock(return_value=redis)
    redis.execute = AsyncMock(return_value=[])
    return redis


@pytest.fixture
def mock_opa_client() -> MagicMock:
    """Return a MagicMock standing in for the OPA client."""
    opa = MagicMock()
    opa.evaluate = AsyncMock(
        return_value={"allowed": True, "violations": [], "input": {"agent": "test"}}
    )
    opa.check_scope = AsyncMock(return_value=True)
    return opa


# ---------------------------------------------------------------------------
# Auth helpers for tests
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_headers(test_settings: Any) -> dict[str, str]:
    """Return Authorization headers with a valid test JWT."""
    from app.security.auth import create_access_token  # noqa: E402

    token = create_access_token(
        subject="test-user-id",
        extra_claims={"role": "admin", "tier": "professional"},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_auth_headers(test_settings: Any) -> dict[str, str]:
    """Return Authorization headers for a viewer-role user."""
    from app.security.auth import create_access_token  # noqa: E402

    token = create_access_token(
        subject="viewer-user-id",
        extra_claims={"role": "viewer", "tier": "free"},
    )
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def reviewer_auth_headers(test_settings: Any) -> dict[str, str]:
    """Return Authorization headers for a reviewer-role user (human review)."""
    from app.security.auth import create_access_token  # noqa: E402

    token = create_access_token(
        subject="reviewer-user-id",
        extra_claims={"role": "reviewer", "tier": "starter"},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_user_auth_headers(test_settings: Any) -> dict[str, str]:
    """Return Authorization headers for a second, unrelated viewer."""
    from app.security.auth import create_access_token  # noqa: E402

    token = create_access_token(
        subject="other-user-id",
        extra_claims={"role": "viewer", "tier": "free"},
    )
    return {"Authorization": f"Bearer {token}"}
