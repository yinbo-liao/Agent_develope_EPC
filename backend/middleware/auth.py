"""
API Key Authentication Middleware

Simple API key authentication as the first line of defense.
Protects all routes when FPSO_API_KEY environment variable is set.

Usage:
    # Set the key (omit to disable — all requests allowed):
    export FPSO_API_KEY=your-secure-key

    # Clients must include:
    #   Header: X-API-Key: your-secure-key

Full OAuth2+JWT with RBAC should replace this in a subsequent phase.
"""

import logging
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded API key — only validated once on first request
_api_key: str | None = None
_api_key_loaded: bool = False


def _get_api_key() -> str | None:
    """Load API key from environment. Returns None if not configured."""
    global _api_key, _api_key_loaded
    if not _api_key_loaded:
        import os
        _api_key = os.getenv("FPSO_API_KEY", "").strip() or None
        _api_key_loaded = True
        if _api_key:
            logger.info("API key authentication enabled (FPSO_API_KEY set)")
        else:
            logger.warning("API key authentication DISABLED — all requests are public. Set FPSO_API_KEY to enable.")
    return _api_key


async def verify_api_key(request: Request) -> None:
    """
    FastAPI dependency — verifies the X-API-Key header.
    Add to route dependencies: @router.get("/path", dependencies=[Depends(verify_api_key)])

    Safe to use as middleware (applies to all routes) or per-route.
    If FPSO_API_KEY is not set, all requests pass through.
    """
    expected_key = _get_api_key()
    if expected_key is None:
        # API key auth not configured — allow all requests
        return

    provided_key = request.headers.get("X-API-Key", "")
    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header. API key authentication is required.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def require_auth():
    """Convenience import for route-level dependencies."""
    from fastapi import Depends
    return Depends(verify_api_key)
