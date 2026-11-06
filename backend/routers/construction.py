from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/construction", tags=["construction"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


def sql_in_placeholders(prefix: str, values: list) -> tuple[str, dict]:
    """Build a portable `:p0, :p1, ...` IN list and its params."""
    names = [f"{prefix}{i}" for i in range(len(values))]
    return ", ".join(f":{n}" for n in names), {n: v for n, v in zip(names, values)}


class ManpowerRecord(BaseModel):
    project_id: str
    report_date: date
    discipline: str
    planned_headcount: int
    actual_headcount: int
    overtime_hours: Optional[float] = 0


class WeeklyTaskCreate(BaseModel):
    project_id: str
    week_start: date
    activity_id: str
    planned_status: str
    planned_completion_percent: int
    accountability_party: Optional[str] = None


class WeeklyTaskUpdate(BaseModel):
    actual_completion_percent: int
    is_completed: bool = False
    delay_reason: Optional[str] = None


class ShortageCreate(BaseModel):
    project_id: str
    shortage_type: str
    resource_name: str
    required_quantity: float
    available_quantity: float
    shortfall: float
    expected_resolution_date: Optional[date] = None
    impact_description: Optional[str] = None


class MvrStatusUpdate(BaseModel):
    mvr_status: str
    confirmed_by: Optional[str] = None


@router.post("/daily-manpower")
async def record_manpower(data: ManpowerRecord, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO daily_manpower (record_id, project_id, report_date, discipline, planned_headcount, actual_headcount, overtime_hours) "
             "VALUES (gen_random_uuid(), :pid, :rdate, :disc, :planned, :actual, :ot) "
             "ON CONFLICT (project_id, report_date, discipline) DO UPDATE "
             "SET planned_headcount = EXCLUDED.planned_headcount, actual_headcount = EXCLUDED.actual_headcount, overtime_hours = EXCLUDED.overtime_hours"),
        {"pid": data.project_id, "rdate": data.report_date, "disc": data.discipline,
         "planned": data.planned_headcount, "actual": data.actual_headcount, "ot": data.overtime_hours}
    )
    await db.commit()
    return {"status": "recorded"}


@router.get("/daily-manpower/{project_id}")
async def get_manpower(project_id: str, report_date: Optional[date] = None, db: AsyncSession = Depends(get_db)):
    if report_date:
        result = await db.execute(
            text("SELECT * FROM daily_manpower WHERE project_id = :pid AND report_date = :rdate"),
            {"pid": project_id, "rdate": report_date}
        )
    else:
        result = await db.execute(
            text("SELECT * FROM daily_manpower WHERE project_id = :pid ORDER BY report_date DESC LIMIT 30"),
            {"pid": project_id}
        )
    return [dict(r._mapping) for r in result]


@router.get("/weekly-planning/{project_id}")
async def get_weekly_planning(project_id: str, week_start: date, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT wpt.*, a.activity_name FROM weekly_planning_tasks wpt "
             "JOIN activities a ON wpt.activity_id = a.activity_id "
             "WHERE wpt.project_id = :pid AND wpt.week_start = :ws"),
        {"pid": project_id, "ws": week_start}
    )
    return [dict(r._mapping) for r in result]


@router.post("/weekly-planning")
async def create_weekly_task(data: WeeklyTaskCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO weekly_planning_tasks (task_id, project_id, week_start, activity_id, planned_status, planned_completion_percent, accountability_party) "
             "VALUES (gen_random_uuid(), :pid, :ws, :aid, :ps, :pcp, :ap)"),
        {"pid": data.project_id, "ws": data.week_start, "aid": data.activity_id,
         "ps": data.planned_status, "pcp": data.planned_completion_percent, "ap": data.accountability_party}
    )
    await db.commit()
    return {"status": "created"}


@router.patch("/weekly-planning/{task_id}")
async def update_weekly_task(task_id: str, data: WeeklyTaskUpdate,
                             project_id: Optional[str] = None,
                             db: AsyncSession = Depends(get_db)):
    scope_sql = " AND project_id = :pid" if project_id else ""
    await db.execute(
        text("UPDATE weekly_planning_tasks SET actual_completion_percent = :acp, "
             "is_completed = :ic, delay_reason = :dr "
             f"WHERE task_id = :tid{scope_sql}"),
        {"acp": data.actual_completion_percent, "ic": data.is_completed,
         "dr": data.delay_reason, "tid": task_id,
         **({"pid": project_id} if project_id else {})}
    )
    await db.commit()
    return {"status": "updated"}


