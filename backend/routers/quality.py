"""Quality Management router — NCR lifecycle, weld tracking, quality analytics."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/quality", tags=["quality"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ---- Pydantic Schemas ----

class NCRCreate(BaseModel):
    ncr_number: str
    discipline_id: Optional[int] = None
    sub_system_id: Optional[str] = None
    activity_id: Optional[str] = None
    severity: str = "MINOR"
    category: Optional[str] = None
    description: str
    immediate_action: Optional[str] = None
    raised_by: Optional[str] = None
    target_closeout_date: Optional[date] = None


class NCRUpdate(BaseModel):
    status: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None
    target_closeout_date: Optional[date] = None
    actual_closeout_date: Optional[date] = None
    verified_by: Optional[str] = None


class WeldCreate(BaseModel):
    weld_number: str
    drawing_id: Optional[str] = None
    discipline_id: Optional[int] = None
    weld_type: Optional[str] = None
    joint_type: Optional[str] = None
    diameter_mm: Optional[float] = None
    thickness_mm: Optional[float] = None
    welder_id: Optional[str] = None
    weld_date: Optional[date] = None


class WeldNDTUpdate(BaseModel):
    ndt_method: Optional[str] = None
    ndt_result: Optional[str] = None
    rejection_reason: Optional[str] = None
    repair_count: Optional[int] = None
    status: Optional[str] = None


# ---- NCR Endpoints ----

@router.post("/ncr/{project_id}")
async def create_ncr(project_id: str, data: NCRCreate, db: AsyncSession = Depends(get_db),
                     user: TokenData = Depends(get_current_user)):
    await db.execute(
        text("""INSERT INTO quality_ncr (ncr_id, project_id, ncr_number, discipline_id,
                 sub_system_id, activity_id, severity, category, description,
                 immediate_action, raised_by, target_closeout_date)
                VALUES (gen_random_uuid(), :pid, :num, :did, :ssid, :aid, :sev, :cat,
                        :desc, :action, :by, :tdate)"""),
        {"pid": project_id, "num": data.ncr_number, "did": data.discipline_id,
         "ssid": data.sub_system_id, "aid": data.activity_id, "sev": data.severity,
         "cat": data.category, "desc": data.description, "action": data.immediate_action,
         # raised_by is identity — never trust the request body.
         "by": user.username, "tdate": data.target_closeout_date}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/ncr/{project_id}")
async def list_ncrs(
    project_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    discipline_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT ncr.*, ed.discipline_name, ss.system_code
               FROM quality_ncr ncr
               LEFT JOIN engineering_disciplines ed ON ncr.discipline_id = ed.discipline_id
               LEFT JOIN sub_systems ss ON ncr.sub_system_id = ss.sub_system_id
               WHERE ncr.project_id = :pid"""
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if status:
        query += " AND ncr.status = :st"
        params["st"] = status
    if severity:
        query += " AND ncr.severity = :sev"
        params["sev"] = severity
    if discipline_id:
        query += " AND ncr.discipline_id = :did"
        params["did"] = discipline_id
    query += " ORDER BY CASE ncr.severity WHEN 'CRITICAL' THEN 0 WHEN 'MAJOR' THEN 1 ELSE 2 END, ncr.raised_date DESC"
    query += " LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/ncr/{project_id}/{ncr_id}")
