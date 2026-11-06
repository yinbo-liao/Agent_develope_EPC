"""FPSO EPC Project Control System — production FastAPI application.

Importing this module must never require a database or Redis connection:
connections are established in the lifespan handler, and every external
dependency is allowed to be absent in development.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import settings, validate_runtime_config
from websocket import manager
from services.alert_service import AlertService
from auth import (
    TokenData,
    bootstrap_admin,
    decode_token,
    get_current_user,
    has_role,
    limiter as shared_limiter,
    require_role,
    user_has_project_access,
)
from db import init_pool, close_pool, get_pool

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Writes that are part of the authentication handshake itself.
PUBLIC_WRITE_PATHS = {
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/logout-all",
}


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware:
    """Adds defensive response headers. Pure ASGI to keep it cheap."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Permissions-Policy",
                    "geolocation=(), microphone=(), camera=()",
                )
                if settings.environment == "production":
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
                # Lock down API (JSON) responses; leave docs/HTML alone in dev.
                if settings.environment == "production" or "application/json" in \
                        headers.get("content-type", ""):
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'none'; frame-ancestors 'none'",
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


class WriteRoleGuardMiddleware:
    """Rejects mutating requests from roles below ``trade_lead``.

    Authentication itself is delegated to route dependencies: a missing or
    invalid token is passed through so the dependency can return a consistent
    401. This middleware only upgrades ``viewer`` (or unknown roles) to 403.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method", "").upper() not in MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not settings.auth_enforcement or path in PUBLIC_WRITE_PATHS or path.startswith("/health") \
                or path.startswith("/ws"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            # Route dependency will return 401.
            await self.app(scope, receive, send)
            return

        user = decode_token(authorization[7:].strip())
        if user is None:
            # Route dependency will return 401.
            await self.app(scope, receive, send)
            return

        if not has_role(user.role, "trade_lead"):
            response = JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "This action requires trade_lead role or higher.",
                    "code": "forbidden",
                    "context": None,
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    is_production = settings.environment == "production"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fail closed on insecure production configuration.
        validate_runtime_config()

        pool = None
        try:
            pool = await init_pool()
            AlertService.set_pool(pool)
            await bootstrap_admin(pool)
        except RuntimeError:
            # Configuration errors (e.g. production bootstrap password) must
            # always be fatal.
            raise
        except Exception as exc:
            if is_production:
                raise
            logger.warning(
                "Database unavailable at startup (%s); continuing in degraded mode. "
                "Routes that need the database will return errors.",
                exc,
            )

        try:
            await manager.start_redis_listener()
        except Exception as exc:  # Redis is optional
            logger.warning("Redis listener unavailable at startup: %s", exc)

        try:
            yield
        finally:
            try:
                await manager.stop_redis_listener()
            except Exception as exc:  # pragma: no cover - shutdown best effort
                logger.warning("Error stopping Redis listener: %s", exc)
            await close_pool()

    app = FastAPI(
        title="FPSO EPC Project Control System",
        version="4.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    # Standardized error handling
    from errors import register_error_handlers
    register_error_handlers(app)

    # Rate limiting (shared limiter instance defined in auth.py to avoid a
    # circular import with the auth router).
    limiter = shared_limiter
    if limiter is not None:
        try:
            from slowapi import _rate_limit_exceeded_handler
            from slowapi.errors import RateLimitExceeded
            from slowapi.middleware import SlowAPIMiddleware

            app.state.limiter = limiter
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
            app.add_middleware(SlowAPIMiddleware)
        except ImportError:  # pragma: no cover - slowapi optional
            limiter = None

    # Structured logging
    from logging_config import setup_logging
    setup_logging()

    # CSRF protection
    from middleware.csrf import add_csrf_middleware
    add_csrf_middleware(app)

    # Observability (correlation IDs, metrics, request logging)
    from middleware.observability import add_observability_middleware
    add_observability_middleware(app)

    # Security middleware (added before CORS so CORS stays outermost)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(WriteRoleGuardMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    # CORS — explicit origins only, never a wildcard with credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-ID"],
    )

    # Feature routers require an authenticated user.
    from routers import (
        engineering, procurement, construction, inspection, reports, equipment,
        completion, commissioning, quality, safety, training, planning, conflict,
        stagegate, feedback, ai, traceability_router, auth_router,
    )

    # Register AI function tools on startup (import triggers @tool_registry decorators)
    import services.tools.query_tools  # noqa: F401

    app.include_router(auth_router.router)
    for router_module in (
        engineering, procurement, construction, inspection, reports, equipment,
        completion, commissioning, quality, safety, training, planning, conflict,
        stagegate, feedback, ai, traceability_router,
    ):
        app.include_router(
            router_module.router,
            dependencies=[Depends(get_current_user)],
        )

    # -- Health & metrics -------------------------------------------------

    @app.get("/health/live")
    async def health_live():
        """Liveness probe — the process is up. Never touches dependencies."""
        return {"status": "alive"}

    @app.get("/health/ready")
    async def health_ready():
        """Readiness probe — the database must be reachable."""
        try:
            db_pool = await get_pool()
            await asyncio.wait_for(_ping_pool(db_pool), timeout=0.8)
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "checks": {"database": "unavailable"}},
            )
        return {"status": "ready", "checks": {"database": "healthy"}}

    @app.get("/health")
    async def health():
        """Backward-compatible aggregate health check (no internal details)."""
        db_status = "unavailable"
        try:
            db_pool = await get_pool()
            await asyncio.wait_for(_ping_pool(db_pool), timeout=0.8)
            db_status = "healthy"
        except Exception:
            pass

        redis_status = "unavailable"
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url)
            try:
                await asyncio.wait_for(r.ping(), timeout=0.8)
                redis_status = "healthy"
            finally:
                try:
                    await r.aclose()
                except Exception:
                    pass
        except Exception:
            pass

        overall = "healthy" if db_status == "healthy" else "degraded"
        return {
            "status": overall,
            "checks": {"database": db_status, "redis": redis_status},
        }

    @app.get("/metrics")
    async def metrics(request: Request):
        """Prometheus metrics — admin bearer token or loopback only."""
        if not _metrics_allowed(request):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Metrics are restricted.", "code": "forbidden", "context": None},
            )
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
            from fastapi.responses import Response
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except ImportError:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "prometheus_client not installed", "code": "unavailable",
                         "context": None},
            )

    # -- WebSocket --------------------------------------------------------

    @app.websocket("/ws/{project_id}")
    async def websocket_endpoint(ws: WebSocket, project_id: str):
        token, subprotocol = _websocket_token(ws)
        user: TokenData | None = None

        if settings.auth_enforcement:
            if not token:
                await ws.close(code=status.WS_1008_POLICY_VIOLATION,
                               reason="Missing authentication token")
                return
            user = decode_token(token)
            if user is None:
                await ws.close(code=status.WS_1008_POLICY_VIOLATION,
                               reason="Invalid or expired token")
                return
        else:
            user = TokenData(
                user_id="00000000-0000-0000-0000-000000000000",
                username="auth-disabled-bypass",
                role="admin",
            )

        # Origin validation (browsers always send Origin for WS).
        origin = ws.headers.get("origin")
        if origin and not any(
            origin.rstrip("/") == allowed.rstrip("/") for allowed in settings.cors_origins
        ):
            await _reject_websocket(ws, subprotocol, "Origin not allowed")
            return

        # Project-level authorization.
        if settings.auth_enforcement:
            try:
                db_pool = await get_pool()
                allowed = await user_has_project_access(db_pool, project_id, user)
            except Exception as exc:
                logger.warning("WebSocket project access check failed: %s", exc)
                allowed = False
            if not allowed:
                await _reject_websocket(ws, subprotocol, "Project access denied")
                return

        await manager.connect(ws, project_id, subprotocol=subprotocol)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(ws, project_id)
        except Exception:
            await manager.disconnect(ws, project_id)

    # -- Alerts -----------------------------------------------------------

    @app.post("/api/alerts/generate/{project_id}")
    async def trigger_alert_generation(
        project_id: str,
        user: TokenData = Depends(require_role("admin", "project_manager")),
    ):
        db_pool = await get_pool()
        await AlertService.generate_alerts(project_id, db_pool)
        return {"status": "alerts generated"}

    @app.get("/api/alerts/{project_id}")
    async def get_alerts(
        project_id: str,
        severity: str | None = None,
        user: TokenData = Depends(get_current_user),
    ):
        db_pool = await get_pool()
        query = "SELECT * FROM schedule_alerts WHERE project_id = $1 AND is_resolved = FALSE"
        params = [project_id]
        if severity:
            query += " AND severity = $2"
            params.append(severity)
        query += " ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END"
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    return app


async def _ping_pool(db_pool) -> None:
    async with db_pool.acquire() as conn:
        await conn.fetchval("SELECT 1")


def _metrics_allowed(request: Request) -> bool:
    client = request.client.host if request.client else None
    if client in {"127.0.0.1", "::1", "localhost", "testclient", "testserver"}:
        return True
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        user = decode_token(authorization[7:].strip())
        return user is not None and user.role == "admin"
    return False


def _websocket_token(ws: WebSocket) -> tuple[str | None, str | None]:
    """Extract a bearer JWT from the WS subprotocol, or ?token= in development.

    Returns (token, subprotocol_to_echo).
    """
    offered = ws.headers.get("sec-websocket-protocol", "")
    for protocol in (p.strip() for p in offered.split(",")):
        if protocol.startswith("bearer."):
            return protocol[len("bearer."):], protocol

    if settings.environment == "development":
        query_token = ws.query_params.get("token")
        if query_token:
            return query_token, None

    return None, None


async def _reject_websocket(ws: WebSocket, subprotocol: str | None, reason: str):
    """Accept then immediately close so the client gets a clean 1008 close."""
    if subprotocol:
        await ws.accept(subprotocol=subprotocol)
    else:
        await ws.accept()
    await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
