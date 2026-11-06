from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/equipment", tags=["equipment"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


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
async def list_equipment(project_id: str, category: Optional[str] = None,
                         page: int = 1, page_size: int = 500,
                         db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    # Totals cover the whole filtered set, not just the current page.
    count_query = ("SELECT COUNT(*) AS total, "
                   "SUM(CASE WHEN el.spec_status = 'APPROVED' THEN 1 ELSE 0 END) AS approved "
                   "FROM equipment_list el "
                   "JOIN equipment_categories ec ON el.category_id = ec.cat_id "
                   "WHERE el.project_id = :pid")
    params = {"pid": project_id}
    if category:
        count_query += " AND ec.category_name = :cat"
        params["cat"] = category
    totals = await db.execute(text(count_query), params)
    t = totals.fetchone()._mapping
    total = t["total"] or 0
    approved = t["approved"] or 0

    query = ("SELECT el.*, ec.category_name FROM equipment_list el "
             "JOIN equipment_categories ec ON el.category_id = ec.cat_id "
             "WHERE el.project_id = :pid")
    if category:
        query += " AND ec.category_name = :cat"
    query += " ORDER BY el.tag_number LIMIT :limit OFFSET :offset"
    params.update({"limit": page_size, "offset": (page - 1) * page_size})
    result = await db.execute(text(query), params)
    items = [dict(r._mapping) for r in result]

    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "total": total,
        "approved_count": approved,
        "conformance_pct": round(approved / total * 100, 1) if total else 0,
        "pagination": {
            "total": total, "page": page, "page_size": page_size,
            "total_pages": total_pages, "has_next": page < total_pages, "has_prev": page > 1,
        },
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
async def update_spec_status(equipment_id: str, data: SpecStatusUpdate,
                             project_id: Optional[str] = None,
                             db: AsyncSession = Depends(get_db)):
    valid_statuses = {"SUBMITTED", "APPROVED", "REJECTED", "PENDING"}
    if data.status.upper() not in valid_statuses:
        return {"status": "error", "message": f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}"}
    query = "UPDATE equipment_list SET spec_status = :st WHERE equipment_id = :eid"
    params = {"st": data.status.upper(), "eid": equipment_id}
    if project_id:
        query += " AND project_id = :proj_pid"
        params["proj_pid"] = project_id
    await db.execute(text(query), params)
    await db.commit()
    return {"status": "updated"}
