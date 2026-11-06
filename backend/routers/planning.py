"""Multi-Level Planning router — weekly/bi-weekly/monthly/bi-monthly/4-month plans."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date, timedelta
from typing import Optional
import calendar
from database import get_db
from errors import not_found, bad_request
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/planning", tags=["planning"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    """Clamp pagination inputs to safe bounds."""
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ── Pure date helpers (unit-testable) ─────────────────────────────────
#
# Naive `month + 1` arithmetic raises ValueError for November/December
# (month 12 + 1 = 13). These helpers normalise month indices through a
# zero-based total-months value so any offset is safe.

def add_months(anchor: date, months: int) -> date:
    """Return the first day of the month `months` months after `anchor`'s month.

    Safe for December/January rollover and for negative offsets.
    """
    total = (anchor.year * 12 + (anchor.month - 1)) + months
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def month_bounds(anchor: date, month_offset: int) -> tuple[date, date]:
    """Return (first_day, last_day) of the month `month_offset` months from anchor."""
    start = add_months(anchor, month_offset)
    next_start = add_months(anchor, month_offset + 1)
    return start, next_start - timedelta(days=1)


def next_week_start(anchor: date) -> date:
    """Return the anchor itself when it is a Monday, else the following Monday."""
    return anchor + timedelta(days=(7 - anchor.weekday()) % 7)


def bi_month_start(anchor: date, block_offset: int = 0) -> date:
    """Return the first day of the two-month block containing `anchor`.

    `block_offset` counts blocks of two months from the containing block and
    may cross a year boundary (e.g. November + 1 block -> January next year).
    """
    # Month index 0-based within the year; blocks start at odd months (Jan, Mar...).
    months_from_year_start = ((anchor.month - 1) // 2) * 2 + block_offset * 2
    return add_months(date(anchor.year, 1, 1), months_from_year_start)


def four_month_start(anchor: date) -> date:
    """Return the first day of the four-month block containing `anchor`."""
    months_from_year_start = ((anchor.month - 1) // 4) * 4
    return add_months(date(anchor.year, 1, 1), months_from_year_start)


# ---- Pydantic Schemas ----

class PlanningPeriodCreate(BaseModel):
    period_type: str  # WEEKLY, BI_WEEKLY, MONTHLY, BI_MONTHLY, FOUR_MONTH
    period_start: date
    period_end: date
    period_label: Optional[str] = None


class PlanItemCreate(BaseModel):
    period_id: str
    activity_id: str
    planned_weight_pct: float
    milestone_flag: bool = False
    milestone_name: Optional[str] = None


class PlanItemUpdate(BaseModel):
    actual_weight_pct: Optional[float] = None
    status: Optional[str] = None
    variance_note: Optional[str] = None
    milestone_flag: Optional[bool] = None


# ---- Planning Periods ----

@router.post("/periods/{project_id}")
async def create_period(project_id: str, data: PlanningPeriodCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
                VALUES (gen_random_uuid(), :pid, :ptype, :pstart, :pend, :plabel)
                ON CONFLICT (project_id, period_type, period_start) DO UPDATE
                SET period_end = EXCLUDED.period_end, period_label = EXCLUDED.period_label
                RETURNING period_id"""),
        {"pid": project_id, "ptype": data.period_type, "pstart": data.period_start,
         "pend": data.period_end, "plabel": data.period_label}
    )
    await db.commit()
    return {"period_id": str(result.scalar()), "status": "created"}


