"""
Observability Middleware — Correlation IDs, Request Logging, Metrics Collection.

Adds:
- ``X-Correlation-ID`` on every response. An incoming header is honoured only
  when it is a well-formed UUID; otherwise a fresh UUID4 hex is generated.
- ``correlation_id`` context variable (``get_correlation_id()``) so application
  code and log records emitted deep in the stack can attach the same ID.
- Request count + latency Prometheus metrics, labelled by the routed endpoint
  *template* (``/api/engineering/projects/{project_id}/...``) rather than the
  raw path, preventing unbounded label cardinality from UUIDs/IDs.
- Structured request logging.

Never logs request bodies or the Authorization / Cookie headers.
Health-check and metrics-scrape requests are excluded from access logging and
metric collection to keep signal-to-noise high.
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("fpso.api")

# ---------------------------------------------------------------------------
# Correlation ID context
# ---------------------------------------------------------------------------
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Paths that are polled constantly by probes and scrapers. They still get a
# correlation header but do not generate access logs or metrics.
_SKIP_ACCESS_PATHS = frozenset({
    "/health",
    "/health/live",
    "/health/ready",
    "/healthz",
    "/live",
    "/ready",
    "/metrics",
    "/favicon.ico",
})


def get_correlation_id() -> Optional[str]:
    """Return the correlation ID for the current request context, if any."""
    return correlation_id_var.get()


def _normalize_correlation_id(value: Optional[str]) -> Optional[str]:
    """Return a canonical UUID string iff *value* is a valid UUID, else None."""
    if not value:
        return None
    candidate = value.strip()
    if not _UUID_RE.match(candidate):
        return None
    try:
        # Canonicalises case/hyphenation and rejects impossible values.
        return str(uuid.UUID(candidate))
    except (ValueError, AttributeError):
        return None


class CorrelationIdFilter(logging.Filter):
    """Attach the active correlation ID to records that do not carry one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", None):
            correlation_id = correlation_id_var.get()
            if correlation_id:
                record.correlation_id = correlation_id
        return True


def _install_correlation_filter() -> None:
    """Install the filter on every root handler (handler filters see all logs)."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
            handler.addFilter(CorrelationIdFilter())
    if not root_logger.handlers:
        # setup_logging() normally runs first; fall back to the root logger so
        # the filter still applies once a handler is attached later.
        if not any(isinstance(f, CorrelationIdFilter) for f in root_logger.filters):
            root_logger.addFilter(CorrelationIdFilter())


# ---------------------------------------------------------------------------
# Prometheus metrics (lazy, optional)
# ---------------------------------------------------------------------------
_metrics_available = False
REQUEST_COUNT = None
REQUEST_LATENCY = None


def _init_metrics() -> None:
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
        # prometheus_client is optional in minimal installs.
        logger.warning("prometheus_client unavailable — request metrics disabled")
    except ValueError:
        # Duplicate registration (module reload / test double-import).
        logger.warning("Prometheus metrics already registered — reusing disabled")


_init_metrics()


def _route_template(request: Request) -> str:
    """Best-effort low-cardinality label for the request.

    Starlette stores the matched route in ``scope["route"]`` after routing.
    Using its path pattern (``/api/x/{id}``) avoids one label per UUID.
    """
    route = request.scope.get("route")
    template = getattr(route, "path", None) if route is not None else None
    if template:
        return template
    # No matched route (404, or routing did not complete): do not use the raw
    # path, which may contain IDs; classify it instead.
    return "<unmatched>"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Injects correlation IDs, logs requests, collects metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = _normalize_correlation_id(
            request.headers.get("X-Correlation-ID")
        ) or uuid.uuid4().hex

        path = request.url.path
        skip_access = path in _SKIP_ACCESS_PATHS

        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        status_code = 500
        response: Optional[Response] = None

        if not skip_access:
            logger.info(
                "request_start",
                extra={
                    "method": request.method,
                    "path": path,
                    "correlation_id": correlation_id,
                    "client": request.client.host if request.client else "unknown",
                },
            )

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # Log with the correlation ID, then let the app's exception
            # handlers / server produce the response.
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": path,
                    "correlation_id": correlation_id,
                },
            )
            raise
        finally:
            elapsed = time.perf_counter() - start

            if response is not None:
                response.headers.setdefault("X-Correlation-ID", correlation_id)

            if not skip_access and _metrics_available:
                endpoint = _route_template(request)
                try:
                    REQUEST_COUNT.labels(
                        method=request.method,
                        endpoint=endpoint,
                        status=status_code,
                    ).inc()
                    REQUEST_LATENCY.labels(
                        method=request.method,
                        endpoint=endpoint,
                    ).observe(elapsed)
                except Exception:  # pragma: no cover - metrics must never break requests
                    logger.debug("metric emission failed", exc_info=True)

            if not skip_access:
                logger.info(
                    "request_complete",
                    extra={
                        "method": request.method,
                        "path": path,
                        "route": _route_template(request),
                        "status": status_code,
                        "duration_ms": round(elapsed * 1000, 2),
                        "correlation_id": correlation_id,
                    },
                )

            correlation_id_var.reset(token)


def add_observability_middleware(app) -> None:
    """Add correlation ID + metrics middleware to FastAPI app."""
    _install_correlation_filter()
    app.add_middleware(ObservabilityMiddleware)
    logger.info("Observability middleware enabled (correlation IDs + metrics)")
