from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
import csv, io, uuid
from database import get_db
from pagination import PaginationParams, paginate
from auth import require_role
from errors import not_found, bad_request

router = APIRouter(prefix="/api/engineering", tags=["engineering"])

MAX_PAGE_SIZE = 500


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size


async def get_discipline_maps(db: AsyncSession) -> tuple[dict[str, int], dict[int, str]]:
    """Load the authoritative discipline name<->id maps from the database.

    The previous hardcoded dicts omitted ARCHITECTURE_DECORATION (discipline 6)
    and assumed serial IDs, so imports silently rejected valid disciplines.
    """
    result = await db.execute(text("SELECT discipline_id, discipline_name FROM engineering_disciplines"))
    rows = [dict(r._mapping) for r in result]
    name_to_id = {str(r["discipline_name"]).upper(): r["discipline_id"] for r in rows}
    id_to_name = {r["discipline_id"]: r["discipline_name"] for r in rows}
    return name_to_id, id_to_name


class DrawingCreate(BaseModel):
    drawing_number: str
    discipline_id: int
    drawing_title: Optional[str] = None
    drawing_type: Optional[str] = None
    planned_issue_date: Optional[date] = None
    weight_kg: Optional[float] = None


@router.post("/drawings/{project_id}")
async def create_drawing(project_id: str, drawing: DrawingCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO drawings (drawing_id, project_id, discipline_id, drawing_number, drawing_title, drawing_type, planned_issue_date, weight_kg) "
             "VALUES (gen_random_uuid(), :pid, :did, :dn, :dt, :dtype, :pdate, :wkg)"),
        {"pid": project_id, "did": drawing.discipline_id, "dn": drawing.drawing_number,
         "dt": drawing.drawing_title, "dtype": drawing.drawing_type,
         "pdate": drawing.planned_issue_date, "wkg": drawing.weight_kg}
    )
    await db.commit()
    return {"status": "created"}


@router.get("/summary/{project_id}")
async def get_engineering_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("SELECT d.discipline_name, COUNT(drw.*) AS total_drawings, "
             "COALESCE(SUM(drw.weight_kg), 0) AS total_weight_kg, "
             "COUNT(*) FILTER (WHERE drw.status = 'IFC') AS ifc_drawings "
             "FROM drawings drw JOIN engineering_disciplines d ON drw.discipline_id = d.discipline_id "
             "WHERE drw.project_id = :pid GROUP BY d.discipline_name"),
        {"pid": project_id}
    )
    mto_rows = await db.execute(
        text("SELECT ed.discipline_name, COALESCE(SUM(mto.quantity * mto.unit_weight_kg), 0) AS mto_weight_kg "
             "FROM material_takeoff mto JOIN engineering_disciplines ed ON mto.discipline_id = ed.discipline_id "
             "WHERE mto.project_id = :pid GROUP BY ed.discipline_name"),
        {"pid": project_id}
    )
    return {
        "drawings": [dict(r._mapping) for r in rows],
        "mto_weights": [dict(r._mapping) for r in mto_rows],
    }


@router.get("/drawings/{project_id}")
async def list_drawings(project_id: str, discipline_id: Optional[int] = None,
                        page: int = 1, page_size: int = 50, db: AsyncSession = Depends(get_db)):
    page, page_size = clamp_page(page, page_size)
    base = ("FROM drawings drw JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
            "WHERE drw.project_id = :pid")
    params = {"pid": project_id}
    # Apply every filter BEFORE building/running the count query so the total
    # reflects the same filter set as the page.
    if discipline_id:
        base += " AND drw.discipline_id = :did"
        params["did"] = discipline_id
    total_result = await db.execute(text(f"SELECT COUNT(*) {base}"), params)
    total = total_result.scalar() or 0
    # Paginated fetch
    query = (f"SELECT drw.*, ed.discipline_name {base} "
             "ORDER BY ed.discipline_id, drw.drawing_number "
             "LIMIT :limit OFFSET :offset")
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    result = await db.execute(text(query), params)
    items = [dict(r._mapping) for r in result]
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "pagination": {
            "total": total, "page": page, "page_size": page_size,
            "total_pages": total_pages, "has_next": page < total_pages, "has_prev": page > 1,
        },
    }


