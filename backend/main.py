from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import settings
from websocket import manager
from services.alert_service import AlertService
from auth import decode_token
from db import init_pool, close_pool, get_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    pool = await get_pool()
    AlertService.set_pool(pool)
    yield
    await close_pool()


app = FastAPI(title="FPSO EPC Project Control System", version="4.0", lifespan=lifespan)

# Standardized error handling
from errors import register_error_handlers
register_error_handlers(app)

# CORS (tightened from Phase 1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-ID"],
)


# Rate Limiting
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    limiter = None

# Structured logging
from logging_config import setup_logging
setup_logging()

# Observability (correlation IDs, metrics, request logging)
from middleware.observability import add_observability_middleware
add_observability_middleware(app)

# CSRF Protection
from middleware.csrf import add_csrf_middleware
add_csrf_middleware(app)


from routers import engineering, procurement, construction, inspection, reports, equipment
from routers import completion, commissioning, quality, safety, training, planning, conflict, stagegate, feedback, ai
from routers import traceability_router, auth_router

# Register AI function tools on startup (import triggers @tool_registry.register decorators)
import services.tools.query_tools  # noqa: F401

app.include_router(auth_router.router)
app.include_router(engineering.router)
app.include_router(procurement.router)
app.include_router(construction.router)
app.include_router(inspection.router)
app.include_router(reports.router)
app.include_router(equipment.router)
app.include_router(completion.router)
app.include_router(commissioning.router)
app.include_router(quality.router)
app.include_router(safety.router)
app.include_router(training.router)
app.include_router(planning.router)
app.include_router(conflict.router)
app.include_router(stagegate.router)
app.include_router(feedback.router)
app.include_router(ai.router)
app.include_router(traceability_router.router)


@app.get("/health")
async def health():
    """Health check with dependency verification."""
    status_info = {"status": "healthy", "checks": {}}

    # Check database
    try:
        db_pool = await get_pool()
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        status_info["checks"]["database"] = "healthy"
    except Exception as e:
        status_info["checks"]["database"] = f"unhealthy: {e}"
        status_info["status"] = "degraded"

    # Check Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        status_info["checks"]["redis"] = "healthy"
    except Exception as e:
        status_info["checks"]["redis"] = f"unavailable: {e}"

    return status_info


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from fastapi.responses import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        return {"error": "prometheus_client not installed"}


@app.websocket("/ws/{project_id}")
async def websocket_endpoint(ws: WebSocket, project_id: str, token: str = Query(None)):
    # Authenticate WebSocket connections
    if not settings.secret_key or settings.secret_key == "change-me-in-production":
        pass  # Dev mode — no auth required
    elif not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return
    else:
        token_data = decode_token(token)
        if token_data is None:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
            return
    await manager.connect(ws, project_id)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, project_id)
    except Exception:
        manager.disconnect(ws, project_id)


from auth import get_current_user, require_role
from auth import TokenData


@app.post("/api/alerts/generate/{project_id}")
async def trigger_alert_generation(project_id: str, user: TokenData = Depends(require_role("admin", "project_manager"))):
    db_pool = await get_pool()
    await AlertService.generate_alerts(project_id, db_pool)
    return {"status": "alerts generated"}


@app.get("/api/alerts/{project_id}")
async def get_alerts(project_id: str, severity: str | None = None, user: TokenData = Depends(get_current_user)):
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
