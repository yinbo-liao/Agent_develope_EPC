"""
Project Data Summarizer — generates cached text summaries of project state.

These summaries are indexed alongside schema metadata for RAG retrieval,
enabling the LLM to answer questions like "What's the current project health?"
without executing every tool on every query.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProjectSummarizer:
    """Generates and caches text summaries of project data for RAG retrieval."""

    def __init__(self):
        self._cache: dict[str, dict] = {}  # project_id → {summary, generated_at}

    async def summarize(self, project_id: str, pool) -> str:
        """Generate a concise text summary of a project's current state."""
        import json

        async with pool.acquire() as conn:
            # Project info
            proj = await conn.fetchrow(
                "SELECT project_name, project_code, current_status, planned_finish_date FROM projects WHERE project_id = $1",
                project_id,
            )
            if not proj:
                return f"Project {project_id} not found."

            # Activity summary
            acts = await conn.fetchrow(
                "SELECT COUNT(*) AS total, AVG(physical_percent_complete) AS avg_pct, "
                "COUNT(*) FILTER (WHERE is_critical) AS critical, "
                "COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed "
                "FROM activities WHERE project_id = $1", project_id)

            # Alert summary
            alerts = await conn.fetchrow(
                "SELECT COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE severity = 'CRITICAL') AS critical, "
                "COUNT(*) FILTER (WHERE severity = 'HIGH') AS high "
                "FROM schedule_alerts WHERE project_id = $1 AND is_resolved = FALSE", project_id)

            # NCR summary
            ncrs = await conn.fetchrow(
                "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status != 'CLOSED') AS open, "
                "COUNT(*) FILTER (WHERE severity = 'CRITICAL') AS critical "
                "FROM quality_ncr WHERE project_id = $1", project_id)

            # Material receipt rate
            mats = await conn.fetchrow(
                "SELECT COALESCE(SUM(pi.quantity_received),0) AS recv, COALESCE(SUM(pi.quantity_ordered),0) AS ord "
                "FROM purchase_items pi JOIN procurement_purchase_orders po ON pi.po_id = po.po_id "
                "WHERE po.project_id = $1", project_id)

            # Safety (last 90 days)
            safety = await conn.fetchrow(
                "SELECT COUNT(*) AS total, SUM(lost_time_days) AS ltd "
                "FROM safety_incidents WHERE project_id = $1 AND incident_date >= CURRENT_DATE - 90", project_id)

        mat_pct = round((mats["recv"] / mats["ord"] * 100) if mats and mats["ord"] else 0, 1)
        avg_pct = round(float(acts["avg_pct"] or 0), 1) if acts else 0.0

        summary = (
            f"Project: {proj['project_name']} ({proj['project_code']}) — Status: {proj['current_status']}\n"
            f"Planned Finish: {proj.get('planned_finish_date', 'N/A')}\n"
            f"Progress: {avg_pct}% ({acts['completed'] if acts else 0}/{acts['total'] if acts else 0} activities complete), "
            f"{acts['critical'] if acts else 0} critical path activities\n"
            f"Open Alerts: {alerts['total'] if alerts else 0} ({alerts['critical'] if alerts else 0} critical, {alerts['high'] if alerts else 0} high)\n"
            f"Quality: {ncrs['open'] if ncrs else 0} open NCRs ({ncrs['critical'] if ncrs else 0} critical) out of {ncrs['total'] if ncrs else 0} total\n"
            f"Materials: {mat_pct}% received ({mats['recv'] or 0}/{mats['ord'] or 0})\n"
            f"Safety (90d): {safety['total'] if safety else 0} incidents, {safety['ltd'] or 0 if safety else 0} lost days\n"
        )

        self._cache[project_id] = {
            "summary": summary,
            "generated_at": datetime.now().isoformat(),
        }
        return summary

    def get_cached(self, project_id: str) -> str | None:
        """Get a cached summary if available."""
        entry = self._cache.get(project_id)
        if entry:
            return entry["summary"]
        return None


# Singleton
project_summarizer = ProjectSummarizer()
