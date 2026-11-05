"""
Observability Middleware — Correlation IDs, Request Logging, Metrics Collection.

Adds:
- X-Correlation-ID header (generated if not provided, propagated to responses)
- Request count + latency Prometheus metrics
- Structured request logging
"""

import time
import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("fpso.api")

# Prometheus metrics (lazy init)
_metrics_available = False
REQUEST_COUNT = None
REQUEST_LATENCY = None


def _init_metrics():
    global _metrics_available, REQUEST_COUNT, REQUEST_LATENCY
    try:
        from prometheus_client import Counter, Histogram
        REQUEST_COUNT = Counter(
            "fpso_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
        )
        REQUEST_LATENCY = Histogram(
            "fpso_http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
        _metrics_available = True
    except ImportError:
        pass


_init_metrics()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Injects correlation IDs, logs requests, collects metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Correlation ID
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4())[:8])

        # Timing
        start = time.perf_counter()

        # Log request
        logger.info(
            "request_start",
            extra={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
                "client": request.client.host if request.client else "unknown",
            },
        )

        response = await call_next(request)

        # Latency
        elapsed = time.perf_counter() - start

        # Add correlation ID to response
        response.headers["X-Correlation-ID"] = correlation_id

        # Emit metrics
        if _metrics_available:
            endpoint = request.url.path
            # Normalize path params for metric cardinality
            for segment in request.path_params.values():
                endpoint = endpoint.replace(str(segment), "{param}")
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=endpoint,
                status=response.status_code,
            ).inc()
            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(elapsed)

        logger.info(
            "request_complete",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
                "correlation_id": correlation_id,
            },
        )

        return response


def add_observability_middleware(app):
    """Add correlation ID + metrics middleware to FastAPI app."""
    app.add_middleware(ObservabilityMiddleware)
    logger.info("Observability middleware enabled (correlation IDs + metrics)")
