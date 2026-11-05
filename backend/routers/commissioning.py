"""Commissioning router — procedures, checklists, MC walkdown."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/commissioning", tags=["commissioning"])


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
    db: AsyncSession = Depends(get_db),
):
    query = """SELECT cp.*, ss.system_code, ss.system_name
               FROM commissioning_procedures cp
               JOIN sub_systems ss ON cp.sub_system_id = ss.sub_system_id
               WHERE cp.project_id = :pid"""
    params = {"pid": project_id}
    if sub_system_id:
        query += " AND cp.sub_system_id = :ssid"
        params["ssid"] = sub_system_id
    if procedure_type:
        query += " AND cp.procedure_type = :ptype"
        params["ptype"] = procedure_type
    if status:
        query += " AND cp.status = :st"
        params["st"] = status
    query += " ORDER BY cp.procedure_type, cp.planned_date"

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
async def update_checklist_item(checklist_id: str, data: ChecklistItemUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"cid": checklist_id}
    for field in ["actual_result", "is_verified", "verified_by", "remarks"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if data.is_verified:
        updates.append("verified_date = NOW()")
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE commissioning_checklist SET {', '.join(updates)} WHERE checklist_id = :cid"),
        params
    )
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
                WHERE ss.project_id = :pid
                GROUP BY ss.system_code, ss.system_name
                ORDER BY ss.system_code"""),
        {"pid": project_id}
    )
    return {
        "by_procedure_type": [dict(r._mapping) for r in by_type],
        "by_system": [dict(r._mapping) for r in by_system],
    }