async def update_ncr(project_id: str, ncr_id: str, data: NCRUpdate,
                     db: AsyncSession = Depends(get_db),
                     user: TokenData = Depends(get_current_user)):
    updates = []
    params = {"pid": project_id, "ncr_id": ncr_id}
    for field in ["status", "root_cause", "corrective_action", "preventive_action",
                   "target_closeout_date", "actual_closeout_date"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    # verified_by is an identity field — derive it from the token.
    if data.verified_by is not None:
        updates.append("verified_by = :verified_by")
        params["verified_by"] = user.username
    if not updates:
        return {"status": "no changes"}
    updates.append("updated_at = NOW()")
    await db.execute(
        text(f"UPDATE quality_ncr SET {', '.join(updates)} WHERE ncr_id = :ncr_id AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


@router.get("/ncr-summary/{project_id}")
async def ncr_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    """Aggregated NCR summary for dashboard."""
    by_severity = await db.execute(
        text("""SELECT severity, COUNT(*) AS count,
                       SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed
                FROM quality_ncr WHERE project_id = :pid
                GROUP BY severity ORDER BY severity"""),
        {"pid": project_id}
    )
    by_discipline = await db.execute(
        text("""SELECT COALESCE(ed.discipline_name, 'Unassigned') AS discipline_name, COUNT(*) AS count,
                       SUM(CASE WHEN ncr.status = 'CLOSED' THEN 1 ELSE 0 END) AS closed
                FROM quality_ncr ncr
                LEFT JOIN engineering_disciplines ed ON ncr.discipline_id = ed.discipline_id
                WHERE ncr.project_id = :pid
                GROUP BY ed.discipline_name ORDER BY count DESC"""),
        {"pid": project_id}
    )
    aging = await db.execute(
        text("""SELECT CASE
                    WHEN CURRENT_DATE - raised_date <= 7 THEN '0-7 days'
                    WHEN CURRENT_DATE - raised_date <= 30 THEN '8-30 days'
                    WHEN CURRENT_DATE - raised_date <= 90 THEN '31-90 days'
                    ELSE '>90 days'
                END AS age_bucket, COUNT(*) AS count
                FROM quality_ncr WHERE project_id = :pid AND status != 'CLOSED'
                GROUP BY age_bucket ORDER BY age_bucket"""),
        {"pid": project_id}
    )
    return {
        "by_severity": [dict(r._mapping) for r in by_severity],
        "by_discipline": [dict(r._mapping) for r in by_discipline],
        "aging": [dict(r._mapping) for r in aging],
    }


# ---- Weld Tracking Endpoints ----

@router.post("/welds/{project_id}")
async def create_weld(project_id: str, data: WeldCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("""INSERT INTO weld_tracking (weld_id, project_id, weld_number, drawing_id,
                 discipline_id, weld_type, joint_type, diameter_mm, thickness_mm,
                 welder_id, weld_date)
                VALUES (gen_random_uuid(), :pid, :wnum, :did, :disc, :wtype, :jtype,
                        :dia, :thk, :welder, :wdate)"""),
        {"pid": project_id, "wnum": data.weld_number, "did": data.drawing_id,
         "disc": data.discipline_id, "wtype": data.weld_type, "jtype": data.joint_type,
         "dia": data.diameter_mm, "thk": data.thickness_mm, "welder": data.welder_id,
         "wdate": data.weld_date}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/welds/{project_id}")
async def list_welds(
    project_id: str,
    drawing_id: Optional[str] = None,
    status: Optional[str] = None,
    discipline_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT wt.*, ed.discipline_name, d.drawing_number
               FROM weld_tracking wt
               LEFT JOIN engineering_disciplines ed ON wt.discipline_id = ed.discipline_id
               LEFT JOIN drawings d ON wt.drawing_id = d.drawing_id AND d.project_id = wt.project_id
               WHERE wt.project_id = :pid"""
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if drawing_id:
        query += " AND wt.drawing_id = :did"
        params["did"] = drawing_id
    if status:
        query += " AND wt.status = :st"
        params["st"] = status
    if discipline_id:
        query += " AND wt.discipline_id = :disc"
        params["disc"] = discipline_id
    query += " ORDER BY wt.weld_date DESC LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/welds/{project_id}/{weld_id}")
async def update_weld_ndt(project_id: str, weld_id: str, data: WeldNDTUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "weld_id": weld_id}
    for field in ["ndt_method", "ndt_result", "rejection_reason", "repair_count", "status"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE weld_tracking SET {', '.join(updates)} WHERE weld_id = :weld_id AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


@router.get("/weld-summary/{project_id}")
async def weld_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""SELECT COALESCE(ndt_method, 'NO_NDT') AS ndt_method,
                       COUNT(*) AS total_welds,
                       SUM(CASE WHEN status = 'ACCEPTED' THEN 1 ELSE 0 END) AS accepted,
                       SUM(CASE WHEN status = 'NDT_FAILED' THEN 1 ELSE 0 END) AS failed,
                       ROUND(100.0 * SUM(CASE WHEN status = 'NDT_FAILED' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS rejection_rate_pct
                FROM weld_tracking WHERE project_id = :pid AND ndt_method IS NOT NULL
                GROUP BY ndt_method ORDER BY ndt_method"""),
        {"pid": project_id}
    )
    return [dict(r._mapping) for r in result]
