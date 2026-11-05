"""
Standardized error handling for the FPSO EPC API.

All endpoints return errors in a consistent shape:
    {"detail": str, "code": str, "context": dict | None}

Usage:
    from errors import AppError, not_found, bad_request

    @router.get("/items/{id}")
    async def get_item(id: str):
        item = await fetch_item(id)
        if not item:
            raise not_found("Item", id)
        return item
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi import status


class AppError(HTTPException):
    """Application-level error with structured context."""

    def __init__(self, status_code: int, detail: str, code: str = "ERROR", context: dict | None = None):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = code
        self.error_context = context or {}


# ── Convenience factories ──────────────────────────────────────────────

def not_found(entity: str, identifier: str | None = None) -> AppError:
    msg = f"{entity} not found"
    if identifier:
        msg += f": {identifier}"
    return AppError(status.HTTP_404_NOT_FOUND, msg, "NOT_FOUND", {"entity": entity, "id": identifier})

def bad_request(detail: str, code: str = "BAD_REQUEST", context: dict | None = None) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, detail, code, context)

def unauthorized(detail: str = "Authentication required") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, detail, "UNAUTHORIZED")

def forbidden(detail: str = "Insufficient permissions") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, detail, "FORBIDDEN")

def conflict(detail: str) -> AppError:
    return AppError(status.HTTP_409_CONFLICT, detail, "CONFLICT")

def validation_error(detail: str, context: dict | None = None) -> AppError:
    return AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, detail, "VALIDATION_ERROR", context)


# ── Global Exception Handlers ──────────────────────────────────────────

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": exc.error_code,
            "context": exc.error_context,
        },
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize standard HTTPExceptions to the app error shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": f"HTTP_{exc.status_code}",
            "context": None,
        },
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors. Returns 500 with safe message."""
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please try again or contact support.",
            "code": "INTERNAL_ERROR",
            "context": None,
        },
    )


def register_error_handlers(app):
    """Register all error handlers on a FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