@router.get("/periods/{project_id}")
async def list_periods(project_id: str, period_type: Optional[str] = None,
                       page: int = 1, page_size: int = 50, db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT pp.*,
                      (SELECT COUNT(*) FROM plan_items pi WHERE pi.period_id = pp.period_id) AS item_count
               FROM planning_periods pp
               WHERE pp.project_id = :pid"""
    params = {"pid": project_id}
    if period_type:
        query += " AND pp.period_type = :ptype"
        params["ptype"] = period_type
    query += (" ORDER BY CASE pp.period_type WHEN 'WEEKLY' THEN 0 WHEN 'BI_WEEKLY' THEN 1 "
              "WHEN 'MONTHLY' THEN 2 WHEN 'BI_MONTHLY' THEN 3 WHEN 'FOUR_MONTH' THEN 4 END, "
              "pp.period_start DESC LIMIT :limit OFFSET :offset")
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.delete("/periods/{project_id}/{period_id}")
async def delete_period(project_id: str, period_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("DELETE FROM planning_periods WHERE period_id = :perid AND project_id = :pid AND is_locked = FALSE"),
        {"perid": period_id, "pid": project_id}
    )
    await db.commit()
    return {"status": "deleted"}


@router.post("/periods/{project_id}/{period_id}/lock")
async def lock_period(project_id: str, period_id: str, db: AsyncSession = Depends(get_db),
                      user: TokenData = Depends(get_current_user)):
    # Identity comes from the authenticated token, never from the client body/query.
    await db.execute(
        text("UPDATE planning_periods SET is_locked = TRUE, locked_by = :by, locked_at = NOW() WHERE period_id = :perid AND project_id = :pid"),
        {"perid": period_id, "pid": project_id, "by": user.username}
    )
    await db.commit()
    return {"status": "locked"}


# ---- Plan Items ----

@router.post("/items/{project_id}")
async def create_plan_item(project_id: str, data: PlanItemCreate, db: AsyncSession = Depends(get_db)):
    # Verify period belongs to project
    period = await db.execute(
        text("SELECT is_locked FROM planning_periods WHERE period_id = :perid AND project_id = :pid"),
        {"perid": data.period_id, "pid": project_id}
    )
    p = period.fetchone()
    if not p:
        raise not_found("Planning period", data.period_id)
    if p._mapping["is_locked"]:
        raise bad_request("Period is locked — cannot add items")

    await db.execute(
        text("""INSERT INTO plan_items (plan_item_id, period_id, activity_id, planned_weight_pct, milestone_flag, milestone_name)
                VALUES (gen_random_uuid(), :perid, :aid, :wpct, :mflag, :mname)
                ON CONFLICT (period_id, activity_id) DO UPDATE
                SET planned_weight_pct = EXCLUDED.planned_weight_pct,
                    milestone_flag = EXCLUDED.milestone_flag,
                    milestone_name = EXCLUDED.milestone_name"""),
        {"perid": data.period_id, "aid": data.activity_id, "wpct": data.planned_weight_pct,
         "mflag": data.milestone_flag, "mname": data.milestone_name}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/items/{project_id}")
async def list_plan_items(
    project_id: str,
    period_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT pi.*, a.activity_code, a.activity_name, a.physical_percent_complete AS current_progress,
                      pp.period_type, pp.period_start, pp.period_end
               FROM plan_items pi
               JOIN planning_periods pp ON pi.period_id = pp.period_id
               JOIN activities a ON pi.activity_id = a.activity_id
               WHERE pp.project_id = :pid"""
    params = {"pid": project_id}
    if period_id:
        query += " AND pi.period_id = :perid"
        params["perid"] = period_id
    if status:
        query += " AND pi.status = :st"
        params["st"] = status
    query += " ORDER BY pp.period_start, a.activity_code LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/items/{project_id}/{plan_item_id}")
async def update_plan_item(project_id: str, plan_item_id: str, data: PlanItemUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "item_id": plan_item_id}
    for field in ["actual_weight_pct", "status", "variance_note", "milestone_flag"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE plan_items SET {', '.join(updates)} WHERE plan_item_id = :item_id "
             "AND period_id IN (SELECT period_id FROM planning_periods WHERE project_id = :pid)"),
        params
    )
    await db.commit()
    return {"status": "updated"}


# ---- Multi-Level Plan View ----

@router.get("/board/{project_id}")
async def planning_board(project_id: str, period_type: str = "WEEKLY", db: AsyncSession = Depends(get_db)):
    """Aggregated planning board for a specific period type."""
    # Get the latest periods for the given type
    periods = await db.execute(
        text("""SELECT period_id, period_start, period_end, period_label, is_locked
                FROM planning_periods
                WHERE project_id = :pid AND period_type = :ptype
                ORDER BY period_start DESC LIMIT 8"""),
        {"pid": project_id, "ptype": period_type}
    )
    period_list = [dict(r._mapping) for r in periods]

    if not period_list:
        return {"periods": [], "items": []}

    # Get all items for these periods
    period_ids = [p["period_id"] for p in period_list]
    placeholders = ", ".join(f":pid{i}" for i in range(len(period_ids)))
    params = {"pid": project_id}
    for i, pid in enumerate(period_ids):
        params[f"pid{i}"] = pid

    items = await db.execute(
        text(f"""SELECT pi.*, a.activity_code, a.activity_name, a.is_critical,
                        a.work_scope_category, a.physical_percent_complete,
                        pp.period_start, pp.period_end
                 FROM plan_items pi
                 JOIN planning_periods pp ON pi.period_id = pp.period_id
                 JOIN activities a ON pi.activity_id = a.activity_id
                 WHERE pp.project_id = :pid AND pi.period_id IN ({placeholders})
                 ORDER BY pp.period_start DESC, a.activity_code
                 LIMIT 2000"""),
        params
    )
    item_list = [dict(r._mapping) for r in items]

    # Roll-up summary
    summary = {"total_items": len(item_list),
               "milestones": sum(1 for i in item_list if i.get("milestone_flag")),
               "on_track": sum(1 for i in item_list if i.get("status") == "ON_TRACK"),
               "at_risk": sum(1 for i in item_list if i.get("status") == "AT_RISK"),
               "delayed": sum(1 for i in item_list if i.get("status") == "DELAYED"),
               "completed": sum(1 for i in item_list if i.get("status") == "COMPLETED")}

    return {"periods": period_list, "items": item_list, "summary": summary}


