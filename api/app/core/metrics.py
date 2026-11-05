from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency in local environments
    from prometheus_client import Counter, Gauge
except ModuleNotFoundError:  # pragma: no cover
    Counter = None  # type: ignore[assignment]

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    Instrumentator = None  # type: ignore[assignment]

llm_cost_usd_total = Counter(  # type: ignore[misc]
    "llm_cost_usd_total",
    "Estimated total LLM cost in USD",
    ["model"],
) if Counter is not None else None

mcp_tool_calls_total = Counter(  # type: ignore[misc]
    "mcp_tool_calls_total",
    "Total MCP tool calls",
    ["server", "tool", "status"],
) if Counter is not None else None

workflow_jobs_total = Counter(  # type: ignore[misc]
    "workflow_jobs_total",
    "Workflow job state transitions",
    ["status"],
) if Counter is not None else None

workflow_job_queue_depth = Gauge(  # type: ignore[misc]
    "workflow_job_queue_depth",
    "Workflow jobs currently waiting to be claimed",
) if Gauge is not None else None


def setup_metrics(app) -> Any:
    if Instrumentator is None:
        return None

    instrumentator = Instrumentator(excluded_handlers=["/health", "/metrics"])
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    return instrumentator


def track_llm_cost(model: str, cost_usd: float) -> None:
    if llm_cost_usd_total is None:
        return
    llm_cost_usd_total.labels(model=model).inc(cost_usd)


def track_mcp_call(server: str, tool: str, status: str) -> None:
    if mcp_tool_calls_total is None:
        return
    mcp_tool_calls_total.labels(server=server, tool=tool, status=status).inc()

def track_job_status(status: str) -> None:
    if workflow_jobs_total is None:
        return
    workflow_jobs_total.labels(status=status).inc()


def set_job_queue_depth(depth: int) -> None:
    if workflow_job_queue_depth is None:
        return
    workflow_job_queue_depth.set(depth)
