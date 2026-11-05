"""Single source of truth for the platform outcome and GATE_G.

Primary KPI: `governed_completion_rate` — completed runs / started runs.
Guardrails (all must hold to expand autonomy):
  * zero unsafe approvals (self-approval or after the review deadline),
  * p95 run duration <= 120 seconds,
  * cost per completed run <= $1.00.

GATE_G is expansion-only: a failure holds autonomy expansion, it does not block a
release. The contract below is the authoritative definition; docs/KPI-CONTRACT.md
describes it, it is not duplicated in configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.human_review import HumanReviewDecision
from app.models.workflow import WorkflowRun


@dataclass(frozen=True)
class KpiContract:
    name: str = "governed_completion_rate"
    target: float = 0.80
    min_sample_size: int = 5
    max_p95_seconds: float = 120.0
    max_cost_per_completed_run_usd: float = 1.0
    window_hours: int = 24


KPI_CONTRACT = KpiContract()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 2)


async def compute_kpi(
    session: AsyncSession,
    *,
    window_hours: int | None = None,
) -> dict[str, Any]:
    contract = KPI_CONTRACT
    hours = window_hours or contract.window_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    runs = list(
        (
            await session.execute(
                select(WorkflowRun).where(WorkflowRun.created_at >= cutoff)
            )
        )
        .scalars()
        .all()
    )
    total = len(runs)
    completed = [run for run in runs if run.current_status == "completed"]
    failed = [run for run in runs if run.current_status == "failed"]

    durations = [
        (_aware(run.completed_at) - _aware(run.created_at)).total_seconds()
        for run in completed
        if run.completed_at is not None
    ]
    p95 = _percentile(durations, 0.95)
    total_cost = sum(float(run.cost_usd or 0) for run in completed)
    cost_per_run = round(total_cost / len(completed), 4) if completed else 0.0
    completion_rate = round(len(completed) / total, 4) if total else 0.0

    decisions = list(
        (
            await session.execute(
                select(HumanReviewDecision, WorkflowRun)
                .join(WorkflowRun, HumanReviewDecision.workflow_id == WorkflowRun.id)
                .where(WorkflowRun.created_at >= cutoff)
            )
        ).all()
    )
    unsafe_approvals = 0
    for decision, run in decisions:
        if decision.reviewer_id == run.user_id:
            unsafe_approvals += 1
            continue
        if run.review_deadline is not None and _aware(decision.created_at) > _aware(
            run.review_deadline
        ):
            unsafe_approvals += 1

    reasons: list[str] = []
    if total < contract.min_sample_size:
        reasons.append(
            f"insufficient sample: {total} runs, need {contract.min_sample_size}"
        )
    if completion_rate < contract.target:
        reasons.append(
            f"completion rate {completion_rate:.0%} below target {contract.target:.0%}"
        )
    if unsafe_approvals > 0:
        reasons.append(f"{unsafe_approvals} unsafe approval(s); integrity guardrail is zero")
    if p95 is not None and p95 > contract.max_p95_seconds:
        reasons.append(f"p95 duration {p95}s above {contract.max_p95_seconds}s")
    if cost_per_run > contract.max_cost_per_completed_run_usd:
        reasons.append(
            f"cost per completed run ${cost_per_run} above "
            f"${contract.max_cost_per_completed_run_usd}"
        )

    expansion_allowed = not reasons
    return {
        "contract": asdict(contract),
        "window_hours": hours,
        "metrics": {
            "total_runs": total,
            "completed_runs": len(completed),
            "failed_runs": len(failed),
            "completion_rate": completion_rate,
            "p95_duration_seconds": p95,
            "cost_per_completed_run_usd": cost_per_run,
            "unsafe_approvals": unsafe_approvals,
        },
        "gate_g": {
            "status": "pass" if expansion_allowed else "hold",
            "expansion_allowed": expansion_allowed,
            "reasons": reasons,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }