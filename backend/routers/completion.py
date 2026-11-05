"""System Completion router — sub-systems, punch list management."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from errors import not_found

router = APIRouter(prefix="/api/completion", tags=["completion"])


# ---- Pydantic Schemas ----

class SubSystemCreate(BaseModel):
    system_code: str
    system_name: str
    parent_system_id: Optional[str] = None
    discipline_id: Optional[int] = None
    area_code: Optional[str] = None
    planned_mc_date: Optional[date] = None
    responsible_engineer: Optional[str] = None
    notes: Optional[str] = None


class SubSystemUpdate(BaseModel):
    system_name: Optional[str] = None
    completion_status: Optional[str] = None
    planned_mc_date: Optional[date] = None
    actual_mc_date: Optional[date] = None
    handover_date: Optional[date] = None
    responsible_engineer: Optional[str] = None
    notes: Optional[str] = None


class PunchItemCreate(BaseModel):
    sub_system_id: str
    category: str = "B"
    discipline_id: Optional[int] = None
    area_code: Optional[str] = None
    description: str
    raised_by: Optional[str] = None
    assigned_to: Optional[str] = None
    target_date: Optional[date] = None
    priority: str = "MEDIUM"


class PunchItemUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    target_date: Optional[date] = None
    closeout_date: Optional[date] = None
    closeout_verified_by: Optional[str] = None


# ---- Sub-Systems ----

@router.post("/sub-systems/{project_id}")
async def create_sub_system(project_id: str, data: SubSystemCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""INSERT INTO sub_systems (sub_system_id, project_id, system_code, system_name,
                 parent_system_id, discipline_id, area_code, planned_mc_date, responsible_engineer, notes)
                VALUES (gen_random_uuid(), :pid, :code, :name, :parent, :did, :area, :mc_date, :eng, :notes)
                ON CONFLICT (project_id, system_code) DO UPDATE
                SET system_name = EXCLUDED.system_name, updated_at = NOW()
                RETURNING sub_system_id"""),
        {"pid": project_id, "code": data.system_code, "name": data.system_name,
         "parent": data.parent_system_id, "did": data.discipline_id,
         "area": data.area_code, "mc_date": data.planned_mc_date,
         "eng": data.responsible_engineer, "notes": data.notes}
    )
    await db.commit()
    return {"sub_system_id": str(result.scalar()), "status": "created"}


@router.get("/sub-systems/{project_id}")
async def list_sub_systems(
    project_id: str,
    status: Optional[str] = None,
    discipline_id: Optional[int] = None,
    area_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = """SELECT ss.*, ed.discipline_name,
                      COALESCE(pi.open_punches, 0) AS open_punch_count
               FROM sub_systems ss
               LEFT JOIN engineering_disciplines ed ON ss.discipline_id = ed.discipline_id
               LEFT JOIN (
                   SELECT sub_system_id, COUNT(*) AS open_punches
                   FROM punch_items WHERE status != 'CLOSED' AND status != 'CANCELLED'
                   GROUP BY sub_system_id
               ) pi ON ss.sub_system_id = pi.sub_system_id
               WHERE ss.project_id = :pid"""
    params = {"pid": project_id}
    if status:
        query += " AND ss.completion_status = :st"
        params["st"] = status
    if discipline_id:
        query += " AND ss.discipline_id = :did"
        params["did"] = discipline_id
    if area_code:
        query += " AND ss.area_code = :area"
        params["area"] = area_code
    query += " ORDER BY ss.system_code"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.get("/sub-systems/{project_id}/{sub_system_id}")
async def get_sub_system(project_id: str, sub_system_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT ss.*, ed.discipline_name FROM sub_systems ss "
             "LEFT JOIN engineering_disciplines ed ON ss.discipline_id = ed.discipline_id "
             "WHERE ss.sub_system_id = :sid AND ss.project_id = :pid"),
        {"sid": sub_system_id, "pid": project_id}
    )
    row = result.fetchone()
    if not row:
        raise not_found("Sub-system", sub_system_id)
    return dict(row._mapping)


