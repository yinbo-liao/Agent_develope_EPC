from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


class EquipmentCreate(BaseModel):
    category_id: int
    tag_number: str
    equipment_name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    specification_doc: Optional[str] = None


class SpecStatusUpdate(BaseModel):
    status: str


@router.get("/{project_id}")
async def list_equipment(project_id: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = ("SELECT el.*, ec.category_name FROM equipment_list el "
             "JOIN equipment_categories ec ON el.category_id = ec.cat_id "
             "WHERE el.project_id = :pid")
    params = {"pid": project_id}
    if category:
        query += " AND ec.category_name = :cat"
        params["cat"] = category
    result = await db.execute(text(query), params)
    items = [dict(r._mapping) for r in result]

    approved = sum(1 for i in items if i.get("spec_status") == "APPROVED")
    return {
        "items": items,
        "total": len(items),
        "approved_count": approved,
        "conformance_pct": round(approved / len(items) * 100, 1) if items else 0,
    }


@router.post("/{project_id}")
async def create_equipment(project_id: str, data: EquipmentCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO equipment_list (equipment_id, project_id, category_id, tag_number, equipment_name, manufacturer, model, specification_doc) "
             "VALUES (gen_random_uuid(), :pid, :cid, :tag, :name, :mfr, :model, :spec)"),
        {"pid": project_id, "cid": data.category_id, "tag": data.tag_number,
         "name": data.equipment_name, "mfr": data.manufacturer, "model": data.model, "spec": data.specification_doc}
    )
    await db.commit()
    return {"status": "created"}


@router.patch("/{equipment_id}/spec-status")
async def update_spec_status(equipment_id: str, data: SpecStatusUpdate, db: AsyncSession = Depends(get_db)):
    valid_statuses = {"SUBMITTED", "APPROVED", "REJECTED", "PENDING"}
    if data.status.upper() not in valid_statuses:
        return {"status": "error", "message": f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}"}
    await db.execute(
        text("UPDATE equipment_list SET spec_status = :st WHERE equipment_id = :eid"),
        {"st": data.status.upper(), "eid": equipment_id}
    )
    await db.commit()
    return {"status": "updated"}
