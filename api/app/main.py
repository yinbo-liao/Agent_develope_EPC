from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1 import analytics, audit, auth, cost, events, health, human_review, mcp, workflows
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging import setup_logging
from app.core.mcp_client import mcp_tool_manager
from app.core.metrics import setup_metrics
from app.core.tracing import tracing_manager
from app.core.websocket_manager import ws_manager
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware

setup_logging()
logger = logging.getLogger(__name__)

# Validate production secrets at import time — refuse to start with insecure defaults
_production_errors = settings.validate_production_secrets()
if _production_errors:
    for error in _production_errors:
        logger.critical("Production secret validation FAILED: %s", error)
    raise RuntimeError(
        "Insecure default secrets detected in production. "
        "Set proper values for: " + ", ".join(_production_errors)
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting backend services")
    await init_db()
    await mcp_tool_manager.initialize()
    await ws_manager.connect()
    try:
        yield
    finally:
        await ws_manager.disconnect()
        await mcp_tool_manager.close()
        await close_db()
        logger.info("Backend services stopped")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(RateLimitMiddleware)

    if settings.ENABLE_METRICS:
        setup_metrics(app)
    tracing_manager.instrument_fastapi(app)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": settings.APP_NAME, "version": settings.APP_VERSION}

    app.include_router(auth.router, prefix=settings.API_PREFIX)
    app.include_router(health.router, prefix="/health", tags=["Health"])
    app.include_router(workflows.router, prefix=settings.API_PREFIX)
    app.include_router(events.router, prefix=settings.API_PREFIX)
    app.include_router(human_review.router, prefix=settings.API_PREFIX)
    app.include_router(cost.router, prefix=settings.API_PREFIX)
    app.include_router(mcp.router, prefix=settings.API_PREFIX)
    app.include_router(analytics.router, prefix=settings.API_PREFIX)
    app.include_router(audit.router, prefix=settings.API_PREFIX)
    return app


app = create_application()
