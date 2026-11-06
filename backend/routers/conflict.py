"""Conflict Detection & Resolution router — cross-phase conflict management.

Route ordering note: FastAPI matches routes in registration order. Static
segments (`/summary`, `/actions`) MUST be registered before the one- and
two-segment dynamic routes (`/{project_id}`, `/{project_id}/{conflict_id}`),
otherwise `GET /api/conflicts/summary/<pid>` resolves as
`GET /api/conflicts/{project_id}` with `project_id="summary"`.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from errors import not_found, bad_request
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ---- Pydantic Schemas ----

class ConflictCreate(BaseModel):
    conflict_type: str
    title: Optional[str] = None
    description: str
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None
    target_entity_type: Optional[str] = None
    target_entity_id: Optional[str] = None
    severity: str = "MEDIUM"
    detected_by_agent: bool = False
    ai_confidence: Optional[float] = None
    ai_recommendation: Optional[str] = None


class ConflictUpdate(BaseModel):
    status: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None  # ignored — identity comes from the token


class ConflictActionCreate(BaseModel):
    conflict_id: str
    action_description: str
    assigned_to: Optional[str] = None
    target_date: Optional[date] = None


class ConflictActionUpdate(BaseModel):
    status: Optional[str] = None
    completion_date: Optional[date] = None


# ---- Static routes (must precede dynamic routes) ----

@router.get("/summary/{project_id}")
async def conflict_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    """Dashboard summary of all conflicts."""
    by_type = await db.execute(
        text("""SELECT conflict_type, COUNT(*) AS count,
                       SUM(CASE WHEN status IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END) AS resolved
                FROM conflicts WHERE project_id = :pid
                GROUP BY conflict_type ORDER BY count DESC"""),
        {"pid": project_id}
    )
    by_severity = await db.execute(
        text("""SELECT severity, COUNT(*) AS count,
                       SUM(CASE WHEN status IN ('DETECTED', 'ACKNOWLEDGED', 'IN_RESOLUTION') THEN 1 ELSE 0 END) AS open
                FROM conflicts WHERE project_id = :pid
                GROUP BY severity ORDER BY severity"""),
        {"pid": project_id}
    )
    ai_stats = await db.execute(
        text("""SELECT detected_by_agent, COUNT(*) AS count,
                       ROUND(AVG(COALESCE(ai_confidence, 0))::numeric, 2) AS avg_confidence
                FROM conflicts WHERE project_id = :pid
                GROUP BY detected_by_agent"""),
        {"pid": project_id}
    )
    return {
        "by_type": [dict(r._mapping) for r in by_type],
        "by_severity": [dict(r._mapping) for r in by_severity],
        "ai_detection_stats": [dict(r._mapping) for r in ai_stats],
    }


# ---- Conflict Actions (static prefix `/actions`) ----

@router.post("/actions/{project_id}")
async def create_action(project_id: str, data: ConflictActionCreate, db: AsyncSession = Depends(get_db)):
    # Parent conflict must belong to the path project.
    parent = await db.execute(
        text("SELECT conflict_id FROM conflicts WHERE conflict_id = :cid AND project_id = :pid"),
        {"cid": data.conflict_id, "pid": project_id},
    )
    if parent.fetchone() is None:
        raise not_found("Conflict", data.conflict_id)

    await db.execute(
        text("""INSERT INTO conflict_actions (action_id, conflict_id, action_description, assigned_to, target_date)
                VALUES (gen_random_uuid(), :cid, :desc, :assign, :tdate)"""),
        {"cid": data.conflict_id, "desc": data.action_description,
         "assign": data.assigned_to, "tdate": data.target_date}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/actions/{project_id}")
async def list_actions(project_id: str, conflict_id: Optional[str] = None,
                       assigned_to: Optional[str] = None,
                       page: int = 1, page_size: int = 50,
                       db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT ca.*, c.title AS conflict_title, c.conflict_type, c.severity
               FROM conflict_actions ca
               JOIN conflicts c ON ca.conflict_id = c.conflict_id
               WHERE c.project_id = :pid"""
    params = {"pid": project_id}
    if conflict_id:
        query += " AND ca.conflict_id = :cid"
        params["cid"] = conflict_id
    if assigned_to:
        query += " AND ca.assigned_to = :assign"
        params["assign"] = assigned_to
    query += " ORDER BY ca.target_date LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/actions/{project_id}/{action_id}")
