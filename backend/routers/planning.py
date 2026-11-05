"""Multi-Level Planning router — weekly/bi-weekly/monthly/bi-monthly/4-month plans."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date, timedelta
from typing import Optional
from database import get_db
from errors import not_found, bad_request

router = APIRouter(prefix="/api/planning", tags=["planning"])


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
async def list_periods(project_id: str, period_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = """SELECT pp.*,
                      (SELECT COUNT(*) FROM plan_items pi WHERE pi.period_id = pp.period_id) AS item_count
               FROM planning_periods pp
               WHERE pp.project_id = :pid"""
    params = {"pid": project_id}
    if period_type:
        query += " AND pp.period_type = :ptype"
        params["ptype"] = period_type
    query += " ORDER BY CASE pp.period_type WHEN 'WEEKLY' THEN 0 WHEN 'BI_WEEKLY' THEN 1 WHEN 'MONTHLY' THEN 2 WHEN 'BI_MONTHLY' THEN 3 WHEN 'FOUR_MONTH' THEN 4 END, pp.period_start DESC"

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
async def lock_period(project_id: str, period_id: str, locked_by: str = "system", db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("UPDATE planning_periods SET is_locked = TRUE, locked_by = :by, locked_at = NOW() WHERE period_id = :perid AND project_id = :pid"),
        {"perid": period_id, "pid": project_id, "by": locked_by}
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
    db: AsyncSession = Depends(get_db),
):
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
    query += " ORDER BY pp.period_start, a.activity_code"

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
        text(f"UPDATE plan_items SET {', '.join(updates)} WHERE plan_item_id = :item_id"),
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
                 ORDER BY pp.period_start DESC, a.activity_code"""),
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

@router.post("/generate/{project_id}")
async def generate_plans(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Auto-generate planning periods for the next 4 months across all levels.
    Creates: 16 weekly, 8 bi-weekly, 4 monthly, 2 bi-monthly, 1 four-month period.
    """
    today = date.today()
    # Find next Monday as the week start
    days_until_monday = (7 - today.weekday()) % 7
    next_monday = today + timedelta(days=days_until_monday) if days_until_monday > 0 else today

    created = {"weekly": 0, "bi_weekly": 0, "monthly": 0, "bi_monthly": 0, "four_month": 0}

    # Weekly — 16 weeks
    for w in range(16):
        ws = next_monday + timedelta(weeks=w)
        we = ws + timedelta(days=6)
        await db.execute(
            text("""INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
                    VALUES (gen_random_uuid(), :pid, 'WEEKLY', :ws, :we, :label)
                    ON CONFLICT (project_id, period_type, period_start) DO NOTHING"""),
            {"pid": project_id, "ws": ws, "we": we,
             "label": f"Week {ws.isoformat()} — {we.isoformat()}"}
        )
        created["weekly"] += 1

    # Bi-Weekly — 8 periods
    for b in range(8):
        bs = next_monday + timedelta(weeks=b * 2)
        be = bs + timedelta(days=13)
        await db.execute(
            text("""INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
                    VALUES (gen_random_uuid(), :pid, 'BI_WEEKLY', :bs, :be, :label)
                    ON CONFLICT (project_id, period_type, period_start) DO NOTHING"""),
            {"pid": project_id, "bs": bs, "be": be,
             "label": f"Bi-Week {bs.isoformat()} — {be.isoformat()}"}
        )
        created["bi_weekly"] += 1

    # Monthly — 4 periods
    for m in range(4):
        ms = date(next_monday.year, next_monday.month, 1)
        # Advance by m months
        for _ in range(m):
            if ms.month == 12:
                ms = date(ms.year + 1, 1, 1)
            else:
                ms = date(ms.year, ms.month + 1, 1)
        if ms.month == 12:
            me = date(ms.year + 1, 1, 1) - timedelta(days=1)
        else:
            me = date(ms.year, ms.month + 1, 1) - timedelta(days=1)
        await db.execute(
            text("""INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
                    VALUES (gen_random_uuid(), :pid, 'MONTHLY', :ms, :me, :label)
                    ON CONFLICT (project_id, period_type, period_start) DO NOTHING"""),
            {"pid": project_id, "ms": ms, "me": me,
             "label": f"{ms.strftime('%B %Y')}"}
        )
        created["monthly"] += 1

    # Bi-Monthly — 2 periods
    for bm in range(2):
        bms = date(next_monday.year, ((next_monday.month - 1) // 2) * 2 + 1 + bm * 2, 1)
        if bms.month + 1 > 12:
            bme = date(bms.year + 1, bms.month + 1 - 12, 1) - timedelta(days=1)
        else:
            bme = date(bms.year, bms.month + 2, 1) - timedelta(days=1)
        await db.execute(
            text("""INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
                    VALUES (gen_random_uuid(), :pid, 'BI_MONTHLY', :bms, :bme, :label)
                    ON CONFLICT (project_id, period_type, period_start) DO NOTHING"""),
            {"pid": project_id, "bms": bms, "bme": bme,
             "label": f"Bi-Month {bms.strftime('%b')} — {bme.strftime('%b %Y')}"}
        )
        created["bi_monthly"] += 1

    # Four-Month — 1 period covering current 4-month block
    # E.g., if next_monday is in July, the block is May-Aug (months 5-8)
    fms = date(next_monday.year, ((next_monday.month - 1) // 4) * 4 + 1, 1)
    # Compute end: first day of next 4-month block, minus 1 day
    if fms.month + 4 > 12:
        fme = date(fms.year + 1, fms.month + 4 - 12, 1) - timedelta(days=1)
    else:
        fme = date(fms.year, fms.month + 4, 1) - timedelta(days=1)
    await db.execute(
        text("""INSERT INTO planning_periods (period_id, project_id, period_type, period_start, period_end, period_label)
                VALUES (gen_random_uuid(), :pid, 'FOUR_MONTH', :fms, :fme, :label)
                ON CONFLICT (project_id, period_type, period_start) DO NOTHING"""),
        {"pid": project_id, "fms": fms, "fme": fme,
         "label": f"4-Month {fms.strftime('%b %Y')} — {fme.strftime('%b %Y')}"}
    )
    created["four_month"] += 1

    await db.commit()
    return {"status": "plans generated", "created_periods": created}
