"""
Function Tool Implementations — 11 database-query tools for the RAG AI system.

Each tool queries specific project database tables and returns structured results.
All tools receive the database pool as their first argument.

Tools:
  1. query_activities      — filter schedule activities
  2. query_drawings        — filter engineering drawings
  3. query_procurement     — filter purchase orders + items
  4. query_quality_ncr     — filter quality NCRs
  5. query_safety_incidents— filter HSE incidents
  6. query_training_records— filter training compliance
  7. query_stage_gates     — filter stage gate status
  8. query_conflicts       — filter project conflicts
  9. query_traceability    — forward/backward trace
  10. calculate_kpi        — compute project KPIs
  11. generate_report      — compose narrative report section
"""

import logging
from datetime import date, timedelta
from services.tools.registry import tool_registry
from services.tools.schema import (
    QueryActivitiesInput, QueryDrawingsInput, QueryProcurementInput,
    QueryQualityNCRInput, QuerySafetyIncidentsInput, QueryTrainingRecordsInput,
    QueryStageGatesInput, QueryConflictsInput, QueryTraceabilityInput,
    CalculateKPIInput, GenerateReportInput,
)

logger = logging.getLogger(__name__)


def _validate_input(model_cls, **kwargs):
    """Validate tool arguments against the registered Pydantic schema.

    Raises pydantic.ValidationError; the registry wrapper converts that into a
    ToolResult(success=False), so bad LLM arguments never reach raw SQL.
    """
    return model_cls(**kwargs)

# ── Tool 1: Query Activities ─────────────────────────────────────────────