@router.post("/mto/{project_id}")
async def create_mto(project_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("INSERT INTO material_takeoff (mto_id, project_id, discipline_id, drawing_id, material_type, material_spec, quantity, unit, unit_weight_kg) "
             "VALUES (gen_random_uuid(), :pid, :did, :drawid, :mtype, :mspec, :qty, :unit, :uwkg)"),
        {"pid": project_id, "did": data["discipline_id"], "drawid": data.get("drawing_id"),
         "mtype": data["material_type"], "mspec": data.get("material_spec"),
         "qty": data["quantity"], "unit": data["unit"], "uwkg": data.get("unit_weight_kg", 0)}
    )
    await db.commit()
    return {"status": "created"}


# ── Materials ────────────────────────────────────────────────────────

@router.get("/materials/{project_id}")
async def get_drawing_materials(
    project_id: str,
    discipline_id: Optional[int] = None,
    drawing_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """Get drawing materials with procurement planning summary.

    `procurement_planning` is aggregated from the returned page only, keeping
    the payload bounded. The default page size matches the historical
    unbounded response for typical projects.
    """
    page, page_size = clamp_page(page, page_size)
    query = (
        "SELECT dm.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev, "
        "drw.issued_for_info, drw.issued_for_construction, "
        "ed.discipline_name FROM drawing_materials dm "
        "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
        "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
        "WHERE dm.project_id = :pid"
    )
    params = {"pid": project_id}
    if discipline_id:
        query += " AND drw.discipline_id = :did"
        params["did"] = discipline_id
    if drawing_id:
        query += " AND dm.drawing_id = :drawid"
        params["drawid"] = drawing_id
    query += " ORDER BY drw.discipline_id, drw.drawing_number, dm.piece_mark LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    rows = [dict(r._mapping) for r in result]

    # Procurement planning aggregation
    groups: dict[str, dict] = {}
    for r in rows:
        cat = r.get("material_category") or r.get("material_type") or ""
        typ = r.get("material_type") or ""
        sz = r.get("size") or r.get("diameter") or "-"
        thick = r.get("material_thickness") or "-"
        grade = r.get("material_grade") or "-"
        mat_class = r.get("material_class") or "-"
        po_stat = r.get("po_status") or "-"
        key = f"{cat}|{typ}|{sz}|{thick}|{grade}|{mat_class}|{po_stat}"
        if key not in groups:
            groups[key] = {
                "material_category": cat, "material_type": typ, "size": sz,
                "thickness": thick, "grade": grade, "material_class": mat_class,
                "po_status": po_stat, "count": 0,
                "total_length_m": 0.0, "total_weight_kg": 0.0,
            }
        groups[key]["count"] += 1
        groups[key]["total_length_m"] += float(r.get("material_length") or 0)
        groups[key]["total_weight_kg"] += float(r.get("total_weight") or 0)

    str_cat_order = {"Steel Plate": 0, "Bulb Plate": 1, "Angle Bar": 2, "I-BEAM": 3, "FlatBar": 4, "Pipe": 5}
    pip_type_order = {"Pipe": 0, "Flange": 1, "Elbow": 2, "Tee": 3, "Reducer": 4, "Blank": 5, "Bellow": 6, "Bolt/Nuts": 7, "Weldolet": 8}
    mat_order = {"CS": 0, "SS": 1, "DSS": 2, "CUNI": 3, "GRE": 4, "TI": 5}
    if discipline_id == 2:
        planning = sorted(groups.values(), key=lambda x: (pip_type_order.get(x["material_type"], 99), mat_order.get(x.get("material_category", ""), 99)))
    else:
        planning = sorted(groups.values(), key=lambda x: (str_cat_order.get(x.get("material_category", ""), 99), mat_order.get(x.get("material_class", ""), 99)))

    return {"items": rows, "procurement_planning": planning}


# ── Equipment ────────────────────────────────────────────────────────

@router.get("/equipment/{project_id}")
async def get_drawing_equipment(
    project_id: str,
    discipline_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """Get drawing equipment with procurement planning summary."""
    page, page_size = clamp_page(page, page_size)
    query = (
        "SELECT de.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev, "
        "drw.issued_for_info, drw.issued_for_construction, "
        "ed.discipline_name FROM drawing_equipment de "
        "JOIN drawings drw ON de.drawing_id = drw.drawing_id "
        "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
        "WHERE de.project_id = :pid"
    )
    params = {"pid": project_id}
    if discipline_id:
        query += " AND drw.discipline_id = :did"
        params["did"] = discipline_id
    query += " ORDER BY drw.discipline_id, drw.drawing_number, de.equipment_tag LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    result = await db.execute(text(query), params)
    rows = [dict(r._mapping) for r in result]

    summary: dict[str, dict] = {}
    for r in rows:
        key = r.get("equipment_type") or "Uncategorized"
        if key not in summary:
            summary[key] = {"equipment_type": key, "count": 0, "total_weight": 0.0, "fat_approved": 0}
        summary[key]["count"] += 1
        summary[key]["total_weight"] += float(r.get("weight") or 0)
        if r.get("fat_status") == "APPROVED":
            summary[key]["fat_approved"] += 1

    planning = [
        {"equipment_type": k, "count": v["count"],
         "total_weight_kg": round(v["total_weight"], 1),
         "fat_approved": v["fat_approved"], "fat_pending": v["count"] - v["fat_approved"]}
        for k, v in summary.items()
    ]
    return {"items": rows, "procurement_planning": planning}


# ── Change Summary ───────────────────────────────────────────────────

@router.get("/change-summary/{project_id}")
async def get_change_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get change log summary — drawings/materials added/deleted counts."""
    result = await db.execute(
        text("SELECT entity_type, action, COUNT(*) as count "
             "FROM change_log WHERE project_id = :pid "
             "GROUP BY entity_type, action"),
        {"pid": project_id}
    )
    summary = {"drawings_added": 0, "drawings_deleted": 0,
               "materials_added": 0, "materials_deleted": 0}
    for r in result:
        row = dict(r._mapping)
        if row["entity_type"] == "drawing" and row["action"] == "create":
            summary["drawings_added"] = row["count"]
        elif row["entity_type"] == "drawing" and row["action"] == "delete":
            summary["drawings_deleted"] = row["count"]
        elif row["entity_type"] == "material" and row["action"] == "create":
            summary["materials_added"] = row["count"]
        elif row["entity_type"] == "material" and row["action"] == "delete":
            summary["materials_deleted"] = row["count"]
    return summary


# ── Delete Drawing (with cascade) ──────────────────────────────────────

@router.delete("/drawings/{project_id}/{drawing_id}")
async def delete_drawing(project_id: str, drawing_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a drawing and its associated materials, equipment, and MTO records."""
    # Find drawing for change log
    result = await db.execute(
        text("""SELECT drw.drawing_number, ed.discipline_name
                FROM drawings drw
                JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
                WHERE drw.drawing_id = :did AND drw.project_id = :pid"""),
        {"did": drawing_id, "pid": project_id}
    )
    row = result.fetchone()
    if not row:
        return {"status": "not_found"}
    dn = row._mapping["drawing_number"]
    disc = row._mapping["discipline_name"]

    # Cascade delete (every delete is project-scoped, not just the drawing row)
    await db.execute(text("DELETE FROM drawing_materials WHERE drawing_id = :did AND project_id = :pid"),
                     {"did": drawing_id, "pid": project_id})
    await db.execute(text("DELETE FROM drawing_equipment WHERE drawing_id = :did AND project_id = :pid"),
                     {"did": drawing_id, "pid": project_id})
    await db.execute(text("DELETE FROM material_takeoff WHERE drawing_id = :did AND project_id = :pid"),
                     {"did": drawing_id, "pid": project_id})
    await db.execute(text("DELETE FROM drawings WHERE drawing_id = :did AND project_id = :pid"),
                     {"did": drawing_id, "pid": project_id})

    # Log change
    await db.execute(
        text("""INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name)
                VALUES (gen_random_uuid(), :pid, 'drawing', :eid, 'delete', :enum, :disc)"""),
        {"pid": project_id, "eid": drawing_id, "enum": dn, "disc": disc}
    )
    await db.commit()
    return {"status": "deleted", "drawing_id": drawing_id}


# ── Delete Material ────────────────────────────────────────────────────

@router.delete("/materials/{project_id}/{material_id}")
async def delete_material(project_id: str, material_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a material record."""
    result = await db.execute(
        text("""SELECT dm.piece_mark, ed.discipline_name
                FROM drawing_materials dm
                JOIN drawings drw ON dm.drawing_id = drw.drawing_id
                JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
                WHERE dm.material_id = :mid AND dm.project_id = :pid"""),
        {"mid": material_id, "pid": project_id}
    )
    row = result.fetchone()
    if not row:
        return {"status": "not_found"}
    pm = row._mapping["piece_mark"]
    disc = row._mapping["discipline_name"]

    await db.execute(text("DELETE FROM drawing_materials WHERE material_id = :mid AND project_id = :pid"),
                     {"mid": material_id, "pid": project_id})

    await db.execute(
        text("""INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name)
                VALUES (gen_random_uuid(), :pid, 'material', :eid, 'delete', :enum, :disc)"""),
        {"pid": project_id, "eid": material_id, "enum": pm, "disc": disc}
    )
    await db.commit()
    return {"status": "deleted", "material_id": material_id}


# ── Material records (engineering team writes) ─────────────────────────

MATERIAL_PO_STATUSES = [
    "Info-AFI",
    "Structure-requested",
    "piping-requested",
    "PR-Raised",
    "PO-issued",
    "Delivered",
]


class MaterialCreate(BaseModel):
    drawing_id: str
    material_type: str
    material_category: Optional[str] = None
    piece_mark: Optional[str] = None
    material_grade: Optional[str] = None
    material_thickness: Optional[str] = None
    size: Optional[str] = None
    diameter: Optional[str] = None
    material_class: Optional[str] = None
    material_length: Optional[float] = None
    material_weight: Optional[float] = None
    total_weight: Optional[float] = None
    po_status: Optional[str] = None


class MaterialStatusUpdate(BaseModel):
    po_status: str


@router.post("/materials/{project_id}", dependencies=[Depends(require_role("trade_lead"))])
async def create_material(project_id: str, data: MaterialCreate, db: AsyncSession = Depends(get_db)):
    """Add a material record to a drawing. Requires trade_lead or above."""
    if data.po_status and data.po_status not in MATERIAL_PO_STATUSES:
        raise bad_request(f"po_status must be one of {MATERIAL_PO_STATUSES}")

    result = await db.execute(
        text("""SELECT drw.drawing_number, ed.discipline_name
                FROM drawings drw
                JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
                WHERE drw.drawing_id = :did AND drw.project_id = :pid"""),
        {"did": data.drawing_id, "pid": project_id}
    )
    drawing = result.fetchone()
    if not drawing:
        raise not_found("Drawing", data.drawing_id)
    disc = drawing._mapping["discipline_name"]

    length = data.material_length or 0
    unit_weight = data.material_weight or 0
    total_weight = data.total_weight
    if total_weight is None:
        total_weight = round(unit_weight * length, 3)

    result = await db.execute(
        text("""INSERT INTO drawing_materials
                (material_id, drawing_id, project_id, piece_mark, material_grade,
                 material_thickness, material_weight, material_type, size, diameter,
                 material_length, material_category, total_weight, material_class, po_status)
                VALUES (gen_random_uuid(), :did, :pid, :pm, :grade, :thk, :uweight, :mtype,
                        :size, :dia, :len, :cat, :tweight, :mclass, :status)
                RETURNING material_id"""),
        {"did": data.drawing_id, "pid": project_id, "pm": data.piece_mark or "-",
         "grade": data.material_grade, "thk": data.material_thickness, "uweight": unit_weight,
         "mtype": data.material_type, "size": data.size, "dia": data.diameter, "len": length,
         "cat": data.material_category or data.material_type, "tweight": total_weight,
         "mclass": data.material_class, "status": data.po_status}
    )
    material_id = result.fetchone()._mapping["material_id"]

    await db.execute(
        text("""INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name)
                VALUES (gen_random_uuid(), :pid, 'material', :eid, 'create', :enum, :disc)"""),
        {"pid": project_id, "eid": material_id, "enum": data.piece_mark or "-", "disc": disc}
    )
    await db.commit()
    return {"status": "created", "material_id": str(material_id)}


@router.patch("/materials/{project_id}/{material_id}/status",
              dependencies=[Depends(require_role("trade_lead"))])
async def update_material_status(project_id: str, material_id: str, data: MaterialStatusUpdate,
                                 db: AsyncSession = Depends(get_db)):
    """Change the PO status of a material record. Requires trade_lead or above."""
    if data.po_status not in MATERIAL_PO_STATUSES:
        raise bad_request(f"po_status must be one of {MATERIAL_PO_STATUSES}")

    result = await db.execute(
        text("""SELECT dm.piece_mark, ed.discipline_name
                FROM drawing_materials dm
                JOIN drawings drw ON dm.drawing_id = drw.drawing_id
                JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
                WHERE dm.material_id = :mid AND dm.project_id = :pid"""),
        {"mid": material_id, "pid": project_id}
    )
    row = result.fetchone()
    if not row:
        raise not_found("Material", material_id)
    pm = row._mapping["piece_mark"]
    disc = row._mapping["discipline_name"]

    await db.execute(
        text("UPDATE drawing_materials SET po_status = :status WHERE material_id = :mid AND project_id = :pid"),
        {"status": data.po_status, "mid": material_id, "pid": project_id}
    )
    await db.execute(
        text("""INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name)
                VALUES (gen_random_uuid(), :pid, 'material', :eid, 'update', :enum, :disc)"""),
        {"pid": project_id, "eid": material_id, "enum": pm, "disc": disc}
    )
    await db.commit()
    return {"status": "updated", "material_id": material_id, "po_status": data.po_status}


# ── CSV Import: Drawings ───────────────────────────────────────────────

@router.post("/import-drawings/{project_id}")
async def import_drawings_csv(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Import drawings from CSV. Columns: Drawing No, Discipline, Drawing Title, Rev,
       Issued for Info, Issued Date, Issued for Construction, Issued Date."""
    body = await request.body()
    text_data = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_data))
    imported, skipped, errors = 0, 0, []
    name_to_id, _ = await get_discipline_maps(db)

    for row_num, row in enumerate(reader, start=2):
        try:
            dn = (row.get("Drawing No") or "").strip()
            if not dn:
                skipped += 1; continue
            disc_name = (row.get("Discipline") or "").strip().upper()
            disc_id = name_to_id.get(disc_name) if disc_name else None
            if not disc_id:
                errors.append(f"Row {row_num}: unknown discipline '{disc_name}'"); skipped += 1; continue
            title = (row.get("Drawing Title") or "").strip()
            rev = (row.get("Rev") or row.get("Revision") or "").strip() or None
            ifa_raw = (row.get("Issued for Info") or "Yes").strip()
            ifa = "Yes" if ifa_raw.lower() in ("yes", "y", "1", "true") else "No"
            ifa_date = (row.get("Issued Date") or row.get("IFA Date") or "").strip() or None
            ifc_raw = (row.get("Issued for Construction") or "No").strip()
            ifc = "Yes" if ifc_raw.lower() in ("yes", "y", "1", "true") else "No"
            ifc_date = (row.get("IFC Date") or row.get("Issued Date (IFC)") or "").strip() or None
            status = "IFC" if ifc == "Yes" else ("IFA" if ifa == "Yes" else "WIP")

            drw_id = str(uuid.uuid4())
            # Savepoint per row: a bad row rolls back only itself, leaving the
            # outer import transaction usable for the remaining rows.
            async with db.begin_nested():
                await db.execute(
                    text("""INSERT INTO drawings (drawing_id, project_id, discipline_id, drawing_number,
                             drawing_title, status, revision, issued_for_info, issued_for_info_date,
                             issued_for_construction, issued_for_construction_date)
                            VALUES (:did, :pid, :disc_id, :dn, :title, :status, :rev, :ifa, :ifa_date, :ifc, :ifc_date)"""),
                    {"did": drw_id, "pid": project_id, "disc_id": disc_id, "dn": dn,
                     "title": title, "status": status, "rev": rev,
                     "ifa": ifa, "ifa_date": ifa_date, "ifc": ifc, "ifc_date": ifc_date})
                await db.execute(
                    text("""INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name)
                            VALUES (gen_random_uuid(), :pid, 'drawing', :eid, 'create', :enum, :disc)"""),
                    {"pid": project_id, "eid": drw_id, "enum": dn, "disc": disc_name})
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}"); skipped += 1
    await db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