@router.get("/resource-shortages/{project_id}")
async def get_open_shortages(project_id: str, page: int = 1, page_size: int = 200,
                             db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("SELECT * FROM resource_shortages WHERE project_id = :pid AND status = 'OPEN' "
             "ORDER BY shortfall DESC LIMIT :limit OFFSET :offset"),
        {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]


@router.post("/resource-shortages")
async def create_shortage(data: ShortageCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO resource_shortages (shortage_id, project_id, shortage_type, resource_name, required_quantity, available_quantity, shortfall, expected_resolution_date, impact_description) "
             "VALUES (gen_random_uuid(), :pid, :stype, :rname, :req, :avail, :shortfall, :resdate, :impact)"),
        {"pid": data.project_id, "stype": data.shortage_type, "rname": data.resource_name,
         "req": data.required_quantity, "avail": data.available_quantity,
         "shortfall": data.shortfall, "resdate": data.expected_resolution_date,
         "impact": data.impact_description}
    )
    await db.commit()
    return {"status": "created"}


# ── MVR Materials ────────────────────────────────────────────────────

@router.get("/materials/{project_id}")
async def get_construction_materials(
    project_id: str,
    discipline_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Get construction materials with MVR status, drawing AFC/IFA flags, and PO enrichment."""
    page, page_size = clamp_page(page, page_size)
    # Count query for pagination
    count_query = (
        "SELECT COUNT(*) FROM drawing_materials dm "
        "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
        "WHERE dm.project_id = :pid"
    )
    count_params = {"pid": project_id}
    if discipline_id:
        count_query += " AND drw.discipline_id = :did"
        count_params["did"] = discipline_id
    total_result = await db.execute(text(count_query), count_params)
    total = total_result.scalar() or 0

    # Materials query with pagination
    mat_query = (
        "SELECT dm.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev, "
        "drw.issued_for_info, drw.issued_for_construction, "
        "ed.discipline_name, ed.discipline_id "
        "FROM drawing_materials dm "
        "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
        "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
        "WHERE dm.project_id = :pid"
    )
    mat_params = {"pid": project_id}
    if discipline_id:
        mat_query += " AND drw.discipline_id = :did"
        mat_params["did"] = discipline_id
    mat_query += " ORDER BY ed.discipline_id, drw.drawing_number, dm.piece_mark"
    mat_query += " LIMIT :limit OFFSET :offset"
    mat_params["limit"] = page_size
    mat_params["offset"] = (page - 1) * page_size

    mat_result = await db.execute(text(mat_query), mat_params)
    mat_rows = [dict(r._mapping) for r in mat_result]

    # Equipment query — paginated and enriched only for the current page
    eq_count_query = (
        "SELECT COUNT(*) FROM drawing_equipment de "
        "JOIN drawings drw ON de.drawing_id = drw.drawing_id "
        "WHERE de.project_id = :pid"
    )
    eq_count_params = {"pid": project_id}
    if discipline_id:
        eq_count_query += " AND drw.discipline_id = :did"
        eq_count_params["did"] = discipline_id
    eq_total_result = await db.execute(text(eq_count_query), eq_count_params)
    eq_total = eq_total_result.scalar() or 0

    eq_query = (
        "SELECT de.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev, "
        "drw.issued_for_info, drw.issued_for_construction, "
        "ed.discipline_name, ed.discipline_id "
        "FROM drawing_equipment de "
        "JOIN drawings drw ON de.drawing_id = drw.drawing_id "
        "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
        "WHERE de.project_id = :pid"
    )
    eq_params = {"pid": project_id}
    if discipline_id:
        eq_query += " AND drw.discipline_id = :did"
        eq_params["did"] = discipline_id
    eq_query += (" ORDER BY ed.discipline_id, drw.drawing_number, de.equipment_tag "
                 "LIMIT :limit OFFSET :offset")
    eq_params["limit"] = page_size
    eq_params["offset"] = (page - 1) * page_size

    eq_result = await db.execute(text(eq_query), eq_params)
    eq_rows = [dict(r._mapping) for r in eq_result]

    # PO enrichment for materials — only the current page, project-scoped, and
    # matched on a composite key (material_type + grade/spec) instead of
    # material_type alone, which pulled the wrong PO.
    po_map = {}
    if mat_rows:
        material_ids = [m["material_id"] for m in mat_rows]
        in_sql, in_params = sql_in_placeholders("mid", material_ids)
        po_result = await db.execute(
            text(f"""SELECT dm.material_id, pi.po_id, po.po_number, po.status AS po_status
                    FROM drawing_materials dm
                    JOIN purchase_items pi ON dm.material_type = pi.material_type
                        AND (
                            pi.material_spec IS NULL
                            OR dm.material_grade = pi.material_spec
                            OR dm.material_class = pi.material_spec
                        )
                    JOIN procurement_purchase_orders po ON pi.po_id = po.po_id
                    WHERE dm.project_id = :pid AND po.project_id = :pid
                      AND dm.material_id IN ({in_sql})"""),
            {"pid": project_id, **in_params}
        )
        for r in po_result:
            row = dict(r._mapping)
            if row["material_id"] not in po_map:
                po_map[row["material_id"]] = {
                    "po_id": row["po_id"], "po_number": row["po_number"], "po_status": row["po_status"]
                }

    materials = []
    for r in mat_rows:
        mid = r["material_id"]
        item = dict(r)
        if mid in po_map:
            item.update(po_map[mid])
        else:
            item["po_id"] = None
            item["po_number"] = None
            item["po_status"] = item.get("po_status") or None
        item["is_afc"] = item.get("issued_for_construction") == "Yes"
        item["is_afi"] = (item.get("issued_for_info") == "Yes"
                          and item.get("issued_for_construction") != "Yes")
        if not item.get("mvr_status"):
            item["mvr_status"] = "Info-AFI"
        materials.append(item)

    equipment = []
    for r in eq_rows:
        item = dict(r)
        item["is_afc"] = item.get("issued_for_construction") == "Yes"
        item["is_afi"] = (item.get("issued_for_info") == "Yes"
                          and item.get("issued_for_construction") != "Yes")
        equipment.append(item)

    total_pages = max(1, (total + page_size - 1) // page_size)
    eq_total_pages = max(1, (eq_total + page_size - 1) // page_size)
    return {
        "materials": materials,
        "equipment": equipment,
        "pagination": {
            "total": total, "page": page, "page_size": page_size,
            "total_pages": total_pages, "has_next": page < total_pages, "has_prev": page > 1,
        },
        "equipment_pagination": {
            "total": eq_total, "page": page, "page_size": page_size,
            "total_pages": eq_total_pages, "has_next": page < eq_total_pages, "has_prev": page > 1,
        },
    }


# ── MVR Status Update ────────────────────────────────────────────────

@router.patch("/mvr-status/{material_id}")
async def update_mvr_status(material_id: str, data: MvrStatusUpdate,
                            project_id: Optional[str] = None,
                            db: AsyncSession = Depends(get_db),
                            user: TokenData = Depends(get_current_user)):
    """Update MVR status. MVR-confirm requires AFC drawing.

    `project_id` is an optional scope guard; `confirmed_by` always comes from
    the authenticated token, never the request body.
    """
    new_status = data.mvr_status
    confirmed_by = user.username

    valid_statuses = {"Info-AFI", "Structure-requested", "MVR-confirm"}
    if new_status not in valid_statuses:
        return {"status": "error", "message": f"Invalid MVR status: {new_status}. Must be one of: {valid_statuses}"}

    # Check drawing AFC status
    scope_sql = " AND dm.project_id = :pid" if project_id else ""
    result = await db.execute(
        text("SELECT drw.issued_for_construction, drw.issued_for_info "
             "FROM drawing_materials dm "
             "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
             f"WHERE dm.material_id = :mid{scope_sql}"),
        {"mid": material_id, **({"pid": project_id} if project_id else {})}
    )
    row = result.fetchone()
    if not row:
        return {"status": "error", "message": "Material not found"}

    row_data = dict(row._mapping)
    is_afc = row_data["issued_for_construction"] == "Yes"
    is_afi = row_data["issued_for_info"] == "Yes" and not is_afc

    # Business rule: MVR-confirm requires AFC
    if new_status == "MVR-confirm" and not is_afc:
        return {
            "status": "error",
            "message": "Cannot confirm MVR: drawing is not AFC (Approved for Construction). "
                       "Only AFC drawings can be MVR-confirmed."
        }

    # Update MVR status
    from datetime import datetime
    now = datetime.now().isoformat() if new_status == "MVR-confirm" else None
    update_scope = " AND project_id = :pid" if project_id else ""
    await db.execute(
        text("UPDATE drawing_materials SET mvr_status = :st, mvr_confirmed_by = :by, "
             f"mvr_confirmed_at = :ts WHERE material_id = :mid{update_scope}"),
        {"st": new_status, "by": confirmed_by, "ts": now, "mid": material_id,
         **({"pid": project_id} if project_id else {})}
    )
    await db.commit()

    return {
        "status": "updated",
        "material_id": material_id,
        "mvr_status": new_status,
        "confirmed_by": confirmed_by,
        "confirmed_at": now,
        "warning": "AFI dwg only" if (new_status == "MVR-confirm" and is_afi) else None,
    }


# ── MVR Summary ──────────────────────────────────────────────────────

@router.get("/mvr-summary/{project_id}")
async def get_mvr_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    """MVR status summary per discipline."""
    result = await db.execute(
        text("""SELECT ed.discipline_name,
                       COUNT(dm.material_id) AS total_materials,
                       SUM(CASE WHEN dm.mvr_status = 'Info-AFI' THEN 1 ELSE 0 END) AS info_afi_count,
                       SUM(CASE WHEN dm.mvr_status = 'Structure-requested' THEN 1 ELSE 0 END) AS structure_requested_count,
                       SUM(CASE WHEN dm.mvr_status = 'MVR-confirm' THEN 1 ELSE 0 END) AS mvr_confirm_count
                FROM drawing_materials dm
                JOIN drawings drw ON dm.drawing_id = drw.drawing_id
                JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
                WHERE dm.project_id = :pid
                GROUP BY ed.discipline_name
                ORDER BY ed.discipline_name"""),
        {"pid": project_id}
    )
    return [dict(r._mapping) for r in result]