@tool_registry.register(
    name="query_activities",
    description="Query project schedule activities by status, critical path, or work scope. Returns activity codes, names, progress, float, and status.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "status": {"type": "string", "enum": ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "DELAYED"], "description": "Filter by activity status"},
            "is_critical": {"type": "boolean", "description": "Filter critical path activities only"},
            "work_scope_category": {"type": "string", "description": "Filter by work scope category (e.g., CRITICAL, MIDWARE, SHORTER)"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_activities(pool, project_id: str, status: str | None = None,
                           is_critical: bool | None = None, work_scope_category: str | None = None,
                           limit: int = 50):
    """Query schedule activities from the database."""
    _validate_input(QueryActivitiesInput, project_id=project_id, status=status,
                    is_critical=is_critical, work_scope_category=work_scope_category,
                    limit=limit)
    query = """SELECT activity_code, activity_name, status, is_critical,
                      physical_percent_complete, remaining_duration, original_duration,
                      total_float, work_scope_category
               FROM activities WHERE project_id = $1"""
    params = [project_id]
    idx = 2

    if status:
        query += f" AND status = ${idx}"; params.append(status); idx += 1
    if is_critical is not None:
        query += f" AND is_critical = ${idx}"; params.append(is_critical); idx += 1
    if work_scope_category:
        query += f" AND work_scope_category = ${idx}"; params.append(work_scope_category); idx += 1

    query += f" ORDER BY total_float ASC NULLS LAST LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 2: Query Drawings ───────────────────────────────────────────────

@tool_registry.register(
    name="query_drawings",
    description="Query engineering drawings by discipline, status (IFA/IFC), type, or revision. Returns drawing numbers, titles, statuses, and issue dates.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "discipline_name": {"type": "string", "description": "Filter by discipline (STRUCTURAL, PIPING, MECHANICAL, ELECTRICAL, HVAC)"},
            "status": {"type": "string", "description": "Filter by drawing status (WIP, IFA, IFC, APPROVED)"},
            "drawing_type": {"type": "string", "description": "Filter by drawing type"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_drawings(pool, project_id: str, discipline_name: str | None = None,
                         status: str | None = None, drawing_type: str | None = None,
                         limit: int = 50):
    """Query engineering drawings from the database."""
    _validate_input(QueryDrawingsInput, project_id=project_id, discipline_name=discipline_name,
                    status=status, drawing_type=drawing_type, limit=limit)
    query = """SELECT d.drawing_number, d.drawing_title, d.status, d.drawing_type,
                      d.planned_issue_date, d.actual_issue_date, d.revision,
                      ed.discipline_name, d.issued_for_info, d.issued_for_construction
               FROM drawings d
               JOIN engineering_disciplines ed ON d.discipline_id = ed.discipline_id
               WHERE d.project_id = $1"""
    params = [project_id]
    idx = 2

    if discipline_name:
        query += f" AND ed.discipline_name = ${idx}"; params.append(discipline_name); idx += 1
    if status:
        query += f" AND d.status = ${idx}"; params.append(status); idx += 1
    if drawing_type:
        query += f" AND d.drawing_type = ${idx}"; params.append(drawing_type); idx += 1

    query += f" ORDER BY ed.discipline_name, d.drawing_number LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 3: Query Procurement ─────────────────────────────────────────────

@tool_registry.register(
    name="query_procurement",
    description="Query purchase orders by vendor, status, or material type. Returns PO numbers, vendor names, delivery dates, item quantities, and receipt status.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "vendor_name": {"type": "string", "description": "Filter by vendor name (partial match)"},
            "status": {"type": "string", "description": "Filter by PO status (ORDERED, SHIPPED, RECEIVED, CANCELLED)"},
            "material_type": {"type": "string", "description": "Filter by material type"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_procurement(pool, project_id: str, vendor_name: str | None = None,
                            status: str | None = None, material_type: str | None = None,
                            limit: int = 50):
    """Query procurement purchase orders from the database."""
    _validate_input(QueryProcurementInput, project_id=project_id, vendor_name=vendor_name,
                    status=status, material_type=material_type, limit=limit)
    query = """SELECT po.po_number, po.vendor_name, po.order_date, po.expected_delivery_date,
                      po.actual_delivery_date, po.status, po.total_amount,
                      pi.material_type, pi.quantity_ordered, pi.quantity_received,
                      pi.unit_price
               FROM procurement_purchase_orders po
               LEFT JOIN purchase_items pi ON po.po_id = pi.po_id
               WHERE po.project_id = $1"""
    params = [project_id]
    idx = 2

    if vendor_name:
        query += f" AND po.vendor_name ILIKE ${idx}"; params.append(f"%{vendor_name}%"); idx += 1
    if status:
        query += f" AND po.status = ${idx}"; params.append(status); idx += 1
    if material_type:
        query += f" AND pi.material_type ILIKE ${idx}"; params.append(f"%{material_type}%"); idx += 1

    query += f" ORDER BY po.expected_delivery_date LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 4: Query Quality NCR ────────────────────────────────────────────

@tool_registry.register(
    name="query_quality_ncr",
    description="Query quality Non-Conformance Reports (NCRs) by severity, status, discipline, or date range. Returns NCR numbers, descriptions, root causes, and closure dates.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "severity": {"type": "string", "enum": ["CRITICAL", "MAJOR", "MINOR"], "description": "Filter by NCR severity"},
            "status": {"type": "string", "enum": ["OPEN", "INVESTIGATING", "CLOSED"], "description": "Filter by NCR status"},
            "discipline_name": {"type": "string", "description": "Filter by discipline"},
            "from_date": {"type": "string", "format": "date", "description": "Filter NCRs raised after this date (YYYY-MM-DD)"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_quality_ncr(pool, project_id: str, severity: str | None = None,
                            status: str | None = None, discipline_name: str | None = None,
                            from_date: str | None = None, limit: int = 50):
    """Query quality NCRs from the database."""
    _validate_input(QueryQualityNCRInput, project_id=project_id, severity=severity,
                    status=status, discipline_name=discipline_name,
                    from_date=from_date, limit=limit)
    # quality_ncr has no `title`, `discipline_name`, `closed_date` or
    # `system_code` columns: the discipline name comes from the join and the
    # closeout date is actual_closeout_date.
    query = """SELECT ncr.ncr_number, ncr.description, ncr.severity, ncr.status,
                      ed.discipline_name, ncr.root_cause, ncr.corrective_action,
                      ncr.raised_date, ncr.actual_closeout_date AS closed_date
               FROM quality_ncr ncr
               LEFT JOIN engineering_disciplines ed ON ncr.discipline_id = ed.discipline_id
               WHERE ncr.project_id = $1"""
    params = [project_id]
    idx = 2

    if severity:
        query += f" AND ncr.severity = ${idx}"; params.append(severity); idx += 1
    if status:
        query += f" AND ncr.status = ${idx}"; params.append(status); idx += 1
    if discipline_name:
        query += f" AND ed.discipline_name = ${idx}"; params.append(discipline_name); idx += 1
    if from_date:
        query += f" AND ncr.raised_date >= ${idx}::date"; params.append(from_date); idx += 1

    query += f" ORDER BY ncr.raised_date DESC LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 5: Query Safety Incidents ───────────────────────────────────────

@tool_registry.register(
    name="query_safety_incidents",
    description="Query HSE safety incidents by type, severity, or date range. Computes TRIR and LTIFR rates. Returns incident details with investigation status.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "incident_type": {"type": "string", "enum": ["LTI", "MTI", "FAI", "NEAR_MISS", "OBSERVATION"], "description": "Filter by incident type"},
            "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"], "description": "Filter by severity"},
            "from_date": {"type": "string", "format": "date", "description": "Filter incidents after this date (YYYY-MM-DD)"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_safety_incidents(pool, project_id: str, incident_type: str | None = None,
                                 severity: str | None = None, from_date: str | None = None,
                                 limit: int = 50):
    """Query safety incidents from the database."""
    _validate_input(QuerySafetyIncidentsInput, project_id=project_id,
                    incident_type=incident_type, severity=severity,
                    from_date=from_date, limit=limit)
    # Actual columns: corrective_action (singular), status/investigated_by,
    # and area_code (there is no `location` column).
    query = """SELECT incident_date, incident_type, severity, description,
                      status AS investigation_status, corrective_action,
                      lost_time_days, area_code AS location, reported_by
               FROM safety_incidents WHERE project_id = $1"""
    params = [project_id]
    idx = 2

    if incident_type:
        query += f" AND incident_type = ${idx}"; params.append(incident_type); idx += 1
    if severity:
        query += f" AND severity = ${idx}"; params.append(severity); idx += 1
    if from_date:
        query += f" AND incident_date >= ${idx}::date"; params.append(from_date); idx += 1

    query += f" ORDER BY incident_date DESC LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 6: Query Training Records ───────────────────────────────────────

@tool_registry.register(
    name="query_training_records",
    description="Query personnel training records and compliance. Check certification expiry status, course completion rates, and role-based training requirements.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "personnel_name": {"type": "string", "description": "Filter by personnel name (partial match)"},
            "course_name": {"type": "string", "description": "Filter by course name (partial match)"},
            "certification_expired": {"type": "boolean", "description": "Filter personnel with expired certifications"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_training_records(pool, project_id: str, personnel_name: str | None = None,
                                 course_name: str | None = None,
                                 certification_expired: bool | None = None,
                                 limit: int = 50):
    """Query training records from the database."""
    _validate_input(QueryTrainingRecordsInput, project_id=project_id,
                    personnel_name=personnel_name, course_name=course_name,
                    certification_expired=certification_expired, limit=limit)
    # personnel has role_id/discipline (not `role`/`trade`), and
    # personnel_training has no `status` column.
    query = """SELECT p.full_name, tr.role_name AS role, p.discipline AS trade,
                      tc.course_name, ptr.completion_date, ptr.expiry_date,
                      CASE WHEN ptr.expiry_date < CURRENT_DATE THEN TRUE ELSE FALSE END AS is_expired
               FROM personnel_training ptr
               JOIN personnel p ON ptr.personnel_id = p.personnel_id
               LEFT JOIN training_roles tr ON p.role_id = tr.role_id
               JOIN training_courses tc ON ptr.course_id = tc.course_id
               WHERE p.project_id = $1"""
    params = [project_id]
    idx = 2

    if personnel_name:
        query += f" AND p.full_name ILIKE ${idx}"; params.append(f"%{personnel_name}%"); idx += 1
    if course_name:
        query += f" AND tc.course_name ILIKE ${idx}"; params.append(f"%{course_name}%"); idx += 1
    if certification_expired:
        # No placeholder is introduced here, so `idx` must not advance.
        query += " AND ptr.expiry_date < CURRENT_DATE"

    query += f" ORDER BY ptr.expiry_date ASC NULLS LAST LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 7: Query Stage Gates ────────────────────────────────────────────

@tool_registry.register(
    name="query_stage_gates",
    description="Query project stage gates with AI readiness scores, checklist completion, and approval status. Used to assess phase transition readiness.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "status": {"type": "string", "enum": ["PENDING", "IN_REVIEW", "APPROVED", "REJECTED"], "description": "Filter by gate status"},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        },
        "required": ["project_id"],
    },
)
async def query_stage_gates(pool, project_id: str, status: str | None = None, limit: int = 20):
    """Query stage gates from the database."""
    _validate_input(QueryStageGatesInput, project_id=project_id, status=status, limit=limit)
    # Actual columns: human_approver / approval_date, and the checklist PK is
    # checklist_item_id (not item_id).
    query = """SELECT sg.gate_name, sg.from_phase, sg.to_phase, sg.status,
                      sg.ai_readiness_score, sg.human_approver,
                      sg.approval_date AS approved_at,
                      COUNT(sgc.checklist_item_id) AS total_checklist,
                      SUM(CASE WHEN sgc.is_complete THEN 1 ELSE 0 END) AS completed_checklist
               FROM stage_gates sg
               LEFT JOIN stage_gate_checklist sgc ON sg.gate_id = sgc.gate_id
               WHERE sg.project_id = $1"""
    params = [project_id]
    idx = 2

    if status:
        query += f" AND sg.status = ${idx}"; params.append(status); idx += 1

    query += f" GROUP BY sg.gate_id ORDER BY sg.gate_sequence LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 8: Query Conflicts ──────────────────────────────────────────────

@tool_registry.register(
    name="query_conflicts",
    description="Query project conflicts detected by AI or manual review. Includes cross-phase clashes, resource conflicts, and schedule mismatches with resolution status.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "conflict_type": {"type": "string", "description": "Filter by conflict type (SCHEDULE, RESOURCE, MATERIAL, DESIGN, OTHER)"},
            "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"], "description": "Filter by severity"},
            "status": {"type": "string", "enum": ["OPEN", "IN_PROGRESS", "RESOLVED", "DISMISSED"], "description": "Filter by resolution status"},
            "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
        },
        "required": ["project_id"],
    },
)
async def query_conflicts(pool, project_id: str, conflict_type: str | None = None,
                          severity: str | None = None, status: str | None = None,
                          limit: int = 50):
    """Query conflicts from the database."""
    _validate_input(QueryConflictsInput, project_id=project_id, conflict_type=conflict_type,
                    severity=severity, status=status, limit=limit)
    query = """SELECT c.title, c.description, c.conflict_type, c.severity, c.status,
                      c.detected_by_agent, c.ai_confidence, c.ai_recommendation,
                      c.created_at, c.resolved_at
               FROM conflicts WHERE project_id = $1"""
    params = [project_id]
    idx = 2

    if conflict_type:
        query += f" AND conflict_type = ${idx}"; params.append(conflict_type); idx += 1
    if severity:
        query += f" AND severity = ${idx}"; params.append(severity); idx += 1
    if status:
        query += f" AND status = ${idx}"; params.append(status); idx += 1

    query += f" ORDER BY CASE severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, created_at DESC LIMIT ${idx}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


# ── Tool 9: Query Traceability ───────────────────────────────────────────

@tool_registry.register(
    name="query_traceability",
    description="Full lifecycle trace: forward from a drawing to all downstream items, or backward from a sub-system to all upstream items. Shows the complete chain from engineering to commissioning.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "entity_type": {"type": "string", "enum": ["drawing", "activity", "purchase_order", "equipment", "system"], "description": "Starting entity type"},
            "entity_id": {"type": "string", "description": "Entity UUID or identifier"},
        },
        "required": ["project_id", "entity_type", "entity_id"],
    },
)
async def query_traceability(pool, project_id: str, entity_type: str, entity_id: str):
    """Query traceability chain from the database via the traceability service."""
    _validate_input(QueryTraceabilityInput, project_id=project_id,
                    entity_type=entity_type, entity_id=entity_id)
    from services.traceability_service import TraceabilityService

    if entity_type == "drawing":
        return await TraceabilityService.forward_trace(entity_id, project_id, pool)
    elif entity_type == "system":
        return await TraceabilityService.backward_trace(entity_id, project_id, pool)
    elif entity_type in ("activity", "purchase_order", "equipment"):
        return await TraceabilityService.impact_analysis(entity_type, entity_id, project_id, pool)
    else:
        return await TraceabilityService.full_traceability_matrix(project_id, pool)


# ── Tool 10: Calculate KPI ───────────────────────────────────────────────

@tool_registry.register(
    name="calculate_kpi",
    description="Compute real-time project KPIs: overall progress %, critical path health, open NCR count, punch list status, material receipt %, safety incident rate (TRIR), and alert count.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
        },
        "required": ["project_id"],
    },
)
async def calculate_kpi(pool, project_id: str):
    """Calculate comprehensive project KPIs."""
    _validate_input(CalculateKPIInput, project_id=project_id)
    async with pool.acquire() as conn:
        # Project overview
        project = await conn.fetchrow("SELECT * FROM projects WHERE project_id = $1", project_id)
        if not project:
            return {"error": "Project not found"}

        # Activity stats
        activities = await conn.fetchrow(
            """SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_critical) AS critical,
                      AVG(physical_percent_complete) AS avg_pct,
                      COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed
               FROM activities WHERE project_id = $1""", project_id)

        # Open alerts
        alerts = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM schedule_alerts WHERE project_id = $1 AND is_resolved = FALSE", project_id)

        # Open NCRs
        ncrs = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM quality_ncr WHERE project_id = $1 AND status != 'CLOSED'", project_id)

        # Open punch items
        punches = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM punch_items WHERE project_id = $1 AND status NOT IN ('CLOSED', 'CANCELLED')", project_id)

        # Material receipt rate
        materials = await conn.fetchrow(
            """SELECT COALESCE(SUM(pi.quantity_received), 0) AS received,
                      COALESCE(SUM(pi.quantity_ordered), 0) AS ordered
               FROM purchase_items pi
               JOIN procurement_purchase_orders po ON pi.po_id = po.po_id
               WHERE po.project_id = $1""", project_id)

        # Safety incidents (last 90 days)
        incidents = await conn.fetchrow(
            """SELECT COUNT(*) AS cnt, SUM(lost_time_days) AS total_lost_days
               FROM safety_incidents WHERE project_id = $1 AND incident_date >= CURRENT_DATE - 90""", project_id)

        # Commissioning progress
        commissioning = await conn.fetchrow(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE status = 'PASSED') AS passed
               FROM commissioning_procedures cp
               JOIN sub_systems ss ON cp.sub_system_id = ss.sub_system_id
               WHERE ss.project_id = $1""", project_id)

        material_rate = round((materials["received"] / materials["ordered"] * 100) if materials and materials["ordered"] else 0, 1)

        return {
            "project_name": project["project_name"],
            "project_code": project["project_code"],
            "status": project["current_status"],
            "planned_finish": str(project["planned_finish_date"]) if project.get("planned_finish_date") else None,
            "activities": {
                "total": activities["total"] if activities else 0,
                "critical": activities["critical"] if activities else 0,
                "avg_progress_pct": round(float(activities["avg_pct"] or 0), 1) if activities else 0.0,
                "completed": activities["completed"] if activities else 0,
            },
            "alerts": {"open": alerts["cnt"] if alerts else 0},
            "quality": {"open_ncrs": ncrs["cnt"] if ncrs else 0},
            "completion": {"open_punch_items": punches["cnt"] if punches else 0},
            "procurement": {"material_receipt_pct": material_rate},
            "safety": {
                "incidents_90d": incidents["cnt"] if incidents else 0,
                "total_lost_days": incidents["total_lost_days"] or 0 if incidents else 0,
            },
            "commissioning": {
                "total_procedures": commissioning["total"] if commissioning else 0,
                "passed": commissioning["passed"] if commissioning else 0,
                "pass_rate_pct": round(float(commissioning["passed"] or 0) / (commissioning["total"] or 1) * 100, 1) if commissioning else 0.0,
            },
        }


# ── Tool 11: Generate Report ─────────────────────────────────────────────

@tool_registry.register(
    name="generate_report",
    description="Generate a data-driven narrative report section (weekly, monthly, or executive summary). Returns structured text with key metrics, achievements, risks, and recommendations.",
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project UUID"},
            "report_type": {"type": "string", "enum": ["weekly", "monthly", "executive"], "description": "Report type"},
            "week_end": {"type": "string", "format": "date", "description": "Week ending date for weekly reports (YYYY-MM-DD)"},
        },
        "required": ["project_id"],
    },
)
async def generate_report(pool, project_id: str, report_type: str = "weekly", week_end: str | None = None):
    """Generate a structured report section from KPI data."""
    _validate_input(GenerateReportInput, project_id=project_id,
                    report_type=report_type, week_end=week_end)
    # First get KPIs — use keyword args since tools are wrapped with **kwargs
    kpis_result = await calculate_kpi(pool=pool, project_id=project_id)
    kpis = kpis_result.data if hasattr(kpis_result, 'data') else kpis_result

    async with pool.acquire() as conn:
        # Get recent alerts
        top_alerts = await conn.fetch(
            """SELECT alert_title, severity, recommended_action
               FROM schedule_alerts WHERE project_id = $1 AND is_resolved = FALSE
               ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END LIMIT 5""",
            project_id)

        # Get recent conflicts
        top_conflicts = await conn.fetch(
            "SELECT title, severity, conflict_type FROM conflicts WHERE project_id = $1 AND status != 'RESOLVED' ORDER BY created_at DESC LIMIT 5",
            project_id)

    report_lines = [
        f"## {report_type.title()} Report — {kpis.get('project_name', 'Unknown Project')}",
        f"**Project Code**: {kpis.get('project_code', 'N/A')} | **Status**: {kpis.get('status', 'N/A')}",
        "",
        "### Key Metrics",
        f"- Overall Progress: {kpis['activities']['avg_progress_pct']}% ({kpis['activities']['completed']}/{kpis['activities']['total']} activities complete)",
        f"- Critical Path: {kpis['activities']['critical']} activities | Material Receipt: {kpis['procurement']['material_receipt_pct']}%",
        f"- Open Alerts: {kpis['alerts']['open']} | Open NCRs: {kpis['quality']['open_ncrs']} | Open Punch Items: {kpis['completion']['open_punch_items']}",
        f"- Safety: {kpis['safety']['incidents_90d']} incidents (90d) | Commissioning Pass Rate: {kpis['commissioning']['pass_rate_pct']}%",
        "",
    ]

    if top_alerts:
        report_lines.append("### Top Alerts")
        for a in top_alerts:
            a_dict = dict(a)
            report_lines.append(f"- [{a_dict['severity']}] {a_dict['alert_title']}: {a_dict.get('recommended_action', 'No action specified')}")

    if top_conflicts:
        report_lines.append("\n### Active Conflicts")
        for c in top_conflicts:
            c_dict = dict(c)
            report_lines.append(f"- [{c_dict['severity']}] {c_dict['title']} ({c_dict['conflict_type']})")

    report_lines.append(f"\n---\n*Generated {date.today().isoformat()} — data-driven report section*")

    return {"report_text": "\n".join(report_lines), "kpis": kpis}


# ── Registration helper ──────────────────────────────────────────────────

def register_tools():
    """Import-trigger for tool registration. Tools auto-register via decorators on import."""
    logger.info(f"Registered {len(tool_registry._tools)} tools: {tool_registry.list_tools()}")
