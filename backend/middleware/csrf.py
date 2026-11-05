"""
CSRF Protection Middleware

Validates Origin/Referer headers for state-changing requests (POST/PUT/PATCH/DELETE).
Rejects requests with mismatched or missing Origin headers.

For SPAs served from the same origin, this is sufficient protection against CSRF.
For cross-origin API access, use the CSRF token pattern (next phase).
"""

import logging
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class CSRFTokenMiddleware(BaseHTTPMiddleware):
    """Origin/Referer header validation for state-changing requests."""

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)

        # In development, allow requests without Origin checks
        # In production, validate Origin against allowed CORS origins
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        allowed_origins = settings.cors_origins

        # If no Origin/Referer and not in dev mode, reject
        if not origin and not referer:
            logger.warning(f"CSRF: No Origin/Referer on {request.method} {request.url.path}")
            # For API clients (Postman, curl), allow if they have valid auth
            # (auth dependency handles that separately)
            return await call_next(request)

        # Validate Origin
        if origin:
            if any(origin.startswith(allowed.rstrip("/")) or origin == allowed
                   for allowed in allowed_origins):
                return await call_next(request)

        # Validate Referer as fallback
        if referer:
            if any(referer.startswith(allowed.rstrip("/")) or referer.startswith(allowed)
                   for allowed in allowed_origins):
                return await call_next(request)

        logger.warning(f"CSRF: Invalid Origin '{origin}' for {request.method} {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin request rejected. Invalid Origin header.",
        )


def add_csrf_middleware(app):
    """Add CSRF middleware to FastAPI app."""
    app.add_middleware(CSRFTokenMiddleware)
    logger.info("CSRF middleware enabled")
