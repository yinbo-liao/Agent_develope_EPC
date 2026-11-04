from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.models.workflow import WorkflowRun
from app.workflows.human_review import HumanReviewError, process_human_decision
from app.workflows.state import WorkflowDecisionRequest, WorkflowDetail

router = APIRouter(prefix="/human-review", tags=["Human Review"])

REVIEWER = dict[str, object]


@router.post("/decide", response_model=WorkflowDetail, status_code=status.HTTP_200_OK)
async def decide_workflow(
    payload: WorkflowDecisionRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: REVIEWER = Depends(require_role("reviewer", "admin")),
) -> WorkflowDetail:
    result = await session.execute(select(WorkflowRun).where(WorkflowRun.id == payload.task_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        updated = await process_human_decision(
            session=session,
            task_id=payload.task_id,
            reviewer_id=str(current_user["user_id"]),
            decision=payload.decision,
            comment=payload.comment,
        )
    except HumanReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return WorkflowDetail.model_validate(updated, from_attributes=True)