async def update_action(project_id: str, action_id: str, data: ConflictActionUpdate,
                        db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "aid": action_id}
    for field in ["status", "completion_date"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE conflict_actions SET {', '.join(updates)} WHERE action_id = :aid "
             "AND conflict_id IN (SELECT conflict_id FROM conflicts WHERE project_id = :pid)"),
        params
    )
    await db.commit()
    return {"status": "updated"}


# ---- Conflicts ----

@router.post("/{project_id}")
async def create_conflict(project_id: str, data: ConflictCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""INSERT INTO conflicts (conflict_id, project_id, conflict_type, title, description,
                 source_entity_type, source_entity_id, target_entity_type, target_entity_id,
                 severity, detected_by_agent, ai_confidence, ai_recommendation)
                VALUES (gen_random_uuid(), :pid, :ctype, :title, :desc, :stype, :sid,
                        :ttype, :tid, :sev, :agent, :conf, :rec)
                RETURNING conflict_id"""),
        {"pid": project_id, "ctype": data.conflict_type, "title": data.title,
         "desc": data.description, "stype": data.source_entity_type,
         "sid": data.source_entity_id, "ttype": data.target_entity_type,
         "tid": data.target_entity_id, "sev": data.severity,
         "agent": data.detected_by_agent, "conf": data.ai_confidence,
         "rec": data.ai_recommendation}
    )
    await db.commit()
    return {"conflict_id": str(result.scalar()), "status": "created"}


@router.get("/{project_id}")
async def list_conflicts(
    project_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    conflict_type: Optional[str] = None,
    detected_by_agent: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT c.*, COALESCE(ca.action_count, 0) AS open_actions
               FROM conflicts c
               LEFT JOIN (
                   SELECT conflict_id, COUNT(*) AS action_count
                   FROM conflict_actions WHERE status != 'COMPLETED' AND status != 'CANCELLED'
                   GROUP BY conflict_id
               ) ca ON c.conflict_id = ca.conflict_id
               WHERE c.project_id = :pid"""
    params = {"pid": project_id}
    if status:
        query += " AND c.status = :st"
        params["st"] = status
    if severity:
        query += " AND c.severity = :sev"
        params["sev"] = severity
    if conflict_type:
        query += " AND c.conflict_type = :ctype"
        params["ctype"] = conflict_type
    if detected_by_agent is not None:
        query += " AND c.detected_by_agent = :agent"
        params["agent"] = detected_by_agent
    query += (" ORDER BY CASE c.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END, "
              "c.created_at DESC LIMIT :limit OFFSET :offset")
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.get("/{project_id}/{conflict_id}")
async def get_conflict(project_id: str, conflict_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM conflicts WHERE conflict_id = :cid AND project_id = :pid"),
        {"cid": conflict_id, "pid": project_id}
    )
    row = result.fetchone()
    if not row:
        raise not_found("Conflict", conflict_id)

    actions = await db.execute(
        text("SELECT * FROM conflict_actions WHERE conflict_id = :cid ORDER BY target_date"),
        {"cid": conflict_id}
    )
    return {"conflict": dict(row._mapping), "actions": [dict(r._mapping) for r in actions]}


@router.patch("/{project_id}/{conflict_id}")
async def update_conflict(project_id: str, conflict_id: str, data: ConflictUpdate,
                          db: AsyncSession = Depends(get_db),
                          user: TokenData = Depends(get_current_user)):
    updates = []
    params = {"pid": project_id, "cid": conflict_id}
    for field in ["status", "resolution_notes"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if data.status == "RESOLVED":
        updates.append("resolved_at = NOW()")
        # Resolution identity is derived from the token, never the body.
        updates.append("resolved_by = :resolved_by")
        params["resolved_by"] = user.username
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE conflicts SET {', '.join(updates)} WHERE conflict_id = :cid AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}
