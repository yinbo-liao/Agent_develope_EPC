"""Commissioning router — procedures, checklists, MC walkdown."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from auth import get_current_user, TokenData
from errors import not_found

router = APIRouter(prefix="/api/commissioning", tags=["commissioning"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


# ---- Pydantic Schemas ----

class CommissioningProcedureCreate(BaseModel):
    sub_system_id: str
    procedure_code: str
    procedure_name: str
    procedure_type: str = "MC_CHECK"
    description: Optional[str] = None
    planned_date: Optional[date] = None
    responsible_party: Optional[str] = None
    witness_required: bool = False
    witness_party: Optional[str] = None


class CommissioningProcedureUpdate(BaseModel):
    procedure_name: Optional[str] = None
    status: Optional[str] = None
    planned_date: Optional[date] = None
    actual_date: Optional[date] = None
    responsible_party: Optional[str] = None
    test_result: Optional[str] = None
    attachments: Optional[str] = None


class ChecklistItemCreate(BaseModel):
    procedure_id: str
    item_number: int
    check_description: str
    expected_result: Optional[str] = None


class ChecklistItemUpdate(BaseModel):
    actual_result: Optional[str] = None
    is_verified: Optional[bool] = None
    verified_by: Optional[str] = None
    remarks: Optional[str] = None


# ---- Procedures ----

@router.post("/procedures/{project_id}")
async def create_procedure(project_id: str, data: CommissioningProcedureCreate, db: AsyncSession = Depends(get_db)):
    # The parent sub-system must belong to the path project.
    parent = await db.execute(
        text("SELECT sub_system_id FROM sub_systems WHERE sub_system_id = :ssid AND project_id = :pid"),
        {"ssid": data.sub_system_id, "pid": project_id},
    )
    if parent.fetchone() is None:
        raise not_found("Sub-system", data.sub_system_id)
    result = await db.execute(
        text("""INSERT INTO commissioning_procedures
                (procedure_id, sub_system_id, project_id, procedure_code, procedure_name,
                 procedure_type, description, planned_date, responsible_party,
                 witness_required, witness_party)
                VALUES (gen_random_uuid(), :ssid, :pid, :code, :name, :ptype, :desc,
                        :pdate, :resp, :wreq, :wparty)
                RETURNING procedure_id"""),
        {"ssid": data.sub_system_id, "pid": project_id, "code": data.procedure_code,
         "name": data.procedure_name, "ptype": data.procedure_type, "desc": data.description,
         "pdate": data.planned_date, "resp": data.responsible_party,
         "wreq": data.witness_required, "wparty": data.witness_party}
    )
    await db.commit()
    return {"procedure_id": str(result.scalar()), "status": "created"}


@router.get("/procedures/{project_id}")
async def list_procedures(
    project_id: str,
    sub_system_id: Optional[str] = None,
    procedure_type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    page, page_size = clamp_page(page, page_size)
    query = """SELECT cp.*, ss.system_code, ss.system_name
               FROM commissioning_procedures cp
               JOIN sub_systems ss ON cp.sub_system_id = ss.sub_system_id
               WHERE cp.project_id = :pid AND ss.project_id = :pid"""
    params = {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    if sub_system_id:
        query += " AND cp.sub_system_id = :ssid"
        params["ssid"] = sub_system_id
    if procedure_type:
        query += " AND cp.procedure_type = :ptype"
        params["ptype"] = procedure_type
    if status:
        query += " AND cp.status = :st"
        params["st"] = status
    query += " ORDER BY cp.procedure_type, cp.planned_date LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result]


@router.patch("/procedures/{project_id}/{procedure_id}")
async def update_procedure(project_id: str, procedure_id: str, data: CommissioningProcedureUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "procedure_id": procedure_id}
    for field in ["procedure_name", "status", "planned_date", "actual_date",
                   "responsible_party", "test_result", "attachments"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if not updates:
        return {"status": "no changes"}
    updates.append("updated_at = NOW()")
    await db.execute(
        text(f"UPDATE commissioning_procedures SET {', '.join(updates)} WHERE procedure_id = :procedure_id AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


# ---- Checklist Items ----

@router.post("/checklist/{project_id}")
async def create_checklist_item(project_id: str, data: ChecklistItemCreate, db: AsyncSession = Depends(get_db)):
    # The parent procedure must belong to the path project.
    parent = await db.execute(
        text("SELECT procedure_id FROM commissioning_procedures "
             "WHERE procedure_id = :prid AND project_id = :pid"),
        {"prid": data.procedure_id, "pid": project_id},
    )
    if parent.fetchone() is None:
        raise not_found("Commissioning procedure", data.procedure_id)
    await db.execute(
        text("""INSERT INTO commissioning_checklist (checklist_id, procedure_id, item_number, check_description, expected_result)
                VALUES (gen_random_uuid(), :pid_param, :inum, :desc, :expected)"""),
        {"pid_param": data.procedure_id, "inum": data.item_number,
         "desc": data.check_description, "expected": data.expected_result}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/checklist/{procedure_id}")
async def list_checklist_items(procedure_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM commissioning_checklist WHERE procedure_id = :pid ORDER BY item_number"),
        {"pid": procedure_id}
    )
    return [dict(r._mapping) for r in result]


@router.patch("/checklist/{checklist_id}")
async def update_checklist_item(checklist_id: str, data: ChecklistItemUpdate,
                                project_id: Optional[str] = None,
                                db: AsyncSession = Depends(get_db),
                                user: TokenData = Depends(get_current_user)):
    updates = []
    params = {"cid": checklist_id}
    for field in ["actual_result", "is_verified", "remarks"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    # verified_by is an identity field — derived from the token.
    if data.verified_by is not None or data.is_verified:
        updates.append("verified_by = :verified_by")
        params["verified_by"] = user.username
    if data.is_verified:
        updates.append("verified_date = NOW()")
    if not updates:
        return {"status": "no changes"}
    query = f"UPDATE commissioning_checklist SET {', '.join(updates)} WHERE checklist_id = :cid"
    if project_id:
        # Scope the child row through its parent procedure when a project is supplied.
        query += (" AND procedure_id IN (SELECT procedure_id FROM commissioning_procedures "
                  "WHERE project_id = :pid)")
        params["pid"] = project_id
    await db.execute(text(query), params)
    await db.commit()
    return {"status": "updated"}


# ---- Commissioning Summary ----

@router.get("/summary/{project_id}")
async def commissioning_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    by_type = await db.execute(
        text("""SELECT procedure_type, COUNT(*) AS total,
                       SUM(CASE WHEN status = 'PASSED' THEN 1 ELSE 0 END) AS passed,
                       SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                       SUM(CASE WHEN status IN ('PENDING', 'SCHEDULED', 'IN_PROGRESS') THEN 1 ELSE 0 END) AS pending
                FROM commissioning_procedures WHERE project_id = :pid
                GROUP BY procedure_type ORDER BY procedure_type"""),
        {"pid": project_id}
    )
    by_system = await db.execute(
        text("""SELECT ss.system_code, ss.system_name,
                       COUNT(cp.*) AS total_procedures,
                       SUM(CASE WHEN cp.status = 'PASSED' THEN 1 ELSE 0 END) AS passed
                FROM sub_systems ss
                LEFT JOIN commissioning_procedures cp ON ss.sub_system_id = cp.sub_system_id
                                                     AND cp.project_id = ss.project_id
                WHERE ss.project_id = :pid
                GROUP BY ss.system_code, ss.system_name
                ORDER BY ss.system_code"""),
        {"pid": project_id}
    )
    return {
        "by_procedure_type": [dict(r._mapping) for r in by_type],
        "by_system": [dict(r._mapping) for r in by_system],
    }
