"""System Completion router — sub-systems, punch list management."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from errors import not_found, conflict, bad_request
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/completion", tags=["completion"])

MAX_PAGE_SIZE = 500
PUNCH_NUMBER_MAX_ATTEMPTS = 25


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ── Punch number helpers (pure, unit-testable) ────────────────────────
#
# The old format `PUNCH-{project[:8]}-{YYMMDD}` was identical for every item
# raised on the same day in the same project, so the second insert hit the
# unique constraint and was silently discarded (`ON CONFLICT DO NOTHING`).
# The number now carries a per-project, per-day sequence suffix and the insert
# retries on a genuine conflict instead of dropping the row.

def punch_number_prefix(project_id: str, on: date) -> str:
    """Return the collision-prone stem shared by one project/day."""
    return f"PUNCH-{project_id[:8]}-{on.strftime('%y%m%d')}"


def build_punch_number(prefix: str, sequence: int) -> str:
    """Build a numbered punch id, e.g. PUNCH-demo-pro-261106-0001."""
    return f"{prefix}-{sequence:04d}"


def next_sequence_from(last_number: Optional[str], prefix: str) -> int:
    """Derive the next sequence from the highest existing number for `prefix`.

    Returns 1 when there is no existing number or it cannot be parsed.
    """
    if not last_number or not last_number.startswith(prefix + "-"):
        return 1
    try:
        return int(last_number.rsplit("-", 1)[1]) + 1
    except (ValueError, IndexError):
        return 1


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
    if data.parent_system_id:
        parent = await db.execute(
            text("SELECT sub_system_id FROM sub_systems WHERE sub_system_id = :sid AND project_id = :pid"),
            {"sid": data.parent_system_id, "pid": project_id},
        )
        if parent.fetchone() is None:
            raise not_found("Parent sub-system", data.parent_system_id)
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
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
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
    query += " ORDER BY ss.system_code LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

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
async def create_punch_item(project_id: str, data: PunchItemCreate, db: AsyncSession = Depends(get_db),
                            user: TokenData = Depends(get_current_user)):
    # The parent sub-system must belong to the path project.
    parent = await db.execute(
        text("SELECT sub_system_id FROM sub_systems WHERE sub_system_id = :ssid AND project_id = :pid"),
        {"ssid": data.sub_system_id, "pid": project_id},
    )
    if parent.fetchone() is None:
        raise not_found("Sub-system", data.sub_system_id)

    prefix = punch_number_prefix(project_id, date.today())
    last = await db.execute(
        text("""SELECT punch_number FROM punch_items
                WHERE project_id = :pid AND punch_number LIKE :pat
                ORDER BY punch_number DESC LIMIT 1"""),
        {"pid": project_id, "pat": f"{prefix}-%"},
    )
    last_row = last.fetchone()
    sequence = next_sequence_from(last_row[0] if last_row else None, prefix)

    for attempt in range(PUNCH_NUMBER_MAX_ATTEMPTS):
        punch_number = build_punch_number(prefix, sequence + attempt)
        result = await db.execute(
            text("""INSERT INTO punch_items (punch_id, project_id, sub_system_id, punch_number, category,
                     discipline_id, area_code, description, raised_by, assigned_to, target_date, priority)
                    VALUES (gen_random_uuid(), :pid, :ssid, :pnum, :cat, :did, :area, :desc, :by, :assign, :tdate, :pri)
                    ON CONFLICT (punch_number) DO NOTHING
                    RETURNING punch_id"""),
            {"pid": project_id, "ssid": data.sub_system_id, "pnum": punch_number,
             "cat": data.category, "did": data.discipline_id, "area": data.area_code,
             "desc": data.description, "by": user.username, "assign": data.assigned_to,
             "tdate": data.target_date, "pri": data.priority}
        )
        row = result.fetchone()
        if row is not None:
            await db.commit()
            return {"punch_id": str(row[0]), "punch_number": punch_number, "status": "created"}

    # Retries exhausted: report a genuine conflict rather than silently dropping.
    await db.rollback()
    raise conflict("Could not allocate a unique punch number after repeated attempts")


@router.get("/punch-items/{project_id}")
async def list_punch_items(
    project_id: str,
    sub_system_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
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
    query += (" ORDER BY CASE pi.category WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END, "
              "pi.raised_date DESC LIMIT :limit OFFSET :offset")
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/punch-items/{project_id}/{punch_id}")
async def update_punch_item(project_id: str, punch_id: str, data: PunchItemUpdate,
                            db: AsyncSession = Depends(get_db),
                            user: TokenData = Depends(get_current_user)):
    updates = []
    params = {"pid": project_id, "punch_id": punch_id}
    # Identity/approval fields are never trusted from the request body.
    for field in ["status", "assigned_to", "target_date", "closeout_date"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if data.closeout_date is not None or data.status == "CLOSED":
        updates.append("closeout_verified_by = :verified_by")
        params["verified_by"] = user.username
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