# ---- Plan Generation (roll-up from weekly to higher levels) ----

INSERT_PERIOD_SQL = text(
    """INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
       VALUES (gen_random_uuid(), :pid, :ptype, :pstart, :pend, :label)
       ON CONFLICT (project_id, period_type, period_start) DO NOTHING
       RETURNING period_id"""
)


def build_periods(anchor: date) -> list[dict]:
    """Build the full set of planning periods for a project anchor date.

    Pure function so the date arithmetic is unit-testable. Returns one dict per
    period, each `created` counter keyed by lower-case period type.
    """
    next_monday = next_week_start(anchor)
    periods: list[dict] = []

    # Weekly — 16 weeks
    for w in range(16):
        ws = next_monday + timedelta(weeks=w)
        we = ws + timedelta(days=6)
        periods.append({"ptype": "WEEKLY", "pstart": ws, "pend": we,
                        "label": f"Week {ws.isoformat()} — {we.isoformat()}"})

    # Bi-Weekly — 8 periods
    for b in range(8):
        bs = next_monday + timedelta(weeks=b * 2)
        be = bs + timedelta(days=13)
        periods.append({"ptype": "BI_WEEKLY", "pstart": bs, "pend": be,
                        "label": f"Bi-Week {bs.isoformat()} — {be.isoformat()}"})

    # Monthly — 4 periods (safe across December/January)
    for m in range(4):
        ms, me = month_bounds(next_monday, m)
        periods.append({"ptype": "MONTHLY", "pstart": ms, "pend": me,
                        "label": ms.strftime("%B %Y")})

    # Bi-Monthly — 2 periods (safe across November/December -> January)
    for bm in range(2):
        bms = bi_month_start(next_monday, bm)
        bme = add_months(bms, 2) - timedelta(days=1)
        periods.append({"ptype": "BI_MONTHLY", "pstart": bms, "pend": bme,
                        "label": f"Bi-Month {bms.strftime('%b')} — {bme.strftime('%b %Y')}"})

    # Four-Month — 1 period covering the current 4-month block
    fms = four_month_start(next_monday)
    fme = add_months(fms, 4) - timedelta(days=1)
    periods.append({"ptype": "FOUR_MONTH", "pstart": fms, "pend": fme,
                    "label": f"4-Month {fms.strftime('%b %Y')} — {fme.strftime('%b %Y')}"})

    return periods


@router.post("/generate/{project_id}")
async def generate_plans(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Auto-generate planning periods for the next 4 months across all levels.
    Creates: 16 weekly, 8 bi-weekly, 4 monthly, 2 bi-monthly, 1 four-month period.

    Idempotent: existing (project, period_type, period_start) periods are
    skipped via ON CONFLICT. The whole batch runs in a single transaction so a
    failure leaves no partial generation behind.
    """
    created = {"weekly": 0, "bi_weekly": 0, "monthly": 0, "bi_monthly": 0, "four_month": 0}
    key_map = {
        "WEEKLY": "weekly", "BI_WEEKLY": "bi_weekly", "MONTHLY": "monthly",
        "BI_MONTHLY": "bi_monthly", "FOUR_MONTH": "four_month",
    }

    periods = build_periods(date.today())
    async with db.begin():
        for p in periods:
            result = await db.execute(
                INSERT_PERIOD_SQL,
                {"pid": project_id, "ptype": p["ptype"],
                 "pstart": p["pstart"], "pend": p["pend"], "label": p["label"]},
            )
            if result.scalar() is not None:
                created[key_map[p["ptype"]]] += 1

    return {"status": "plans generated", "created_periods": created}
