from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import MCPToolCallAudit
from app.models.workflow import WorkflowRun

logger = logging.getLogger(__name__)


async def analyze_workflow_patterns(
    session: AsyncSession,
    *,
    hours: int = 24,
) -> dict[str, Any]:
    """Analyze recent workflow patterns and return actionable insights.

    Reads from workflow_runs, human_review_decisions, and MCP audit tables.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Workflow statistics
    total_result = await session.execute(
        select(func.count()).select_from(WorkflowRun).where(WorkflowRun.created_at >= cutoff)
    )
    total = total_result.scalar() or 0

    failed_result = await session.execute(
        select(func.count())
        .select_from(WorkflowRun)
        .where(
            WorkflowRun.created_at >= cutoff,
            WorkflowRun.current_status == "failed",
        )
    )
    failed = failed_result.scalar() or 0

    # Risk accuracy: how many CRITICAL workflows were approved by humans?
    critical_approved_result = await session.execute(
        select(func.count())
        .select_from(WorkflowRun)
        .where(
            WorkflowRun.created_at >= cutoff,
            WorkflowRun.risk_level == "critical",
            WorkflowRun.human_decision == "approved",
        )
    )
    false_positives = critical_approved_result.scalar() or 0

    total_critical_result = await session.execute(
        select(func.count())
        .select_from(WorkflowRun)
        .where(
            WorkflowRun.created_at >= cutoff,
            WorkflowRun.risk_level == "critical",
        )
    )
    total_critical = total_critical_result.scalar() or 1

    false_positive_rate = round(false_positives / total_critical * 100, 1)

    # Common failure patterns
    failed_result_detail = await session.execute(
        select(WorkflowRun.error_info)
        .where(
            WorkflowRun.created_at >= cutoff,
            WorkflowRun.current_status == "failed",
            WorkflowRun.error_info.isnot(None),
        )
    )
    errors = [row[0] for row in failed_result_detail.fetchall() if row[0]]
    error_keywords: Counter[str] = Counter()
    for error in errors:
        for keyword in ("timeout", "circuit", "budget", "connection", "validation"):
            if keyword in str(error).lower():
                error_keywords[keyword] += 1

    # MCP tool call analysis
    mcp_total_result = await session.execute(
        select(func.count()).select_from(MCPToolCallAudit).where(MCPToolCallAudit.created_at >= cutoff)
    )
    mcp_total = mcp_total_result.scalar() or 0

    mcp_error_result = await session.execute(
        select(func.count())
        .select_from(MCPToolCallAudit)
        .where(
            MCPToolCallAudit.created_at >= cutoff,
            MCPToolCallAudit.status == "error",
        )
    )
    mcp_errors = mcp_error_result.scalar() or 0

    # Build insights report
    insights: list[dict[str, Any]] = []

    if total > 0 and failed > 0:
        fail_rate = round(failed / total * 100, 1)
        insights.append({
            "type": "reliability",
            "severity": "warning" if fail_rate > 10 else "info",
            "message": f"Workflow failure rate: {fail_rate}% ({failed}/{total}) in the last {hours}h",
            "metric": "failure_rate",
            "value": fail_rate,
        })

    if false_positive_rate > 30:
        insights.append({
            "type": "risk_accuracy",
            "severity": "warning",
            "message": (
                f"Risk false positive rate: {false_positive_rate}% "
                f"({false_positives}/{total_critical} CRITICAL workflows approved). "
                f"Consider adjusting risk thresholds."
            ),
            "action": "reduce_critical_bias",
        })

    most_common_error = error_keywords.most_common(1)
    if most_common_error:
        keyword, count = most_common_error[0]
        insights.append({
            "type": "common_failure",
            "severity": "info",
            "message": f"Most common failure pattern: '{keyword}' ({count} occurrences)",
            "pattern": keyword,
            "count": count,
        })

    if mcp_total > 0 and mcp_errors > 0:
        mcp_error_rate = round(mcp_errors / mcp_total * 100, 1)
        insights.append({
            "type": "mcp_reliability",
            "severity": "warning" if mcp_error_rate > 10 else "info",
            "message": f"MCP tool error rate: {mcp_error_rate}% ({mcp_errors}/{mcp_total})",
        })

    return {
        "period_hours": hours,
        "workflows": {"total": total, "failed": failed},
        "risk_accuracy": {
            "false_positives": false_positives,
            "total_critical": total_critical,
            "false_positive_rate_pct": false_positive_rate,
        },
        "common_errors": dict(error_keywords.most_common(5)),
        "mcp_tools": {"total_calls": mcp_total, "errors": mcp_errors},
        "insights": insights,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