# ── CSV Import: Materials ──────────────────────────────────────────────

@router.post("/import-materials/{project_id}")
async def import_materials_csv(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Import materials from CSV. Columns: Drawing No, Piece Mark, Material Grade,
       Thickness, Material Type, Size/OD, Material Cat, Unit Wt, Length, Total Wt."""
    body = await request.body()
    text_data = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_data))
    imported, skipped, errors = 0, 0, []
    _, id_to_name = await get_discipline_maps(db)

    for row_num, row in enumerate(reader, start=2):
        try:
            dn = (row.get("Drawing No") or "").strip()
            if not dn:
                skipped += 1; continue
            # Find drawing by number
            result = await db.execute(
                text("SELECT drawing_id, discipline_id FROM drawings WHERE drawing_number = :dn AND project_id = :pid"),
                {"dn": dn, "pid": project_id})
            drw = result.fetchone()
            if not drw:
                errors.append(f"Row {row_num}: drawing '{dn}' not found"); skipped += 1; continue

            pm = (row.get("Piece Mark") or "-").strip()
            grade = (row.get("Material Grade") or row.get("Grade") or "").strip() or None
            thick = (row.get("Thickness") or row.get("Material Thickness") or "").strip() or None
            mtype = (row.get("Material Type") or row.get("Type") or "").strip()
            sz = (row.get("Size") or "").strip() or None
            dia = (row.get("OD") or row.get("Pipe OD") or row.get("Diameter") or "").strip() or None
            mcat = (row.get("Material Cat") or row.get("Material Category") or "").strip() or None
            unit_wt = float(row.get("Unit Wt (kg/m)") or row.get("Unit Wt") or row.get("Material Weight") or 0)
            length = float(row.get("Length (m)") or row.get("Length") or 0)
            total_wt = float(row.get("Total Wt (kg)") or row.get("Total Wt") or row.get("Total Weight") or unit_wt * length)

            mat_id = str(uuid.uuid4())
            disc_id = drw._mapping["discipline_id"]
            disc_name = id_to_name.get(disc_id, "UNKNOWN")
            async with db.begin_nested():
                await db.execute(
                    text("""INSERT INTO drawing_materials (material_id, drawing_id, project_id, piece_mark,
                             material_grade, material_thickness, material_weight, material_type,
                             size, diameter, material_length, material_category, total_weight)
                            VALUES (:mid, :did, :pid, :pm, :grade, :thick, :uwt, :mtype, :sz, :dia, :len, :mcat, :twt)"""),
                    {"mid": mat_id, "did": drw._mapping["drawing_id"], "pid": project_id,
                     "pm": pm, "grade": grade, "thick": thick, "uwt": unit_wt, "mtype": mtype,
                     "sz": sz, "dia": dia, "len": length, "mcat": mcat, "twt": total_wt})
                await db.execute(
                    text("""INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name)
                            VALUES (gen_random_uuid(), :pid, 'material', :eid, 'create', :enum, :disc)"""),
                    {"pid": project_id, "eid": mat_id, "enum": pm, "disc": disc_name})
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}"); skipped += 1
    await db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


# ── CSV Import: Equipment ──────────────────────────────────────────────

@router.post("/import-equipment/{project_id}")
async def import_equipment_csv(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Import equipment from CSV. Columns: Drawing No, Equipment Tag, Equipment Name,
       Equipment Detail, Install Location, Weight (kg), Equipment Type, Certification,
       FAT Status, Test Status, System Code, System Name, Delivery Date, Install Date, Remark."""
    body = await request.body()
    text_data = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_data))
    imported, skipped, errors = 0, 0, []

    for row_num, row in enumerate(reader, start=2):
        try:
            dn = (row.get("Drawing No") or "").strip()
            if not dn:
                skipped += 1; continue
            result = await db.execute(
                text("SELECT drawing_id FROM drawings WHERE drawing_number = :dn AND project_id = :pid"),
                {"dn": dn, "pid": project_id})
            drw = result.fetchone()
            if not drw:
                errors.append(f"Row {row_num}: drawing '{dn}' not found"); skipped += 1; continue

            tag = (row.get("Equipment Tag") or row.get("Equipment No") or row.get("Tag") or "").strip()
            name = (row.get("Equipment Name") or row.get("Name") or "").strip() or None
            detail = (row.get("Equipment Detail") or row.get("Detail") or "").strip() or None
            location = (row.get("Install Location") or row.get("Location") or "").strip() or None
            wt = float(row.get("Weight (kg)") or row.get("Weight") or 0)
            etype = (row.get("Equipment Type") or row.get("Type") or "").strip()
            cert = (row.get("Certification") or row.get("Equipment Certification") or row.get("Testing Report/Certs") or "").strip() or None
            fat = (row.get("FAT Status") or row.get("FAT") or "PENDING").strip().upper()
            test = (row.get("Test Status") or row.get("Mega/Loop Test") or row.get("Shop Test Status") or "").strip() or None
            sys_code = (row.get("System Code") or row.get("Sys Code") or "").strip() or None
            sys_name = (row.get("System Name") or row.get("Sys Name") or "").strip() or None
            del_date = (row.get("Delivery Date") or row.get("Schedule Delivery Date") or "").strip() or None
            inst_date = (row.get("Install Date") or row.get("Schedule Install Date") or "").strip() or None
            remark = (row.get("Remark") or row.get("Remarks") or "").strip() or None

            async with db.begin_nested():
                await db.execute(
                    text("""INSERT INTO drawing_equipment (equipment_id, drawing_id, project_id, equipment_tag,
                             equipment_name, equipment_detail, install_location, weight, equipment_type,
                             certification, fat_status, test_status, system_code, system_name,
                             schedule_delivery_date, schedule_install_date, remark)
                            VALUES (gen_random_uuid(), :did, :pid, :tag, :name, :detail, :loc, :wt, :etype,
                                    :cert, :fat, :test, :scode, :sname, :ddate, :idate, :remark)"""),
                    {"did": drw._mapping["drawing_id"], "pid": project_id, "tag": tag, "name": name,
                     "detail": detail, "loc": location, "wt": wt, "etype": etype, "cert": cert,
                     "fat": fat, "test": test, "scode": sys_code, "sname": sys_name,
                     "ddate": del_date, "idate": inst_date, "remark": remark})
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}"); skipped += 1
    await db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}
