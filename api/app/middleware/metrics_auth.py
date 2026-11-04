"""Protect the Prometheus endpoint.

Metrics can leak route names, traffic volume and error patterns. In production the
endpoint is hidden unless METRICS_TOKEN is configured, in which case the scraper
must present it. In development it stays open for convenience.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

METRICS_PATH = "/metrics"
METRICS_HEADER = "x-metrics-token"


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == METRICS_PATH:
            expected = settings.METRICS_TOKEN
            if expected is None:
                if settings.is_production:
                    return Response(status_code=404)
            elif request.headers.get(METRICS_HEADER) != expected:
                return Response(status_code=401)
        return await call_next(request)