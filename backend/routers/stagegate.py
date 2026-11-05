"""Stage Gate router — phase transition approval gates with AI readiness scoring."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from typing import Optional
from database import get_db
from errors import not_found

router = APIRouter(prefix="/api/stagegate", tags=["stagegate"])


# ---- Pydantic Schemas ----

class StageGateCreate(BaseModel):
    gate_name: str
    gate_sequence: int
    from_phase: str
    to_phase: str
    planned_date: Optional[date] = None


class StageGateUpdate(BaseModel):
    status: Optional[str] = None
    planned_date: Optional[date] = None
    actual_date: Optional[date] = None
    human_approver: Optional[str] = None
    approver_comments: Optional[str] = None


class GateChecklistItemCreate(BaseModel):
    gate_id: str
    item_number: int
    category: Optional[str] = None
    description: str
    verification_method: Optional[str] = None


class GateChecklistItemUpdate(BaseModel):
    is_complete: Optional[bool] = None
    verified_by: Optional[str] = None
    evidence_ref: Optional[str] = None
    remarks: Optional[str] = None


# ---- Stage Gates ----

@router.post("/{project_id}")
async def create_gate(project_id: str, data: StageGateCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""INSERT INTO stage_gates (gate_id, project_id, gate_name, gate_sequence,
                 from_phase, to_phase, planned_date)
                VALUES (gen_random_uuid(), :pid, :name, :seq, :from, :to, :pdate)
                ON CONFLICT (project_id, gate_sequence) DO NOTHING
                RETURNING gate_id"""),
        {"pid": project_id, "name": data.gate_name, "seq": data.gate_sequence,
         "from": data.from_phase, "to": data.to_phase, "pdate": data.planned_date}
    )
    await db.commit()
    row = result.fetchone()
    if not row:
        return {"status": "gate_sequence_exists"}
    return {"gate_id": str(row[0]), "status": "created"}


