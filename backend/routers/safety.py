"""Safety (HSE) Management router — incidents, permits, observations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date, time
from typing import Optional
from database import get_db
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/safety", tags=["safety"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ---- Pydantic Schemas ----

class IncidentCreate(BaseModel):
    incident_date: date
    incident_time: Optional[str] = None
    incident_type: str
    severity: str = "LOW"
    area_code: Optional[str] = None
    discipline_id: Optional[int] = None
    description: str
    immediate_cause: Optional[str] = None
    reported_by: Optional[str] = None
    man_hours_at_incident: Optional[int] = 0


class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    preventive_action: Optional[str] = None
    investigated_by: Optional[str] = None
    lost_time_days: Optional[int] = None


class PermitCreate(BaseModel):
    permit_type: str
    permit_number: str
    work_description: str
    area_code: Optional[str] = None
    discipline_id: Optional[int] = None
    requested_by: Optional[str] = None
    approved_by: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    isolation_required: str = "No"
    gas_test_required: str = "No"


class PermitUpdate(BaseModel):
    status: Optional[str] = None
    approved_by: Optional[str] = None
    issue_date: Optional[date] = None
    gas_test_result: Optional[str] = None


class ObservationCreate(BaseModel):
    area_code: Optional[str] = None
    category: Optional[str] = None
    observation: str
    action_taken: Optional[str] = None
    observed_by: Optional[str] = None
    positive_observation: bool = False


# ---- Incidents ----

@router.post("/incidents/{project_id}")
async def create_incident(project_id: str, data: IncidentCreate,
                          db: AsyncSession = Depends(get_db),
                          user: TokenData = Depends(get_current_user)):
    await db.execute(
        text("""INSERT INTO safety_incidents (incident_id, project_id, incident_date, incident_time,
                 incident_type, severity, area_code, discipline_id, description,
                 immediate_cause, reported_by, man_hours_at_incident)
                VALUES (gen_random_uuid(), :pid, :idate, :itime::TIME, :itype, :sev, :area,
                        :did, :desc, :cause, :by, :mh)"""),
        {"pid": project_id, "idate": data.incident_date, "itime": data.incident_time,
         "itype": data.incident_type, "sev": data.severity, "area": data.area_code,
         "did": data.discipline_id, "desc": data.description,
         "cause": data.immediate_cause,
         # reported_by is identity — derived from the token.
         "by": user.username,
         "mh": data.man_hours_at_incident}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/incidents/{project_id}")
async def list_incidents(
    project_id: str,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT si.*, ed.discipline_name
               FROM safety_incidents si
               LEFT JOIN engineering_disciplines ed ON si.discipline_id = ed.discipline_id
               WHERE si.project_id = :pid"""
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if incident_type:
        query += " AND si.incident_type = :itype"
        params["itype"] = incident_type
    if severity:
        query += " AND si.severity = :sev"
        params["sev"] = severity
    if status:
        query += " AND si.status = :st"
        params["st"] = status
    if date_from:
        query += " AND si.incident_date >= :dfrom"
        params["dfrom"] = date_from
    if date_to:
        query += " AND si.incident_date <= :dto"
        params["dto"] = date_to
    query += " ORDER BY si.incident_date DESC, si.incident_time DESC LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/incidents/{project_id}/{incident_id}")
