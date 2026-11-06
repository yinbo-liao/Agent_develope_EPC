from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from errors import not_found

router = APIRouter(prefix="/api/inspection", tags=["inspection"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


class NDTRequestCreate(BaseModel):
    project_id: str
    activity_id: Optional[str] = None
    ndt_method: str
    weld_joint_id: str
    requested_date: Optional[date] = None
    acceptance_criteria: Optional[str] = None
    technician_name: Optional[str] = None


class NDTProgressUpdate(BaseModel):
    percent: float = 0
    result: Optional[str] = None


@router.post("/ndt-request")
async def create_ndt_request(req: NDTRequestCreate, db: AsyncSession = Depends(get_db)):
    if req.activity_id:
        parent = await db.execute(
            text("SELECT activity_id FROM activities WHERE activity_id = :aid AND project_id = :pid"),
            {"aid": req.activity_id, "pid": req.project_id},
        )
        if parent.fetchone() is None:
            raise not_found("Activity", req.activity_id)
    result = await db.execute(
        text("INSERT INTO ndt_requests (ndt_id, project_id, activity_id, ndt_method, weld_joint_id, requested_date, acceptance_criteria, technician_name) "
             "VALUES (gen_random_uuid(), :pid, :aid, :method, :weld, COALESCE(:rdate, CURRENT_DATE), :ac, :tech) RETURNING ndt_id"),
        {"pid": req.project_id, "aid": req.activity_id, "method": req.ndt_method,
         "weld": req.weld_joint_id, "rdate": req.requested_date,
         "ac": req.acceptance_criteria, "tech": req.technician_name}
    )
    ndt_id = result.scalar()
    await db.commit()
    return {"ndt_id": str(ndt_id)}


@router.patch("/ndt-progress/{ndt_id}")
async def update_ndt_progress(ndt_id: str, data: NDTProgressUpdate,
                              project_id: Optional[str] = None,
                              db: AsyncSession = Depends(get_db)):
    pct = max(0.0, min(100.0, data.percent))
    query = ("UPDATE ndt_requests SET percent_complete = :pct, result = COALESCE(:res, result), "
             "status = CASE WHEN :pct >= 100 THEN 'COMPLETED' ELSE status END, "
             "completed_date = CASE WHEN :pct >= 100 THEN NOW() ELSE completed_date END "
             "WHERE ndt_id = :nid")
    params = {"pct": pct, "res": data.result, "nid": ndt_id}
    if project_id:
        query += " AND project_id = :proj_pid"
        params["proj_pid"] = project_id
    await db.execute(text(query), params)
    await db.commit()
    return {"status": "updated", "percent_complete": pct}


@router.get("/ndt-summary/{project_id}")
async def get_ndt_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT ndt_method, COUNT(*) AS total, AVG(percent_complete)::DECIMAL(5,1) AS percent_complete_avg, "
             "SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed "
             "FROM ndt_requests WHERE project_id = :pid GROUP BY ndt_method"),
        {"pid": project_id}
    )
    return [dict(r._mapping) for r in result]


