from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import date, timedelta
from database import get_db

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _row_to_dict(row) -> dict:
    """Safely convert a SQLAlchemy Row to dict, returning {} for None."""
    if row is None:
        return {}
    return dict(row._mapping)


@router.get("/accountability/{project_id}")
async def accountability_report(project_id: str, week_end: date, db: AsyncSession = Depends(get_db)):
    week_start = week_end - timedelta(days=6)
    tasks = await db.execute(
        text("SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_completed THEN 1 ELSE 0 END), 0) AS completed, "
             "COALESCE(AVG(actual_completion_percent), 0) AS avg_actual, COALESCE(AVG(planned_completion_percent), 0) AS avg_planned "
             "FROM weekly_planning_tasks WHERE project_id = :pid AND week_start = :ws"),
        {"pid": project_id, "ws": week_start}
    )
    ndt = await db.execute(
        text("SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS completed, "
             "COALESCE(AVG(percent_complete), 0) AS avg_pct FROM ndt_requests "
             "WHERE project_id = :pid AND requested_date BETWEEN :ws AND :we"),
        {"pid": project_id, "ws": week_start, "we": week_end}
    )
    manpower = await db.execute(
        text("SELECT report_date, discipline, "
             "ROUND(100.0 * actual_headcount / NULLIF(planned_headcount, 0), 1) AS productivity_pct "
             "FROM daily_manpower WHERE project_id = :pid AND report_date BETWEEN :ws AND :we "
             "ORDER BY report_date, discipline LIMIT 1000"),
        {"pid": project_id, "ws": week_start, "we": week_end}
    )
    shortages = await db.execute(
        text("SELECT resource_name, shortfall FROM resource_shortages "
             "WHERE project_id = :pid AND status = 'OPEN' ORDER BY shortfall DESC LIMIT 3"),
        {"pid": project_id}
    )
    # fetchone() may be None for COUNT(*) queries on empty tables with SQLAlchemy async
    t_row = tasks.fetchone()
    n_row = ndt.fetchone()
    t = _row_to_dict(t_row)
    n = _row_to_dict(n_row)
    return {
        "week_ending": week_end.isoformat(),
        "task_summary": {
            "total": t.get("total", 0),
            "completed": t.get("completed", 0),
            "planned_pct": float(t.get("avg_planned") or 0),
            "actual_pct": float(t.get("avg_actual") or 0),
        },
        "ndt_achievement": {
            "total_requests": n.get("total", 0),
            "completed": n.get("completed", 0),
            "avg_complete_pct": float(n.get("avg_pct") or 0),
        },
        "manpower_productivity": [_row_to_dict(m) for m in manpower],
        "top_shortages": [_row_to_dict(s) for s in shortages],
    }


@router.get("/dashboard/{project_id}")
async def dashboard_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    projects = await db.execute(text("SELECT * FROM projects WHERE project_id = :pid"), {"pid": project_id})
    proj_row = projects.fetchone()
    if not proj_row:
        return {"project": None, "activities": {}, "alerts": {}, "ndt": {}}

    activities = await db.execute(
        text("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_critical) AS critical_count, "
             "AVG(physical_percent_complete)::DECIMAL(5,1) AS avg_progress "
             "FROM activities WHERE project_id = :pid"), {"pid": project_id}
    )
    act_row = activities.fetchone()

    alerts = await db.execute(
        text("SELECT COUNT(*) AS open_alerts FROM schedule_alerts WHERE project_id = :pid AND is_resolved = FALSE"),
        {"pid": project_id}
    )
    alt_row = alerts.fetchone()

    ndt = await db.execute(
        text("SELECT COUNT(*) AS total, AVG(percent_complete)::DECIMAL(5,1) AS avg_pct FROM ndt_requests WHERE project_id = :pid"),
        {"pid": project_id}
    )
    n_row = ndt.fetchone()

    return {
        "project": _row_to_dict(proj_row),
        "activities": _row_to_dict(act_row),
        "alerts": _row_to_dict(alt_row),
        "ndt": _row_to_dict(n_row),
    }