@router.patch("/sub-systems/{project_id}/{sub_system_id}")
async def update_sub_system(project_id: str, sub_system_id: str, data: SubSystemUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"sid": sub_system_id, "pid": project_id}
    for field in ["system_name", "completion_status", "planned_mc_date", "actual_mc_date",
                   "handover_date", "responsible_engineer", "notes"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        return {"status": "no changes"}
    updates.append("updated_at = NOW()")
    await db.execute(
        text(f"UPDATE sub_systems SET {', '.join(updates)} WHERE sub_system_id = :sid AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


# ---- Punch Items ----

@router.post("/punch-items/{project_id}")
async def create_punch_item(project_id: str, data: PunchItemCreate, db: AsyncSession = Depends(get_db)):
    punch_number = f"PUNCH-{project_id[:8]}-{date.today().strftime('%y%m%d')}"
    result = await db.execute(
        text("""INSERT INTO punch_items (punch_id, project_id, sub_system_id, punch_number, category,
                 discipline_id, area_code, description, raised_by, assigned_to, target_date, priority)
                VALUES (gen_random_uuid(), :pid, :ssid, :pnum, :cat, :did, :area, :desc, :by, :assign, :tdate, :pri)
                ON CONFLICT (punch_number) DO NOTHING
                RETURNING punch_id"""),
        {"pid": project_id, "ssid": data.sub_system_id, "pnum": punch_number,
         "cat": data.category, "did": data.discipline_id, "area": data.area_code,
         "desc": data.description, "by": data.raised_by, "assign": data.assigned_to,
         "tdate": data.target_date, "pri": data.priority}
    )
    await db.commit()
    row = result.fetchone()
    if not row:
        return {"status": "punch_number_exists"}
    return {"punch_id": str(row[0]), "punch_number": punch_number, "status": "created"}


@router.get("/punch-items/{project_id}")
async def list_punch_items(
    project_id: str,
    sub_system_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = """SELECT pi.*, ss.system_code, ss.system_name, ed.discipline_name
               FROM punch_items pi
               JOIN sub_systems ss ON pi.sub_system_id = ss.sub_system_id
               LEFT JOIN engineering_disciplines ed ON pi.discipline_id = ed.discipline_id
               WHERE pi.project_id = :pid"""
    params = {"pid": project_id}
    if sub_system_id:
        query += " AND pi.sub_system_id = :ssid"
        params["ssid"] = sub_system_id
    if status:
        query += " AND pi.status = :st"
        params["st"] = status
    if category:
        query += " AND pi.category = :cat"
        params["cat"] = category
    query += " ORDER BY CASE pi.category WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END, pi.raised_date DESC"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/punch-items/{project_id}/{punch_id}")
async def update_punch_item(project_id: str, punch_id: str, data: PunchItemUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "punch_id": punch_id}
    for field in ["status", "assigned_to", "target_date", "closeout_date", "closeout_verified_by"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        return {"status": "no changes"}
    updates.append("updated_at = NOW()")
    await db.execute(
        text(f"UPDATE punch_items SET {', '.join(updates)} WHERE punch_id = :punch_id AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


@router.get("/punch-summary/{project_id}")
async def punch_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""SELECT COALESCE(category, 'TOTAL') AS category, COUNT(*) AS count,
                       SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed
                FROM punch_items WHERE project_id = :pid
                GROUP BY ROLLUP(category)"""),
        {"pid": project_id}
    )
    rows = [dict(r._mapping) for r in result]
    total_row = next((r for r in rows if r["category"] == "TOTAL"), None)
    details = [r for r in rows if r["category"] != "TOTAL"]
    return {
        "total": total_row["count"] if total_row else 0,
        "total_closed": total_row["closed"] if total_row else 0,
        "closeout_pct": round(total_row["closed"] / total_row["count"] * 100, 1)
                        if total_row and total_row["count"] else 0,
        "by_category": details,
    }