@router.get("/ndt-requests/{project_id}")
async def list_ndt_requests(project_id: str, status: Optional[str] = None,
                            page: int = 1, page_size: int = 500,
                            db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    query = "SELECT * FROM ndt_requests WHERE project_id = :pid"
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if status:
        query += " AND status = :st"
        params["st"] = status
    query += " ORDER BY requested_date DESC NULLS LAST LIMIT :limit OFFSET :offset"
    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


class DailyFocusCreate(BaseModel):
    project_id: str
    focus_date: date
    discipline: str
    focus_point: str
    priority: str = "HIGH"


@router.get("/daily-focus/{project_id}")
async def get_daily_focus(project_id: str, focus_date: date,
                          page: int = 1, page_size: int = 500,
                          db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("SELECT * FROM daily_inspection_focus WHERE project_id = :pid AND focus_date = :fdate "
             "ORDER BY priority LIMIT :limit OFFSET :offset"),
        {"pid": project_id, "fdate": focus_date,
         "limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


@router.post("/daily-focus")
async def create_daily_focus(data: DailyFocusCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO daily_inspection_focus (focus_id, project_id, focus_date, discipline, focus_point, priority) "
             "VALUES (gen_random_uuid(), :pid, :fdate, :disc, :fp, :pri)"),
        {"pid": data.project_id, "fdate": data.focus_date, "disc": data.discipline,
         "fp": data.focus_point, "pri": data.priority}
    )
    await db.commit()
    return {"status": "created"}


@router.patch("/daily-focus/{focus_id}")
async def complete_daily_focus(focus_id: str, achievement_notes: Optional[str] = None,
                               project_id: Optional[str] = None,
                               db: AsyncSession = Depends(get_db)):
    query = ("UPDATE daily_inspection_focus SET is_achieved = TRUE, "
             "achievement_notes = :notes WHERE focus_id = :fid")
    params = {"notes": achievement_notes, "fid": focus_id}
    if project_id:
        query += " AND project_id = :proj_pid"
        params["proj_pid"] = project_id
    await db.execute(text(query), params)
    await db.commit()
    return {"status": "completed"}


# ── NDT Progress Table (per-drawing breakdown) ──────────────────────────

@router.get("/ndt-progress-table/{project_id}")
async def get_ndt_progress_table(project_id: str, page: int = 1, page_size: int = 500,
                                 db: AsyncSession = Depends(get_db)):
    """Returns NDT progress grouped by discipline + method with daily log data."""
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("""SELECT ndl.discipline_name, ndl.ndt_method,
                       ndl.rfi_total_length_mm, ndl.ndt_complete_length_mm,
                       ndl.daily_length_done_mm, ndl.team_deployed,
                       ndl.log_date, ndl.previous_status, ndl.remarks, ndl.updated_by
                FROM ndt_daily_log ndl
                WHERE ndl.project_id = :pid
                ORDER BY ndl.log_date DESC, ndl.discipline_name, ndl.ndt_method
                LIMIT :limit OFFSET :offset"""),
        {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


# ── NDT Drawing Register ────────────────────────────────────────────────

@router.get("/ndt-drawing-register/{project_id}")
async def get_ndt_drawing_register(project_id: str, page: int = 1, page_size: int = 500,
                                   db: AsyncSession = Depends(get_db)):
    """Returns all drawings with NDT request counts and completion status."""
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("""SELECT d.drawing_number, d.drawing_title, ed.discipline_name,
                       d.status AS drawing_status, d.issued_for_construction,
                       COUNT(nr.ndt_id) AS ndt_request_count,
                       COALESCE(SUM(CASE WHEN nr.status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS ndt_completed,
                       COALESCE(AVG(nr.percent_complete), 0) AS avg_ndt_pct
                FROM drawings d
                JOIN engineering_disciplines ed ON d.discipline_id = ed.discipline_id
                LEFT JOIN ndt_requests nr ON d.drawing_id = nr.drawing_id AND nr.project_id = d.project_id
                WHERE d.project_id = :pid
                GROUP BY d.drawing_id, d.drawing_number, d.drawing_title,
                         ed.discipline_name, d.status, d.issued_for_construction
                ORDER BY ed.discipline_name, d.drawing_number
                LIMIT :limit OFFSET :offset"""),
        {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


# ── NDT Drawing Summary (single drawing detail) ─────────────────────────

@router.get("/ndt-drawing-summary/{project_id}/{drawing_id}")
async def get_ndt_drawing_summary(project_id: str, drawing_id: str, db: AsyncSession = Depends(get_db)):
    """Returns detailed NDT status for a specific drawing."""
    result = await db.execute(
        text("""SELECT nr.ndt_method, nr.weld_joint_id, nr.joint_type,
                       nr.joint_length_mm, nr.weld_length_mm, nr.status,
                       nr.percent_complete, nr.result, nr.requested_date,
                       nr.completed_date, nr.technician_name,
                       nr.acceptance_criteria
                FROM ndt_requests nr
                WHERE nr.drawing_id = :did AND nr.project_id = :pid
                ORDER BY nr.ndt_method, nr.weld_joint_id"""),
        {"did": drawing_id, "pid": project_id}
    )
    return [dict(r._mapping) for r in result]


# ── NDT Daily Log Entry ─────────────────────────────────────────────────

class NDTDailyLogCreate(BaseModel):
    project_id: str
    log_date: date
    discipline_name: str
    ndt_method: str
    rfi_total_length_mm: float = 0
    ndt_complete_length_mm: float = 0
    daily_length_done_mm: float = 0
    team_deployed: int = 0
    previous_status: Optional[str] = None
    remarks: Optional[str] = None
    updated_by: Optional[str] = None


@router.post("/ndt-daily-log")
async def create_ndt_daily_log(data: NDTDailyLogCreate, db: AsyncSession = Depends(get_db)):
    """Insert a daily NDT log entry."""
    await db.execute(
        text("""INSERT INTO ndt_daily_log (log_id, project_id, log_date, discipline_name,
                    ndt_method, rfi_total_length_mm, ndt_complete_length_mm,
                    daily_length_done_mm, team_deployed, previous_status, remarks, updated_by)
                VALUES (gen_random_uuid(), :pid, :ldate, :disc, :method, :rfi, :complete,
                        :daily, :team, :prev, :remarks, :updated_by)"""),
        {"pid": data.project_id, "ldate": data.log_date, "disc": data.discipline_name,
         "method": data.ndt_method, "rfi": data.rfi_total_length_mm,
         "complete": data.ndt_complete_length_mm, "daily": data.daily_length_done_mm,
         "team": data.team_deployed, "prev": data.previous_status,
         "remarks": data.remarks, "updated_by": data.updated_by}
    )
    await db.commit()
    return {"status": "created"}
