from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.database import check_database_health

router = APIRouter()


async def check_redis_health() -> bool:
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
        return True
    except Exception:
        return False
    finally:
        await client.aclose()


@router.get("", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(response: Response) -> dict[str, object]:
    """Readiness requires the database; Redis is reported but non-fatal.

    A Redis outage degrades realtime fan-out to local-only, so it must not evict
    every pod from the service. A database outage must.
    """
    database_ok = await check_database_health()
    redis_ok = await check_redis_health()
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if database_ok else "degraded",
        "checks": {"database": database_ok, "redis": redis_ok},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }