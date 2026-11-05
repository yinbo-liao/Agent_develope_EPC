"""
AI Engine Service — Claude Agent integration for EPC project intelligence.

Architecture:
- Stateless analysis agents (powered by Claude API)
- LangGraph state machines for multi-step workflows (stage gates, conflict resolution)
- Human-in-the-loop (HITL) — all recommendations require explicit approval
- WebSocket broadcasting for real-time AI insights

Agent Types:
1. schedule_optimizer  — Critical path analysis, resource leveling suggestions
2. conflict_detector   — Cross-phase clash detection (dates, resources, designs)
3. procurement_advisor — Material delivery risk vs. construction schedule
4. quality_analyst     — NCR pattern recognition, systemic issue detection
5. safety_monitor      — Incident trend analysis, risk zone prediction
6. commissioning_planner — Commissioning sequence optimization
7. report_composer     — Auto-generate narrative weekly/monthly reports
8. stage_gate_assessor — Calculate AI readiness scores for phase transitions
"""
import json
import logging
from datetime import date, datetime
from typing import Any, Optional
from config import settings
from websocket import manager

logger = logging.getLogger(__name__)

# Lazy import to avoid hard dependency at import time
anthropic = None
langgraph = None


def _ensure_anthropic():
    global anthropic
    if anthropic is None:
        try:
            import anthropic as _anthropic
            anthropic = _anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required for AI engine. "
                "Install with: pip install anthropic"
            )
    return anthropic


class AIEngine:
    """Central AI engine coordinating Claude agents for EPC intelligence."""

    def __init__(self):
        self.enabled = settings.ai_enabled and bool(settings.anthropic_api_key)
        self._client = None

    @property
    def client(self):
        if self._client is None and self.enabled:
            ac = _ensure_anthropic()
            self._client = ac.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    # ── Agent: Schedule Optimizer ────────────────────────────────────────

    async def analyze_schedule_risk(self, project_id: str, pool) -> dict:
        """Analyze critical path and identify schedule risks."""
        async with pool.acquire() as conn:
            critical_activities = await conn.fetch(
                """SELECT activity_code, activity_name, total_float,
                          physical_percent_complete, remaining_duration,
                          original_duration, status
                   FROM activities WHERE project_id = $1 AND is_critical = TRUE
                   ORDER BY total_float""",
                project_id,
            )
            resource_shortages = await conn.fetch(
                "SELECT * FROM resource_shortages WHERE project_id = $1 AND status = 'OPEN' ORDER BY shortfall DESC",
                project_id,
            )

        activities_list = [dict(a) for a in critical_activities]
        shortages_list = [dict(s) for s in resource_shortages]

        if not self.enabled:
            return self._basic_schedule_analysis(activities_list, shortages_list)

        prompt = self._build_schedule_prompt(activities_list, shortages_list)
        result = await self._call_claude(prompt, "schedule_optimizer")
        return self._parse_or_fallback(result, "schedule_analysis",
                                        self._basic_schedule_analysis(activities_list, shortages_list))

    def _basic_schedule_analysis(self, activities, shortages) -> dict:
        """Fallback rule-based schedule analysis when AI is disabled."""
        critical_with_neg_float = [a for a in activities if (a.get("total_float") or 0) <= 0]
        delayed = [a for a in activities if a.get("status") != "COMPLETED" and (a.get("remaining_duration") or 0) > (a.get("original_duration") or 1)]

        risks = []
        if critical_with_neg_float:
            risks.append(f"{len(critical_with_neg_float)} critical activities with zero/negative float")
        if delayed:
            risks.append(f"{len(delayed)} activities exceeding original duration")
        if shortages:
            risks.append(f"{len(shortages)} open resource shortages")

        return {
            "risk_level": "HIGH" if len(risks) >= 2 else "MEDIUM" if risks else "LOW",
            "risks": risks,
            "critical_path_health": f"{len(activities)} critical activities, "
                                     f"{len(critical_with_neg_float)} at risk",
            "recommendations": [
                "Expedite critical path activities with negative float",
                "Address open resource shortages prioritized by shortfall",
            ] if risks else ["Schedule on track. Continue monitoring."],
            "generated_by": "rule_based",
        }

    # ── Agent: Conflict Detector ─────────────────────────────────────────

    async def detect_conflicts(self, project_id: str, pool) -> list[dict]:
        """Scan for cross-phase conflicts: schedule, resource, material, design."""
        if not self.enabled:
            return []

        async with pool.acquire() as conn:
            # Gather cross-phase data for conflict analysis
            schedule_data = await conn.fetch(
                """SELECT a.activity_code, a.activity_name, a.total_float, a.is_critical,
                          a.status, a.work_scope_category, a.physical_percent_complete
                   FROM activities a WHERE a.project_id = $1 ORDER BY a.activity_code""",
                project_id,
            )
            procurement_data = await conn.fetch(
                """SELECT po.po_number, po.expected_delivery_date, po.status,
                          pi.material_type, pi.quantity_ordered, pi.quantity_received
                   FROM procurement_purchase_orders po
                   LEFT JOIN purchase_items pi ON po.po_id = pi.po_id
                   WHERE po.project_id = $1""",
                project_id,
            )
            shortage_data = await conn.fetch(
                "SELECT * FROM resource_shortages WHERE project_id = $1 AND status = 'OPEN'",
                project_id,
            )
            drawing_data = await conn.fetch(
                """SELECT d.drawing_number, d.status, d.planned_issue_date, d.actual_issue_date,
                          ed.discipline_name
                   FROM drawings d JOIN engineering_disciplines ed ON d.discipline_id = ed.discipline_id
                   WHERE d.project_id = $1""",
                project_id,
            )

        prompt = self._build_conflict_prompt(
            [dict(r) for r in schedule_data],
            [dict(r) for r in procurement_data],
            [dict(r) for r in shortage_data],
            [dict(r) for r in drawing_data],
        )
        result = await self._call_claude(prompt, "conflict_detector")
        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            return parsed.get("conflicts", [])
        except (json.JSONDecodeError, TypeError):
            return []

    # ── Agent: Stage Gate Assessor ───────────────────────────────────────

    async def assess_stage_gate(self, project_id: str, gate_id: str, pool) -> dict:
        """Comprehensive AI assessment for a stage gate transition."""
        async with pool.acquire() as conn:
            gate = await conn.fetchrow(
                "SELECT * FROM stage_gates WHERE gate_id = $1 AND project_id = $2",
                gate_id, project_id,
            )
            if not gate:
                return {"error": "Gate not found"}

            checklist = await conn.fetch(
                "SELECT * FROM stage_gate_checklist WHERE gate_id = $1 ORDER BY item_number",
                gate_id,
            )
            open_ncrs = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM quality_ncr WHERE project_id = $1 AND status != 'CLOSED'",
                project_id,
            )
            open_punches = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM punch_items WHERE project_id = $1 AND status NOT IN ('CLOSED', 'CANCELLED')",
                project_id,
            )
            material_status = await conn.fetchrow(
                """SELECT SUM(pi.quantity_ordered) AS ordered, SUM(pi.quantity_received) AS received
                   FROM purchase_items pi
                   JOIN procurement_purchase_orders po ON pi.po_id = po.po_id
                   WHERE po.project_id = $1""",
                project_id,
            )
            recent_incidents = await conn.fetchrow(
                "SELECT COUNT(*) AS cnt FROM safety_incidents WHERE project_id = $1 AND incident_date >= CURRENT_DATE - 30 AND incident_type IN ('LTI','MTI')",
                project_id,
            )

        if not self.enabled:
            return self._basic_gate_assessment(
                dict(gate), [dict(c) for c in checklist],
                open_ncrs["cnt"], open_punches["cnt"],
                material_status, recent_incidents["cnt"]
            )

        prompt = self._build_gate_assessment_prompt(
            dict(gate), [dict(c) for c in checklist],
            open_ncrs["cnt"], open_punches["cnt"],
            dict(material_status) if material_status else {}, recent_incidents["cnt"],
        )
        result = await self._call_claude(prompt, "stage_gate_assessor")
        return self._parse_or_fallback(result, "gate_assessment",
                                        self._basic_gate_assessment(
                                            dict(gate), [dict(c) for c in checklist],
                                            open_ncrs["cnt"], open_punches["cnt"],
                                            material_status, recent_incidents["cnt"]))

    def _basic_gate_assessment(self, gate, checklist, open_ncrs, open_punches, material, incidents) -> dict:
        """Rule-based fallback gate assessment."""
        total_items = len(checklist)
        completed = sum(1 for c in checklist if c.get("is_complete"))
        checklist_pct = round(completed / total_items * 100, 1) if total_items else 0

        score = (
            (checklist_pct * 0.40 / 10) +
            (max(0, 10 - open_ncrs * 0.5) * 0.25) +
            (max(0, 10 - open_punches * 0.3) * 0.15) +
            (5 * 0.10) +
            (max(0, 10 - incidents * 3) * 0.10)
        )

        if score >= 8:
            recommendation = "APPROVE — High readiness"
        elif score >= 6:
            recommendation = "CONDITIONAL — Address open items"
        elif score >= 4:
            recommendation = "DEFER — Multiple blockers"
        else:
            recommendation = "REJECT — Insufficient readiness"

        return {
            "ai_readiness_score": round(score, 1),
            "recommendation": recommendation,
            "checklist_pct": checklist_pct,
            "open_ncrs": open_ncrs,
            "open_punches": open_punches,
            "blockers": [f"{open_ncrs} open NCRs"] if open_ncrs > 5 else [],
            "generated_by": "rule_based",
        }

    # ── Agent: Report Composer ───────────────────────────────────────────

    async def compose_weekly_report(self, project_id: str, week_end: date, pool) -> str:
        """Generate a narrative weekly accountability report."""
        async with pool.acquire() as conn:
            # Gather all week data
            from datetime import timedelta
            week_start = week_end - timedelta(days=6)
            tasks = await conn.fetch(
                """SELECT COUNT(*) AS total, SUM(CASE WHEN is_completed THEN 1 ELSE 0 END) AS completed,
                          AVG(actual_completion_percent) AS avg_actual
                   FROM weekly_planning_tasks WHERE project_id = $1 AND week_start = $2""",
                project_id, week_start,
            )
            ndt = await conn.fetch(
                """SELECT ndt_method, COUNT(*) AS total, AVG(percent_complete) AS avg_pct
                   FROM ndt_requests WHERE project_id = $1 AND requested_date BETWEEN $2 AND $3
                   GROUP BY ndt_method""",
                project_id, week_start, week_end,
            )
            manpower = await conn.fetch(
                """SELECT report_date, discipline, actual_headcount, planned_headcount
                   FROM daily_manpower WHERE project_id = $1 AND report_date BETWEEN $2 AND $3""",
                project_id, week_start, week_end,
            )
            shortages = await conn.fetch(
                "SELECT * FROM resource_shortages WHERE project_id = $1 AND status = 'OPEN' ORDER BY shortfall DESC LIMIT 5",
                project_id,
            )
            incidents = await conn.fetch(
                "SELECT incident_type, COUNT(*) AS cnt FROM safety_incidents WHERE project_id = $1 AND incident_date BETWEEN $2 AND $3 GROUP BY incident_type",
                project_id, week_start, week_end,
            )
            project_info = await conn.fetchrow(
                "SELECT * FROM projects WHERE project_id = $1", project_id,
            )

        if not self.enabled:
            return self._basic_report(
                project_id, week_end, dict(project_info) if project_info else {},
                dict(tasks[0]) if tasks else {}, [dict(n) for n in ndt],
                [dict(m) for m in manpower], [dict(s) for s in shortages],
                [dict(i) for i in incidents],
            )

        prompt = self._build_report_prompt(
            dict(project_info) if project_info else {}, week_end,
            dict(tasks[0]) if tasks else {}, [dict(n) for n in ndt],
            [dict(s) for s in shortages], [dict(i) for i in incidents],
        )
        result = await self._call_claude(prompt, "report_composer")
        return result if isinstance(result, str) else str(result)

    def _basic_report(self, project_id, week_end, project, tasks, ndt, manpower, shortages, incidents) -> str:
        """Fallback templated report."""
        lines = [
            f"# Weekly Accountability Report",
            f"**Project**: {project.get('project_name', project_id)}",
            f"**Week Ending**: {week_end.isoformat()}",
            f"**Status**: {project.get('current_status', 'N/A')}",
            "",
            "## Task Summary",
            f"- Total tasks: {tasks.get('total', 0)}, Completed: {tasks.get('completed', 0)}",
            f"- Average actual completion: {tasks.get('avg_actual', 0):.1f}%",
            "",
            "## NDT Progress",
        ]
        for n in ndt:
            lines.append(f"- {n['ndt_method']}: {n['total']} requests, {n['avg_pct']:.0f}% complete")
        if shortages:
            lines.append("\n## Top Resource Shortages")
            for s in shortages:
                lines.append(f"- {s['resource_name']}: shortfall {s['shortfall']} ({s['status']})")
        if incidents:
            lines.append("\n## Safety Incidents This Week")
            for i in incidents:
                lines.append(f"- {i['incident_type']}: {i['cnt']} occurrence(s)")
        lines.append(f"\n---\n*Report generated {datetime.now().isoformat()} (rule-based)*")
        return "\n".join(lines)

    # ── Claude API Call ──────────────────────────────────────────────────

    async def _call_claude(self, prompt: str, agent_type: str) -> str:
        """Call Claude API with structured prompting for a specific agent role."""
        system_prompts = {
            "schedule_optimizer": (
                "You are an EPC project schedule optimization expert. Analyze schedule data "
                "and identify risks, bottlenecks, and optimization opportunities. "
                "Respond with a JSON object containing: risk_level (HIGH/MEDIUM/LOW), "
                "risks (array of strings), critical_path_health (string), "
                "recommendations (array of strings), and delay_predictions (array of "
                "{activity, predicted_delay_days, confidence})."
            ),
            "conflict_detector": (
                "You are an EPC project conflict detection specialist. Scan cross-phase data "
                "for schedule clashes, resource conflicts, material delivery mismatches, "
                "and design inconsistencies. Output JSON with a 'conflicts' array containing "
                "objects: {conflict_type, title, description, severity, source_entity, "
                "target_entity, recommended_action, confidence (0-1)}."
            ),
            "stage_gate_assessor": (
                "You are an EPC stage gate assessment expert. Evaluate readiness for phase "
                "transition based on checklist completion, open NCRs, punch list status, "
                "material readiness, and safety performance. Output JSON with: "
                "ai_readiness_score (0-10), recommendation (APPROVE/CONDITIONAL/DEFER/REJECT), "
                "blockers (array), risks (array), and detailed_findings (string)."
            ),
            "report_composer": (
                "You are an EPC project report writer. Generate a concise, professional "
                "weekly accountability report in markdown format. Include: executive summary, "
                "task achievements, NDT progress, resource status, safety summary, "
                "and recommendations for next week. Be factual and specific."
            ),
        }

        system_msg = system_prompts.get(agent_type, "You are an EPC project management AI assistant.")
        try:
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.ai_max_tokens,
                temperature=settings.ai_temperature,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude API error ({agent_type}): {e}")
            raise

    # ── Prompt Builders ──────────────────────────────────────────────────

    def _build_schedule_prompt(self, activities, shortages) -> str:
        return f"""Analyze the following EPC project schedule data for risks and optimization:

CRITICAL PATH ACTIVITIES:
{json.dumps(activities[:50], indent=2, default=str)}

RESOURCE SHORTAGES:
{json.dumps(shortages[:20], indent=2, default=str)}

Identify:
1. Top 3 schedule risks with mitigation recommendations
2. Activities likely to be delayed in the next 4 weeks
3. Resource reallocation suggestions to optimize critical path"""

    def _build_conflict_prompt(self, schedule, procurement, shortages, drawings) -> str:
        return f"""Scan for cross-phase conflicts in this EPC project:

SCHEDULE DATA ({len(schedule)} activities):
{json.dumps(schedule[:30], indent=2, default=str)}

PROCUREMENT DATA ({len(procurement)} PO items):
{json.dumps(procurement[:30], indent=2, default=str)}

RESOURCE SHORTAGES:
{json.dumps(shortages, indent=2, default=str)}

DRAWING STATUS:
{json.dumps(drawings[:20], indent=2, default=str)}

Detect conflicts involving:
1. Material delivery dates vs. construction start dates
2. Drawing issue delays vs. procurement order dates
3. Resource availability vs. planned activity workload
4. Any other cross-phase inconsistencies"""

    def _build_gate_assessment_prompt(self, gate, checklist, open_ncrs, open_punches, material, incidents) -> str:
        return f"""Assess readiness for this EPC stage gate transition:

GATE: {gate.get('gate_name')} (From: {gate.get('from_phase')} → To: {gate.get('to_phase')})

CHECKLIST ({len(checklist)} items):
{json.dumps(checklist, indent=2, default=str)}

METRICS:
- Open NCRs: {open_ncrs}
- Open Punch Items: {open_punches}
- Material Receipt Status: {json.dumps(material, default=str)}
- Recordable Incidents (30 days): {incidents}

Provide a readiness assessment with score (0-10) and specific recommendations."""

    def _build_report_prompt(self, project, week_end, tasks, ndt, shortages, incidents) -> str:
        return f"""Generate a professional weekly accountability report for:

Project: {project.get('project_name', 'Unknown')} ({project.get('project_code', '')})
Week Ending: {week_end.isoformat()}

TASK SUMMARY: {json.dumps(tasks, default=str)}
NDT PROGRESS: {json.dumps(ndt, default=str)}
RESOURCE SHORTAGES: {json.dumps(shortages, default=str)}
SAFETY INCIDENTS: {json.dumps(incidents, default=str)}

Include: executive summary, achievements this week, concerns/risks, and next week priorities."""

    def _parse_or_fallback(self, raw_result: str, result_type: str, fallback: dict | str) -> dict | str:
        """Try to parse AI JSON result, fallback to rule-based on failure."""
        try:
            if result_type == "report_composer":
                return raw_result
            return json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        except (json.JSONDecodeError, TypeError, AttributeError):
            logger.warning(f"Failed to parse AI {result_type} result, using fallback")
            return fallback


# Singleton
ai_engine = AIEngine()


# ── Convenience Functions ────────────────────────────────────────────────

async def broadcast_ai_insight(project_id: str, insight_type: str, payload: dict):
    """Push an AI-generated insight to all WebSocket clients for a project."""
    await manager.broadcast_to_project(project_id, {
        "type": "AI_INSIGHT",
        "payload": {
            "insight_type": insight_type,
            "timestamp": datetime.now().isoformat(),
            **payload,
        },
    })
