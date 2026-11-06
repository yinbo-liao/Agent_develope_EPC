"""
CSRF Protection Middleware

Validates Origin/Referer headers for state-changing requests (POST/PUT/PATCH/DELETE).

- Origins are matched exactly against ``settings.cors_origins`` (a prefix match
  would let ``http://localhost:5173.evil.com`` through).
- In production, a mutating request with neither Origin nor Referer is rejected.
- In development/test, requests without those headers are allowed so CLI tools
  and the test suite keep working.
"""

import logging
from urllib.parse import urlsplit

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _normalized_origins() -> set[str]:
    return {origin.rstrip("/").lower() for origin in settings.cors_origins}


def _origin_of(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": detail, "code": "CSRF_REJECTED", "context": None},
    )


class CSRFTokenMiddleware(BaseHTTPMiddleware):
    """Origin/Referer header validation for state-changing requests."""

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)

        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        allowed = _normalized_origins()

        if not origin and not referer:
            if settings.environment == "production":
                logger.warning("CSRF: No Origin/Referer on %s %s",
                               request.method, request.url.path)
                return _forbidden("Origin or Referer header is required.")
            # Development/test: allow API clients without browser headers.
            return await call_next(request)

        if origin and origin.rstrip("/").lower() in allowed:
            return await call_next(request)

        if referer:
            referer_origin = _origin_of(referer)
            if referer_origin and referer_origin.rstrip("/") in allowed:
                return await call_next(request)

        logger.warning("CSRF: Invalid Origin '%s' for %s %s",
                       origin, request.method, request.url.path)
        return _forbidden("Cross-origin request rejected. Invalid Origin header.")


def add_csrf_middleware(app):
    """Add CSRF middleware to FastAPI app."""
    app.add_middleware(CSRFTokenMiddleware)
    logger.info("CSRF middleware enabled")