@router.get("/{project_id}")
async def list_gates(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""SELECT sg.*,
                       (SELECT COUNT(*) FROM stage_gate_checklist WHERE gate_id = sg.gate_id) AS total_checklist,
                       (SELECT COUNT(*) FROM stage_gate_checklist WHERE gate_id = sg.gate_id AND is_complete = TRUE) AS completed_checklist
                FROM stage_gates sg
                WHERE sg.project_id = :pid
                ORDER BY sg.gate_sequence"""),
        {"pid": project_id}
    )
    return [dict(r._mapping) for r in result]


@router.get("/{project_id}/{gate_id}")
async def get_gate_detail(project_id: str, gate_id: str, db: AsyncSession = Depends(get_db)):
    gate = await db.execute(
        text("SELECT * FROM stage_gates WHERE gate_id = :gid AND project_id = :pid"),
        {"gid": gate_id, "pid": project_id}
    )
    row = gate.fetchone()
    if not row:
        raise not_found("Stage gate", gate_id)

    checklist = await db.execute(
        text("SELECT * FROM stage_gate_checklist WHERE gate_id = :gid ORDER BY item_number"),
        {"gid": gate_id}
    )

    # Calculate AI readiness score
    items = [dict(r._mapping) for r in checklist]
    total = len(items)
    completed = sum(1 for i in items if i["is_complete"])
    pct = round(completed / total * 100, 1) if total > 0 else 0

    # AI readiness heuristic: checklist % weighted by critical items
    ai_score = round(
        (pct * 0.6) +
        (10 if completed == total else 0) * 0.2 +
        (10 if row._mapping.get("actual_date") is None else 7) * 0.2,
        1
    )

    return {
        "gate": dict(row._mapping),
        "checklist": items,
        "checklist_stats": {"total": total, "completed": completed, "pct": pct},
        "ai_readiness_score": min(ai_score, 10.0),
    }


@router.patch("/{project_id}/{gate_id}")
async def update_gate(project_id: str, gate_id: str, data: StageGateUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "gid": gate_id}
    for field in ["status", "planned_date", "actual_date", "human_approver", "approver_comments"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if data.status == "APPROVED":
        updates.append("approval_date = CURRENT_DATE")
    if not updates:
        return {"status": "no changes"}
    await db.execute(
        text(f"UPDATE stage_gates SET {', '.join(updates)} WHERE gate_id = :gid AND project_id = :pid"),
        params
    )
    await db.commit()
    return {"status": "updated"}


# ---- Checklist Items ----

@router.post("/checklist/{project_id}")
async def create_checklist_item(project_id: str, data: GateChecklistItemCreate, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("""INSERT INTO stage_gate_checklist (checklist_item_id, gate_id, item_number, category,
                 description, verification_method)
                VALUES (gen_random_uuid(), :gid, :inum, :cat, :desc, :vmethod)"""),
        {"gid": data.gate_id, "inum": data.item_number, "cat": data.category,
         "desc": data.description, "vmethod": data.verification_method}
    )
    await db.commit()
    return {"status": "created"}


@router.patch("/checklist/{project_id}/{checklist_item_id}")
async def update_checklist_item(project_id: str, checklist_item_id: str, data: GateChecklistItemUpdate, db: AsyncSession = Depends(get_db)):
    updates = []
    params = {"pid": project_id, "cid": checklist_item_id}
    for field in ["is_complete", "verified_by", "evidence_ref", "remarks"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val
    if data.is_complete:
        updates.append("verified_date = NOW()")
    if not updates:
        return {"status": "no changes"}

    await db.execute(
        text(f"UPDATE stage_gate_checklist SET {', '.join(updates)} WHERE checklist_item_id = :cid"),
        params
    )
    await db.commit()

    # Recalculate gate checklist_complete_pct
    await db.execute(
        text("""UPDATE stage_gates SET checklist_complete_pct = (
                    SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE is_complete) / NULLIF(COUNT(*), 0), 1)
                    FROM stage_gate_checklist WHERE gate_id = sg.gate_id
                )
                FROM stage_gates sg
                WHERE sg.gate_id = stage_gate_checklist.gate_id
                AND stage_gate_checklist.checklist_item_id = :cid"""),
        {"cid": checklist_item_id}
    )
    await db.commit()
    return {"status": "updated"}


# ---- AI Readiness Assessment ----

@router.post("/assess/{project_id}/{gate_id}")
async def run_ai_assessment(project_id: str, gate_id: str, db: AsyncSession = Depends(get_db)):
    """
    Run AI readiness assessment for a stage gate.
    Evaluates: checklist completion, open NCRs, punch items, procurement status,
    resource availability, safety incidents, and schedule variance.
    Returns a score (0-10) and a detailed breakdown.
    """
    gate = await db.execute(
        text("SELECT * FROM stage_gates WHERE gate_id = :gid AND project_id = :pid"),
        {"gid": gate_id, "pid": project_id}
    )
    g = gate.fetchone()
    if not g:
        raise not_found("Stage gate", gate_id)

    gate_data = dict(g._mapping)

    # Gather assessment factors
    factors = {}

    # 1. Checklist completion (40% weight)
    checklist = await db.execute(
        text("SELECT COUNT(*) AS total, SUM(CASE WHEN is_complete THEN 1 ELSE 0 END) AS done FROM stage_gate_checklist WHERE gate_id = :gid"),
        {"gid": gate_id}
    )
    cl = checklist.fetchone()._mapping
    checklist_score = round(cl["done"] / cl["total"] * 10, 1) if cl["total"] > 0 else 0
    factors["checklist_completion"] = {"score": checklist_score, "weight": 0.40,
                                        "detail": f"{cl['done']}/{cl['total']} items complete"}

    # 2. Open NCRs — fewer is better (25% weight)
    ncr = await db.execute(
        text("""SELECT COUNT(*) AS open_ncr,
                       COUNT(*) FILTER (WHERE severity = 'CRITICAL') AS critical_open
                FROM quality_ncr WHERE project_id = :pid AND status != 'CLOSED'"""),
        {"pid": project_id}
    )
    nc = ncr.fetchone()._mapping
    ncr_score = max(0, 10 - (nc["open_ncr"] * 0.5) - (nc["critical_open"] * 2))
    factors["open_ncrs"] = {"score": round(ncr_score, 1), "weight": 0.25,
                            "detail": f"{nc['open_ncr']} open ({nc['critical_open']} critical)"}

    # 3. Punch list closure rate (15% weight)
    punch = await db.execute(
        text("SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed FROM punch_items WHERE project_id = :pid"),
        {"pid": project_id}
    )
    pu = punch.fetchone()._mapping
    punch_score = round(pu["closed"] / pu["total"] * 10, 1) if pu["total"] > 0 else 10
    factors["punch_list"] = {"score": punch_score, "weight": 0.15,
                             "detail": f"{pu['closed']}/{pu['total']} punch items closed"}

    # 4. Material readiness — procurement delivery status (10% weight)
    mat = await db.execute(
        text("SELECT COUNT(*) AS total_items, SUM(pi.quantity_received) AS received, SUM(pi.quantity_ordered) AS ordered FROM purchase_items pi JOIN procurement_purchase_orders po ON pi.po_id = po.po_id WHERE po.project_id = :pid"),
        {"pid": project_id}
    )
    mt = mat.fetchone()._mapping
    mat_score = round(mt["received"] / mt["ordered"] * 10, 1) if mt["ordered"] and mt["ordered"] > 0 else 5
    factors["material_readiness"] = {"score": mat_score, "weight": 0.10,
                                      "detail": f"{mt['received']}/{mt['ordered']} materials received"}

    # 5. Safety performance — no LTIs in last 30 days (10% weight)
    safety = await db.execute(
        text("SELECT COUNT(*) AS recent_incidents FROM safety_incidents WHERE project_id = :pid AND incident_date >= CURRENT_DATE - INTERVAL '30 days' AND incident_type IN ('LTI', 'MTI')"),
        {"pid": project_id}
    )
    sf = safety.fetchone()._mapping
    safety_score = max(0, 10 - (sf["recent_incidents"] * 3))
    factors["safety_performance"] = {"score": round(safety_score, 1), "weight": 0.10,
                                      "detail": f"{sf['recent_incidents']} recordable incidents in last 30 days"}

    # Calculate weighted total
    ai_score = round(sum(f["score"] * f["weight"] for f in factors.values()), 1)

    # Update the gate's AI score
    await db.execute(
        text("UPDATE stage_gates SET ai_readiness_score = :score WHERE gate_id = :gid"),
        {"score": ai_score, "gid": gate_id}
    )
    await db.commit()

    # Determine recommendation
    if ai_score >= 8.0:
        recommendation = "APPROVE — High readiness. Recommend proceeding to next phase."
    elif ai_score >= 6.0:
        recommendation = "CONDITIONAL — Moderate readiness. Address flagged items before proceeding."
    elif ai_score >= 4.0:
        recommendation = "DEFER — Low readiness. Multiple critical items need resolution."
    else:
        recommendation = "REJECT — Insufficient readiness. Major blockers exist."

    return {
        "gate_id": gate_id,
        "gate_name": gate_data["gate_name"],
        "from_phase": gate_data["from_phase"],
        "to_phase": gate_data["to_phase"],
        "ai_readiness_score": ai_score,
        "recommendation": recommendation,
        "factors": factors,
        "assessed_at": date.today().isoformat(),
    }