async def update_incident(project_id: str, incident_id: str, data: IncidentUpdate,
                          db: AsyncSession = Depends(get_db),
                          user: TokenData = Depends(get_current_user)):
    updates = []
    params = {"pid": project_id, "iid": incident_id}
    for field in ["status", "root_cause", "corrective_action", "preventive_action",
                   "lost_time_days"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    # investigated_by is an identity field — derived, never trusted.
    if data.investigated_by is not None:
        updates.append("investigated_by = :investigated_by")
        params["investigated_by"] = user.username
    if not updates:
        return {"status": "no changes"}
    updates.append("updated_at = NOW()")
    await db.execute(
        text(f"UPDATE safety_incidents SET {', '.join(updates)} WHERE incident_id = :iid AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


@router.get("/hse-stats/{project_id}")
async def hse_statistics(project_id: str, db: AsyncSession = Depends(get_db)):
    """Key HSE KPI metrics."""
    totals = await db.execute(
        text("""SELECT COUNT(*) AS total_incidents,
                       SUM(CASE WHEN incident_type = 'LTI' THEN 1 ELSE 0 END) AS lti_count,
                       SUM(CASE WHEN incident_type IN ('LTI', 'MTI', 'RWC') THEN 1 ELSE 0 END) AS recordable_count,
                       SUM(CASE WHEN incident_type = 'FA' THEN 1 ELSE 0 END) AS fa_count,
                       SUM(CASE WHEN incident_type = 'NEAR_MISS' THEN 1 ELSE 0 END) AS near_miss_count,
                       SUM(lost_time_days) AS total_lost_days,
                       SUM(man_hours_at_incident) AS total_man_hours
                FROM safety_incidents WHERE project_id = :pid"""),
        {"pid": project_id}
    )
    row = totals.fetchone()
    row_data = dict(row._mapping) if row is not None else {}
    man_hours = row_data.get("total_man_hours") or 0
    recordable = row_data.get("recordable_count") or 0
    lti = row_data.get("lti_count") or 0

    return {
        "total_incidents": row_data.get("total_incidents") or 0,
        "lti_count": lti,
        "recordable_count": recordable,
        "fa_count": row_data.get("fa_count") or 0,
        "near_miss_count": row_data.get("near_miss_count") or 0,
        "total_lost_days": row_data.get("total_lost_days") or 0,
        "trir": round(recordable * 200000 / man_hours, 2) if man_hours > 0 else 0,
        "ltifr": round(lti * 1000000 / man_hours, 2) if man_hours > 0 else 0,
        "safe_man_hours": man_hours,
    }


# ---- Permits ----

@router.post("/permits/{project_id}")
async def create_permit(project_id: str, data: PermitCreate,
                        db: AsyncSession = Depends(get_db),
                        user: TokenData = Depends(get_current_user)):
    await db.execute(
        text("""INSERT INTO safety_permits (permit_id, project_id, permit_type, permit_number,
                 work_description, area_code, discipline_id, requested_by, approved_by,
                 issue_date, expiry_date, isolation_required, gas_test_required)
                VALUES (gen_random_uuid(), :pid, :ptype, :pnum, :desc, :area, :did,
                        :reqby, :appby, :idate, :edate, :iso, :gas)"""),
        {"pid": project_id, "ptype": data.permit_type, "pnum": data.permit_number,
         "desc": data.work_description, "area": data.area_code, "did": data.discipline_id,
         # requested_by / approved_by are identity fields.
         "reqby": user.username, "appby": user.username if data.approved_by else None,
         "idate": data.issue_date, "edate": data.expiry_date,
         "iso": data.isolation_required, "gas": data.gas_test_required}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/permits/{project_id}")
async def list_permits(
    project_id: str,
    status: Optional[str] = None,
    permit_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = "SELECT * FROM safety_permits WHERE project_id = :pid"
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if status:
        query += " AND status = :st"
        params["st"] = status
    if permit_type:
        query += " AND permit_type = :ptype"
        params["ptype"] = permit_type
    query += " ORDER BY expiry_date DESC LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    permits = [dict(r._mapping) for r in result]

    # Add expiry warning flag
    today = date.today()
    for p in permits:
        if p.get("expiry_date"):
            p["days_to_expiry"] = (p["expiry_date"] - today).days
            p["is_expired"] = p["days_to_expiry"] < 0
            p["is_expiring_soon"] = 0 <= p["days_to_expiry"] <= 3

    return permits


@router.patch("/permits/{project_id}/{permit_id}")
async def update_permit(project_id: str, permit_id: str, data: PermitUpdate,
                        db: AsyncSession = Depends(get_db),
                        user: TokenData = Depends(get_current_user)):
    updates = []
    params = {"pid": project_id, "permit_id": permit_id}
    for field in ["status", "issue_date", "gas_test_result"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    # approved_by is an identity field — derived from the token.
    if data.approved_by is not None:
        updates.append("approved_by = :approved_by")
        params["approved_by"] = user.username
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE safety_permits SET {', '.join(updates)} WHERE permit_id = :permit_id AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


# ---- Observations ----

@router.post("/observations/{project_id}")
async def create_observation(project_id: str, data: ObservationCreate,
                             db: AsyncSession = Depends(get_db),
                             user: TokenData = Depends(get_current_user)):
    await db.execute(
        text("""INSERT INTO safety_observations (observation_id, project_id, area_code, category,
                 observation, action_taken, observed_by, positive_observation)
                VALUES (gen_random_uuid(), :pid, :area, :cat, :obs, :action, :by, :pos)"""),
        {"pid": project_id, "area": data.area_code, "cat": data.category,
         "obs": data.observation, "action": data.action_taken,
         # observed_by is identity — derived from the token.
         "by": user.username, "pos": data.positive_observation}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/observations/{project_id}")
async def list_observations(project_id: str, page: int = 1, page_size: int = 100,
                            db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    result = await db.execute(
        text("SELECT * FROM safety_observations WHERE project_id = :pid "
             "ORDER BY observation_date DESC LIMIT :limit OFFSET :offset"),
        {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    )
    return [dict(r._mapping) for r in result]
