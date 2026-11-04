from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.services.feedback_analyzer import analyze_workflow_patterns

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/insights", status_code=status.HTTP_200_OK)
async def get_insights(
    hours: int = Query(default=24, ge=1, le=720),
    session: AsyncSession = Depends(get_db_session),
    current_user: dict[str, object] = Depends(require_role("admin")),
) -> dict[str, object]:
    """Return workflow pattern analysis and improvement insights.

    Requires admin role. Analyzes workflow patterns over the specified
    time window and returns actionable insights.
    """
    return await analyze_workflow_patterns(session, hours=hours)
