"""
Traceability Service — Full lifecycle trace from drawing to commissioning.

Supports:
- Forward trace: Drawing → MTO → PO → Material Receipt → Installation → Inspection → System Completion → Commissioning
- Backward trace: Commissioning → System → Inspection → Installation → Material → PO → MTO → Drawing
- Impact analysis: "If X is delayed, what downstream items are affected?"
"""
from typing import Optional
import asyncpg


class TraceabilityService:
    """Service for tracing deliverables through the full EPC lifecycle."""

    @staticmethod
    async def forward_trace(drawing_id: str, project_id: str, pool: asyncpg.Pool) -> dict:
        """Trace forward from a drawing to all downstream items.

        Queries are parallelized where possible to reduce latency.
        """
        async with pool.acquire() as conn:
            # 1. Drawing info (must complete first — needed by step 8)
            drawing = await conn.fetchrow(
                """SELECT d.*, ed.discipline_name
                   FROM drawings d JOIN engineering_disciplines ed ON d.discipline_id = ed.discipline_id
                   WHERE d.drawing_id = $1 AND d.project_id = $2""",
                drawing_id, project_id,
            )
            if not drawing:
                return {"error": "Drawing not found", "drawing_id": drawing_id}

            # 2-7. Run independent queries in parallel (single round-trip latency)
            import asyncio
            mto_items, materials, equipment, ndt, welds = await asyncio.gather(
                conn.fetch("SELECT * FROM material_takeoff WHERE drawing_id = $1 AND project_id = $2",
                           drawing_id, project_id),
                conn.fetch("SELECT * FROM drawing_materials WHERE drawing_id = $1 AND project_id = $2",
                           drawing_id, project_id),
                conn.fetch("SELECT * FROM drawing_equipment WHERE drawing_id = $1 AND project_id = $2",
                           drawing_id, project_id),
                conn.fetch("SELECT * FROM ndt_requests WHERE drawing_id = $1 AND project_id = $2",
                           drawing_id, project_id),
                conn.fetch("SELECT * FROM weld_tracking WHERE drawing_id = $1 AND project_id = $2",
                           drawing_id, project_id),
            )

            # 4. Related POs (depends on materials from step 2-7)
            material_types = [m["material_type"] for m in materials] if materials else []
            pos = []
            if material_types:
                pos = await conn.fetch(
                    """SELECT DISTINCT po.* FROM procurement_purchase_orders po
                       JOIN purchase_items pi ON po.po_id = pi.po_id
                       WHERE po.project_id = $1 AND pi.material_type = ANY($2)""",
                    project_id, material_types,
                )

            # 8. Related activities — use drawing_number as prefix match (more efficient than LIKE)
            drawing_number = drawing["drawing_number"]
            prefix = drawing_number.split("-")[0] if "-" in drawing_number else drawing_number[:6]
            activities = await conn.fetch(
                """SELECT DISTINCT a.* FROM activities a
                   WHERE a.project_id = $1 AND a.activity_code LIKE $2""",
                project_id, f"{prefix}%",
            )

            # Build trace chain
            trace = {
                "drawing": dict(drawing),
                "mto_items": [dict(m) for m in mto_items],
                "materials": [dict(m) for m in materials],
                "material_count": len(materials),
                "purchase_orders": [dict(p) for p in pos],
                "equipment": [dict(e) for e in equipment],
                "ndt_requests": [dict(n) for n in ndt],
                "weld_records": [dict(w) for w in welds],
                "related_activities": [dict(a) for a in activities],
            }

            # Derive status at each stage
            trace["stages"] = {
                "engineering": {
                    "status": drawing["status"],
                    "ifa": drawing.get("issued_for_info"),
                    "ifc": drawing.get("issued_for_construction"),
                },
                "mto": {
                    "items": len(mto_items),
                    "status": "COMPLETE" if mto_items else "PENDING",
                },
                "procurement": {
                    "pos_issued": len(pos),
                    "status": "COMPLETE" if pos else "PENDING",
                },
                "inspection": {
                    "ndt_total": len(ndt),
                    "ndt_completed": sum(1 for n in ndt if n["status"] == "COMPLETED"),
                    "status": "COMPLETE" if all(n["status"] == "COMPLETED" for n in ndt) else "IN_PROGRESS" if ndt else "PENDING",
                },
            }

            return trace

    @staticmethod
    async def backward_trace(system_code: str, project_id: str, pool: asyncpg.Pool) -> dict:
        """Trace backward from a sub-system to all upstream items."""
        async with pool.acquire() as conn:
            # Find sub-system
            sub_system = await conn.fetchrow(
                "SELECT * FROM sub_systems WHERE system_code = $1 AND project_id = $2",
                system_code, project_id,
            )
            if not sub_system:
                return {"error": "Sub-system not found", "system_code": system_code}

            ss = dict(sub_system)

            # Commissioning procedures
            procedures = await conn.fetch(
                "SELECT * FROM commissioning_procedures WHERE sub_system_id = $1 AND project_id = $2",
                ss["sub_system_id"], project_id,
            )

            # Punch items
            punch_items = await conn.fetch(
                "SELECT * FROM punch_items WHERE sub_system_id = $1 AND project_id = $2",
                ss["sub_system_id"], project_id,
            )

            # Related drawings (via discipline)
            drawings = await conn.fetch(
                """SELECT d.*, ed.discipline_name FROM drawings d
                   JOIN engineering_disciplines ed ON d.discipline_id = ed.discipline_id
                   WHERE d.project_id = $1 AND d.discipline_id = $2""",
                project_id, ss.get("discipline_id"),
            )

            # Related POs
            pos = await conn.fetch(
                "SELECT * FROM procurement_purchase_orders WHERE project_id = $1",
                project_id,
            )

            # Related activities
            activities = await conn.fetch(
                "SELECT * FROM activities WHERE project_id = $1 AND work_scope_category = $2",
                project_id, ss["system_code"][:10] if ss["system_code"] else "",
            )

            return {
                "sub_system": ss,
                "commissioning_procedures": [dict(p) for p in procedures],
                "commissioning_status": "COMPLETE" if all(
                    p["status"] == "PASSED" for p in procedures
                ) else "IN_PROGRESS" if procedures else "PENDING",
                "punch_items": [dict(p) for p in punch_items],
                "open_punches": sum(1 for p in punch_items if p["status"] != "CLOSED"),
                "related_drawings": [dict(d) for d in drawings],
                "purchase_orders": [dict(p) for p in pos],
                "related_activities": [dict(a) for a in activities],
            }

    @staticmethod
    async def impact_analysis(
        entity_type: str, entity_id: str, project_id: str, pool: asyncpg.Pool
    ) -> dict:
        """
        Analyze downstream impact if an entity is delayed.
        entity_type: 'drawing', 'activity', 'purchase_order', 'equipment'
        """
        async with pool.acquire() as conn:
            affected = {"drawings": [], "activities": [], "pos": [], "sub_systems": [], "commissioning": []}
            severity = "LOW"
            total_impact_items = 0

            if entity_type == "drawing":
                # Find the drawing
                drawing = await conn.fetchrow(
                    "SELECT * FROM drawings WHERE drawing_id = $1 AND project_id = $2",
                    entity_id, project_id,
                )
                if not drawing:
                    return {"error": "Entity not found"}

                # Find MTO items linked to this drawing
                mto = await conn.fetch(
                    "SELECT * FROM material_takeoff WHERE drawing_id = $1 AND project_id = $2",
                    entity_id, project_id,
                )
                # Find POs for these material types
                mto_types = [m["material_type"] for m in mto]
                if mto_types:
                    affected_pos = await conn.fetch(
                        """SELECT DISTINCT po.* FROM procurement_purchase_orders po
                           JOIN purchase_items pi ON po.po_id = pi.po_id
                           WHERE po.project_id = $1 AND pi.material_type = ANY($2)""",
                        project_id, mto_types,
                    )
                    affected["pos"] = [dict(p) for p in affected_pos]
                    total_impact_items += len(affected_pos)

                # Find NDT requests
                ndt = await conn.fetch(
                    "SELECT * FROM ndt_requests WHERE drawing_id = $1 AND project_id = $2",
                    entity_id, project_id,
                )
                if ndt:
                    affected["drawings"].append({"type": "ndt_requests", "count": len(ndt)})
                    total_impact_items += len(ndt)

                affected["drawings"].insert(0, dict(drawing))
                severity = "HIGH" if total_impact_items > 5 else "MEDIUM" if total_impact_items > 0 else "LOW"

            elif entity_type == "activity":
                activity = await conn.fetchrow(
                    "SELECT * FROM activities WHERE activity_id = $1 AND project_id = $2",
                    entity_id, project_id,
                )
                if not activity:
                    return {"error": "Entity not found"}

                # Find successor activities — scope by project to avoid
                # returning cross-project successors for a shared activity id.
                successors = await conn.fetch(
                    """SELECT a.* FROM activities a
                       JOIN activity_relationships ar ON a.activity_id = ar.successor_id
                       WHERE ar.predecessor_id = $1 AND a.project_id = $2""",
                    entity_id, project_id,
                )
                affected["activities"] = [dict(s) for s in successors]
                total_impact_items = len(successors)
                severity = "HIGH" if any(s["is_critical"] for s in successors) else "MEDIUM"

            elif entity_type == "purchase_order":
                po = await conn.fetchrow(
                    "SELECT * FROM procurement_purchase_orders WHERE po_id = $1 AND project_id = $2",
                    entity_id, project_id,
                )
                if not po:
                    return {"error": "Entity not found"}

                # Find construction activities waiting on these materials
                items = await conn.fetch(
                    """SELECT pi.* FROM purchase_items pi
                       JOIN procurement_purchase_orders po ON pi.po_id = po.po_id
                       WHERE pi.po_id = $1 AND po.project_id = $2""",
                    entity_id, project_id,
                )
                mat_types = [i["material_type"] for i in items]
                if mat_types:
                    related = await conn.fetch(
                        """SELECT DISTINCT a.* FROM activities a
                           JOIN weekly_planning_tasks wpt ON a.activity_id = wpt.activity_id
                           WHERE a.project_id = $1 AND wpt.planned_status ILIKE ANY($2)""",
                        project_id, [f"%{mt}%" for mt in mat_types],
                    )
                    affected["activities"] = [dict(r) for r in related]
                    total_impact_items = len(related)

                affected["pos"].append(dict(po))
                severity = "HIGH" if total_impact_items > 3 else "MEDIUM"

            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "total_affected_items": total_impact_items,
                "severity": severity,
                "affected": affected,
                "recommendation": (
                    "Urgent escalation required — critical path impact likely."
                    if severity == "HIGH"
                    else "Review and assess — moderate downstream impact possible."
                    if severity == "MEDIUM"
                    else "Low impact — monitor and proceed."
                ),
            }

    @staticmethod
    async def full_traceability_matrix(project_id: str, pool: asyncpg.Pool,
                                       page: int = 1, page_size: int = 500) -> list[dict]:
        """Generate a complete traceability matrix for the project (paginated)."""
        page = max(1, page)
        page_size = max(1, min(page_size, 500))
        async with pool.acquire() as conn:
            matrix = await conn.fetch(
                """SELECT
                       d.drawing_id, d.drawing_number, d.drawing_title,
                       ed.discipline_name,
                       d.status AS drawing_status,
                       d.issued_for_construction AS ifc,
                       COUNT(DISTINCT dm.material_id) AS material_count,
                       COUNT(DISTINCT de.equipment_id) AS equipment_count,
                       COUNT(DISTINCT CASE WHEN po.po_id IS NOT NULL THEN pi.purchase_item_id END) AS po_item_count,
                       COUNT(DISTINCT nr.ndt_id) AS ndt_count,
                       COUNT(DISTINCT wt.weld_id) AS weld_count,
                       AVG(COALESCE(nr.percent_complete, 0)) AS avg_ndt_pct
                   FROM drawings d
                   JOIN engineering_disciplines ed ON d.discipline_id = ed.discipline_id
                   LEFT JOIN drawing_materials dm ON d.drawing_id = dm.drawing_id AND d.project_id = dm.project_id
                   LEFT JOIN drawing_equipment de ON d.drawing_id = de.drawing_id AND d.project_id = de.project_id
                   LEFT JOIN material_takeoff mto ON d.drawing_id = mto.drawing_id AND d.project_id = mto.project_id
                   -- MTO → PO join: purchase_items alone has no project column, so
                   -- go through procurement_purchase_orders. Without this the same
                   -- material_type in another project inflated the count.
                   LEFT JOIN purchase_items pi ON mto.material_type = pi.material_type
                   LEFT JOIN procurement_purchase_orders po ON pi.po_id = po.po_id AND po.project_id = d.project_id
                   LEFT JOIN ndt_requests nr ON d.drawing_id = nr.drawing_id AND d.project_id = nr.project_id
                   LEFT JOIN weld_tracking wt ON d.drawing_id = wt.drawing_id AND d.project_id = wt.project_id
                   WHERE d.project_id = $1
                   GROUP BY d.drawing_id, d.drawing_number, d.drawing_title, ed.discipline_name, d.status, d.issued_for_construction
                   ORDER BY ed.discipline_name, d.drawing_number
                   LIMIT $2 OFFSET $3""",
                project_id, page_size, (page - 1) * page_size,
            )
            return [dict(r) for r in matrix]
