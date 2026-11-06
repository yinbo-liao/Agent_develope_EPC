"""Shared helpers for authentication/authorization tests.

These helpers only mint tokens and build clients. They never touch a real
database: rejections in FastAPI dependencies happen before a route body (and
therefore before any DB access) is reached, so the full 401/403 matrix is
testable without PostgreSQL.
"""

from __future__ import annotations

from typing import Iterable

import httpx

from auth import TokenData, create_access_token

ROLES = ("viewer", "trade_lead", "project_manager", "admin")

# Roles allowed to perform writes. Keep in sync with the write dependency
# installed in main.py.
WRITE_ROLES = ("trade_lead", "project_manager", "admin")


def make_token(role: str = "viewer", username: str | None = None,
               user_id: str | None = None) -> TokenData:
    """Create a TokenData for the given role."""
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    username = username or f"{role}-test"
    return TokenData(user_id=user_id or f"user-{role}", username=username, role=role)


def bearer(role: str = "viewer", username: str | None = None) -> dict[str, str]:
    """Return a Bearer Authorization header for the given role."""
    token_data = make_token(role, username=username)
    token = create_access_token(
        {"sub": token_data.user_id, "username": token_data.username, "role": token_data.role}
    )
    return {"Authorization": f"Bearer {token}"}


def asgi_client(app) -> httpx.AsyncClient:
    """Build an in-process client. Lifespan is NOT run, so no DB pool starts."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def assert_401(response: httpx.Response, context: str = "") -> None:
    assert response.status_code == 401, (
        f"{context}: expected 401, got {response.status_code}: {response.text[:200]}"
    )


def assert_403(response: httpx.Response, context: str = "") -> None:
    assert response.status_code == 403, (
        f"{context}: expected 403, got {response.status_code}: {response.text[:200]}"
    )


def forbidden_for(role: str, write_roles: Iterable[str] = WRITE_ROLES) -> bool:
    """True when this role must be rejected for write endpoints."""
    return role not in write_roles
