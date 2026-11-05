"""Feedback Loop router — cross-phase feedback for continuous improvement."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# ---- Pydantic Schemas ----

class FeedbackCreate(BaseModel):
    source_stage: str
    target_stage: str
    feedback_type: str
    reference_number: Optional[str] = None
    description: str
    impact_level: str = "MEDIUM"
    created_by: Optional[str] = None


class FeedbackUpdate(BaseModel):
    is_actioned: Optional[bool] = None
    actioned_by: Optional[str] = None
    closure_notes: Optional[str] = None
    impact_assessment: Optional[str] = None


# ---- Feedback Items ----

@router.post("/{project_id}")
async def create_feedback(project_id: str, data: FeedbackCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("""INSERT INTO feedback_loop (feedback_id, project_id, source_stage, target_stage,
                 feedback_type, reference_number, description, impact_level, created_by)
                VALUES (gen_random_uuid(), :pid, :src, :tgt, :ftype, :ref, :desc, :impact, :by)"""),
        {"pid": project_id, "src": data.source_stage, "tgt": data.target_stage,
         "ftype": data.feedback_type, "ref": data.reference_number,
         "desc": data.description, "impact": data.impact_level, "by": data.created_by}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/{project_id}")
async def list_feedback(
    project_id: str,
    source_stage: Optional[str] = None,
    target_stage: Optional[str] = None,
    is_actioned: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    query = "SELECT * FROM feedback_loop WHERE project_id = :pid"
    params = {"pid": project_id}
    if source_stage:
        query += " AND source_stage = :src"
        params["src"] = source_stage
    if target_stage:
        query += " AND target_stage = :tgt"
        params["tgt"] = target_stage
    if is_actioned is not None:
        query += " AND is_actioned = :acted"
        params["acted"] = is_actioned
    query += " ORDER BY created_at DESC"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/{project_id}/{feedback_id}")
async def update_feedback(project_id: str, feedback_id: str, data: FeedbackUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "fid": feedback_id}
    for field in ["is_actioned", "actioned_by", "closure_notes", "impact_assessment"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if data.is_actioned:
        updates.append("actioned_date = NOW()")
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE feedback_loop SET {', '.join(updates)} WHERE feedback_id = :fid AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


@router.get("/summary/{project_id}")
async def feedback_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    """Feedback loop performance metrics."""
    by_direction = await db.execute(
        text("""SELECT source_stage || '→' || target_stage AS direction, COUNT(*) AS count,
                       SUM(CASE WHEN is_actioned THEN 1 ELSE 0 END) AS actioned
                FROM feedback_loop WHERE project_id = :pid
                GROUP BY source_stage, target_stage ORDER BY count DESC"""),
        {"pid": project_id}
    )
    by_type = await db.execute(
        text("""SELECT feedback_type, COUNT(*) AS count,
                       SUM(CASE WHEN is_actioned THEN 1 ELSE 0 END) AS actioned
                FROM feedback_loop WHERE project_id = :pid
                GROUP BY feedback_type ORDER BY count DESC"""),
        {"pid": project_id}
    )
    aging = await db.execute(
        text("""SELECT CASE
                    WHEN CURRENT_DATE - created_at::DATE <= 7 THEN '0-7 days'
                    WHEN CURRENT_DATE - created_at::DATE <= 30 THEN '8-30 days'
                    ELSE '>30 days'
                END AS age_bucket,
                COUNT(*) AS count
                FROM feedback_loop WHERE project_id = :pid AND is_actioned = FALSE
                GROUP BY age_bucket"""),
        {"pid": project_id}
    )
    return {
        "by_direction": [dict(r._mapping) for r in by_direction],
        "by_type": [dict(r._mapping) for r in by_type],
        "aging": [dict(r._mapping) for r in aging],
    }


@router.get("/stale/{project_id}")
async def stale_feedback(project_id: str, days_stale: int = 14, db: AsyncSession = Depends(get_db)):
    """List unactioned feedback older than N days."""
    result = await db.execute(
        text("""SELECT * FROM feedback_loop
                WHERE project_id = :pid AND is_actioned = FALSE
                  AND created_at < CURRENT_DATE - :days::INT
                ORDER BY created_at"""),
        {"pid": project_id, "days": days_stale}
    )
    return [dict(r._mapping) for r in result]
