from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api/procurement", tags=["procurement"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


class POItem(BaseModel):
    material_type: str
    material_spec: Optional[str] = None
    quantity_ordered: float
    unit: str
    unit_price: Optional[float] = None


class POCreate(BaseModel):
    po_number: str
    vendor_name: str
    order_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    items: list[POItem]


class MaterialReceipt(BaseModel):
    quantity_received: float
    received_date: Optional[date] = None


@router.post("/purchase-order/{project_id}")
async def create_po(project_id: str, po_data: POCreate, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        result = await db.execute(
            text("INSERT INTO procurement_purchase_orders (po_id, project_id, po_number, vendor_name, order_date, expected_delivery_date) "
                 "VALUES (gen_random_uuid(), :pid, :ponum, :vendor, :odate, :edate) RETURNING po_id"),
            {"pid": project_id, "ponum": po_data.po_number, "vendor": po_data.vendor_name,
             "odate": po_data.order_date, "edate": po_data.expected_delivery_date}
        )
        po_id = result.scalar()
        for item in po_data.items:
            await db.execute(
                text("INSERT INTO purchase_items (purchase_item_id, po_id, material_type, material_spec, quantity_ordered, unit, unit_price) "
                     "VALUES (gen_random_uuid(), :poid, :mtype, :mspec, :qty, :unit, :uprice)"),
                {"poid": str(po_id), "mtype": item.material_type, "mspec": item.material_spec,
                 "qty": item.quantity_ordered, "unit": item.unit, "uprice": item.unit_price}
            )
    return {"po_id": str(po_id)}


@router.get("/purchase-orders/{project_id}")
async def list_pos(project_id: str, page: int = 1, page_size: int = 50, db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    total_result = await db.execute(
        text("SELECT COUNT(*) FROM procurement_purchase_orders WHERE project_id = :pid"),
        {"pid": project_id}
    )
    total = total_result.scalar() or 0
    result = await db.execute(
        text("SELECT * FROM procurement_purchase_orders WHERE project_id = :pid "
             "ORDER BY order_date DESC LIMIT :limit OFFSET :offset"),
        {"pid": project_id, "limit": page_size, "offset": (page - 1) * page_size}
    )
    items = [dict(r._mapping) for r in result]
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "pagination": {
            "total": total, "page": page, "page_size": page_size,
            "total_pages": total_pages, "has_next": page < total_pages, "has_prev": page > 1,
        },
    }


@router.get("/material-totals/{project_id}")
async def get_material_totals(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT pi.material_type, SUM(pi.quantity_ordered * COALESCE(mto.unit_weight_kg, 0)) AS total_weight_kg "
             "FROM purchase_items pi LEFT JOIN material_takeoff mto ON pi.material_type = mto.material_type "
             "AND pi.material_spec = mto.material_spec AND mto.project_id = :pid "
             "WHERE pi.po_id IN (SELECT po_id FROM procurement_purchase_orders WHERE project_id = :pid) "
             "GROUP BY pi.material_type"),
        {"pid": project_id}
    )
    return {"material_weight_totals": [dict(r._mapping) for r in result]}


@router.patch("/material-receipt/{purchase_item_id}")
async def record_receipt(purchase_item_id: str, data: MaterialReceipt,
                         project_id: Optional[str] = None,
                         db: AsyncSession = Depends(get_db)):
    query = ("UPDATE purchase_items SET quantity_received = :qty, "
             "received_date = COALESCE(:rdate, CURRENT_DATE) WHERE purchase_item_id = :pid")
    params = {"qty": data.quantity_received, "rdate": data.received_date, "pid": purchase_item_id}
    if project_id:
        # purchase_items has no project column; scope through its PO.
        query += (" AND po_id IN (SELECT po_id FROM procurement_purchase_orders "
                  "WHERE project_id = :proj_pid)")
        params["proj_pid"] = project_id
    await db.execute(text(query), params)
    await db.commit()
    return {"status": "updated"}
