"""Human-review decision processing with state, role and deadline guards.

The API layer authenticates the caller and requires a reviewer role; this module
enforces the run-level invariants so no other caller can bypass them:

* the run must be waiting in REVIEWING state,
* it must not already have a decision,
* the reviewer must not be the requester (no self-approval),
* the review deadline must not have passed,
* exactly one decision is recorded and applied.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import review_state_hash
from app.core.websocket_manager import ws_manager
from app.models.human_review import HumanReviewDecision
from app.models.workflow import WorkflowRun
from app.services.audit import append_audit
from app.workflows.nodes import human_review_node
from app.workflows.state import WorkflowStatus


class HumanReviewError(Exception):
    """Domain error mapped to an HTTP status by the API layer."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def process_human_decision(
    session: AsyncSession,
    task_id: str,
    reviewer_id: str,
    decision: str,
    comment: str = "",
) -> WorkflowRun:
    result = await session.execute(select(WorkflowRun).where(WorkflowRun.id == task_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HumanReviewError("Workflow not found", 404)

    if run.current_status != WorkflowStatus.REVIEWING.value or not run.is_human_review_needed:
        raise HumanReviewError("Workflow is not awaiting human review", 409)
    if run.human_decision is not None:
        raise HumanReviewError("Workflow already has a decision", 409)
    if reviewer_id == run.user_id:
        raise HumanReviewError("A reviewer cannot approve their own workflow", 403)
    if run.review_deadline is not None and datetime.now(timezone.utc) > _aware(run.review_deadline):
        raise HumanReviewError("The review deadline has passed", 409)

    current_state_hash = review_state_hash(run)
    if run.review_state_hash is not None and run.review_state_hash != current_state_hash:
        raise HumanReviewError("Workflow state changed since review began", 409)

    run.human_decision = decision
    run.human_comment = comment
    run.updated_at = datetime.now(timezone.utc)
    run.is_human_review_needed = False

    session.add(
        HumanReviewDecision(
            workflow_id=task_id,
            reviewer_id=reviewer_id,
            decision=decision,
            comment=comment,
        )
    )

    updates = await human_review_node(run)
    for key, value in updates.items():
        setattr(run, key, value)

    await append_audit(
        session,
        actor=reviewer_id,
        action="human_review.decide",
        resource=task_id,
        payload={"decision": decision, "state_hash": current_state_hash},
    )
    await session.commit()
    await session.refresh(run)
    await ws_manager.broadcast(
        task_id,
        {
            "type": "human_review",
            "status": run.current_status,
            "currentStep": run.current_step,
            "decision": run.human_decision,
            "comment": run.human_comment,
            "isHumanReviewNeeded": run.is_human_review_needed,
            "finalResponse": run.final_response,
            "error": run.error_info,
        },
    )
    return run
