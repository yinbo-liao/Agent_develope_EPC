"""Authorization matrix tests.

Runs entirely in-process against ``main.app`` (no database, no lifespan):
authentication rejects requests before any route body executes, so the full
401/403 matrix is testable without PostgreSQL.

Covered:
- Every private /api route returns 401 without a bearer token.
- Every DELETE route returns 403 for a viewer and is not rejected for a
  trade_lead (the request may still fail later for other reasons such as a
  missing database or invalid body — that is not an authorization failure).
- WebSocket connections without a token/subprotocol are not accepted.
"""

import re

import pytest
from fastapi.testclient import TestClient

import main
from auth import limiter
from tests.auth_helpers import asgi_client, bearer

# The in-process suite issues more requests than the production 120/min default
# limit; disable limiting here so 429s never masquerade as auth failures.
if limiter is not None:  # pragma: no branch - slowapi is a hard dependency
    limiter.enabled = False

# Endpoints reachable without authentication (middleware-level whitelist).
PUBLIC_API_PATHS = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
}

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
API_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _materialize(path: str) -> str:
    """Replace path params with a concrete value."""
    return re.sub(r"\{[^}]+\}", "test-project", path)


def _private_api_routes():
    for route in main.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if not path.startswith("/api/") or path in PUBLIC_API_PATHS:
            continue
        usable = sorted(methods & API_METHODS)
        if usable:
            yield path, usable


async def test_private_api_routes_require_authentication():
    checked = 0
    async with asgi_client(main.app) as client:
        for path, methods in _private_api_routes():
            for method in methods:
                kwargs = {"json": {}} if method in MUTATING_METHODS else {}
                response = await client.request(
                    method, _materialize(path), **kwargs,
                )
                assert response.status_code == 401, (
                    f"{method} {path}: expected 401 without a token, "
                    f"got {response.status_code}: {response.text[:200]}"
                )
                checked += 1
    assert checked > 100, f"only {checked} private API operations were checked"


async def test_delete_routes_reject_viewers_but_allow_trade_leads():
    delete_routes = [
        path
        for path, methods in _private_api_routes()
        if "DELETE" in methods
    ]
    assert delete_routes, "expected at least one DELETE route to test"

    async with asgi_client(main.app) as client:
        for path in delete_routes:
            url = _materialize(path)

            viewer_response = await client.request(
                "DELETE", url, headers=bearer("viewer"), json={},
            )
            assert viewer_response.status_code == 403, (
                f"DELETE {path}: viewer should get 403, got "
                f"{viewer_response.status_code}: {viewer_response.text[:200]}"
            )

            try:
                lead_response = await client.request(
                    "DELETE", url, headers=bearer("trade_lead"), json={},
                )
            except Exception:
                # Authorization passed; the route itself failed later (for
                # example because no database pool exists in this test).
                continue
            assert lead_response.status_code not in (401, 403), (
                f"DELETE {path}: trade_lead should pass authorization, got "
                f"{lead_response.status_code}: {lead_response.text[:200]}"
            )


def test_websocket_without_token_is_not_accepted():
    client = TestClient(main.app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/test-project"):
            pass
