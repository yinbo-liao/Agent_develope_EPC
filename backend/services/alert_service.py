"""
Alert Service — scheduled alert generation with deduplication and transaction safety.

Generates three types of alerts:
1. CRITICAL_FLOAT — critical path activities with near-zero/negative float
2. MATERIAL_SHORTAGE — open resource shortages
3. NDT_OVERDUE — NDT requests past due date

Deduplication relies on the partial unique index created in migration
`005_reliability_constraints.sql`:

    UNIQUE (project_id, alert_type, entity_id) WHERE is_resolved = FALSE

`entity_id` identifies the source row (activity / shortage / NDT request), so
re-running generation never creates a second unresolved alert for the same
entity. The previous `ON CONFLICT DO NOTHING` without any unique constraint
was a no-op and duplicated every alert on each cycle.
"""

import logging
from websocket import manager

logger = logging.getLogger(__name__)

# The conflict target must repeat the index predicate for PostgreSQL to infer
# the partial unique index.
_ALERT_CONFLICT = (
    "ON CONFLICT (project_id, alert_type, entity_id) "
    "WHERE is_resolved = FALSE DO NOTHING"
)


class AlertService:
    _pool = None

    @classmethod
    def set_pool(cls, pool):
        cls._pool = pool

    @classmethod
    async def generate_alerts(cls, project_id: str, pool=None):
        """Generate alerts atomically with deduplication and broadcast results."""
        p = pool or cls._pool
        if p is None:
            raise RuntimeError("AlertService has no database pool configured")
        async with p.acquire() as conn:
            async with conn.transaction():
                # Critical path float alerts — entity_id = activity_id
                await conn.execute(
                    f"""INSERT INTO schedule_alerts
                          (alert_id, project_id, alert_type, entity_id, activity_id,
                           alert_title, severity, recommended_action)
                       SELECT gen_random_uuid(), project_id, 'CRITICAL_FLOAT', activity_id, activity_id,
                              'Critical path activity ' || activity_code || ' has float = ' || COALESCE(total_float::TEXT, 'N/A'),
                              CASE WHEN total_float <= 0 THEN 'CRITICAL' WHEN total_float <= 3 THEN 'HIGH' ELSE 'MEDIUM' END,
                              'Expedite predecessor or add resources'
                       FROM activities
                       WHERE project_id = $1 AND is_critical AND COALESCE(total_float, 0) < 5 AND status != 'COMPLETED'
                       {_ALERT_CONFLICT}""",
                    project_id)

                # Material shortage alerts — entity_id = shortage_id
                await conn.execute(
                    f"""INSERT INTO schedule_alerts
                          (alert_id, project_id, alert_type, entity_id, activity_id,
                           alert_title, severity, recommended_action)
                       SELECT gen_random_uuid(), project_id, 'MATERIAL_SHORTAGE', shortage_id, NULL,
                              'Material shortage: ' || resource_name || ' shortfall = ' || shortfall::TEXT,
                              CASE WHEN shortfall > 100 THEN 'HIGH' ELSE 'MEDIUM' END,
                              'Expedite procurement or find alternative supplier'
                       FROM resource_shortages WHERE project_id = $1 AND status = 'OPEN'
                       {_ALERT_CONFLICT}""",
                    project_id)

                # NDT overdue alerts — entity_id = ndt_id
                await conn.execute(
                    f"""INSERT INTO schedule_alerts
                          (alert_id, project_id, alert_type, entity_id, activity_id,
                           alert_title, severity, recommended_action)
                       SELECT gen_random_uuid(), project_id, 'NDT_OVERDUE', ndt_id, activity_id,
                              'NDT request overdue: method=' || ndt_method || ' weld=' || COALESCE(weld_joint_id, 'N/A'),
                              'HIGH',
                              'Schedule inspection immediately'
                       FROM ndt_requests WHERE project_id = $1 AND status NOT IN ('COMPLETED', 'CANCELLED')
                       AND requested_date < CURRENT_DATE - INTERVAL '7 days'
                       {_ALERT_CONFLICT}""",
                    project_id)

                # Fetch alerts for broadcasting (within transaction to ensure consistency)
                alerts = await conn.fetch(
                    "SELECT * FROM schedule_alerts WHERE project_id = $1 AND is_resolved = FALSE "
                    "ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 "
                    "WHEN 'MEDIUM' THEN 2 ELSE 3 END",
                    project_id)

        alerts_list = [dict(a) for a in alerts]
        await manager.broadcast_to_project(project_id, {
            "type": "ALERTS_UPDATED",
            "payload": {"alerts": alerts_list, "count": len(alerts_list)},
        })
        return alerts_list


async def run_alert_cycle(pool, project_ids: list[str] | None = None) -> dict:
    """Run one alert-generation cycle for all (or the given) projects.

    Intended to be called by an external scheduler every
    `settings.alert_check_interval_minutes` minutes. Errors are isolated per
    project so one bad project does not abort the cycle. Returns a summary
    instead of raising.
    """
    if project_ids is None:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT project_id FROM projects")
        project_ids = [str(r["project_id"]) for r in rows]

    generated, failed = 0, 0
    for project_id in project_ids:
        try:
            alerts = await AlertService.generate_alerts(project_id, pool)
            generated += len(alerts)
        except Exception as exc:
            failed += 1
            logger.error("Alert cycle failed for project %s: %s", project_id, exc)

    return {
        "projects_processed": len(project_ids),
        "projects_failed": failed,
        "open_alerts": generated,
    }
