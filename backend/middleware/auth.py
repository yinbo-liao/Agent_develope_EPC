"""
Optional API-key guard (a coarse first line of defence in front of JWT auth).

This module is **opt-in**: it does nothing unless ``FPSO_API_KEY`` is set in the
process environment. It is intentionally *not* wired into the application by
this module — see the wiring note at the bottom of the file. It is currently
imported by nothing, so it only takes effect when an application or route
declares the dependency.

Usage::

    export FPSO_API_KEY=your-secure-key

    # Per route:
    @router.get("/path", dependencies=[Depends(verify_api_key)])
    async def handler(): ...

    # Or globally (see note below):
    app = FastAPI(dependencies=[Depends(verify_api_key)])

Clients send ``X-API-Key: <value>``. Comparisons use
``hmac.compare_digest`` to avoid leaking timing information.

.. warning::
   If enabled globally, allow health probes and metrics to bypass it — see the
   wiring note at the bottom of this file. FastAPI-level dependencies do not
   apply to WebSocket endpoints, so the WebSocket route needs its own check.
"""

import hmac
import logging
import os

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# Log the "disabled" warning at most once per process.
_warned_disabled = False


def _get_api_key() -> str | None:
    """Return the configured API key, or ``None`` when the guard is disabled.

    Read from the environment on every call so tests and container restarts
    observe changes; the lookup is a cheap dict access.
    """
    global _warned_disabled
    api_key = os.getenv("FPSO_API_KEY", "").strip()
    if api_key:
        return api_key
    if not _warned_disabled:
        _warned_disabled = True
        logger.info(
            "API key authentication DISABLED (FPSO_API_KEY not set). "
            "All requests pass through this guard."
        )
    return None


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency — verify the ``X-API-Key`` header.

    No-op when ``FPSO_API_KEY`` is unset. Raises 401 when the header is missing
    or does not match in constant time.
    """
    expected_key = _get_api_key()
    if expected_key is None:
        return

    provided_key = request.headers.get("X-API-Key", "")
    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header. API key authentication is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Compare bytes so non-ASCII input cannot raise TypeError.
    if not hmac.compare_digest(
        provided_key.encode("utf-8"), expected_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def require_auth():
    """Convenience helper for route-level dependencies."""
    from fastapi import Depends

    return Depends(verify_api_key)


# ---------------------------------------------------------------------------
# Recommended wiring (not applied here; main.py is owned by the app layer)
# ---------------------------------------------------------------------------
# A global FastAPI dependency is the simplest correct installation, but it must
# exempt the routes that infrastructure calls without credentials:
#
#   from middleware.auth import verify_api_key
#
#   _PUBLIC_PATHS = {"/health", "/health/live", "/health/ready", "/metrics",
#                    "/docs", "/openapi.json", "/redoc"}
#
#   async def api_key_dependency(request: Request) -> None:
#       if request.url.path in _PUBLIC_PATHS:
#           return
#       await verify_api_key(request)
#
#   app = FastAPI(..., dependencies=[Depends(api_key_dependency)])
#
# WebSockets are NOT covered by dependencies; add the same check in
# ``websocket_endpoint`` (header ``X-API-Key`` or query parameter).
#
# Note: CORS must allow the X-API-Key header (main.py already lists it), and
# the frontend has no UI to supply the key — keep this opt-in until clients
# can be configured.
