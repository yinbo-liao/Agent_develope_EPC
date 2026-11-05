"""
Alert Service — scheduled alert generation with deduplication and transaction safety.

Generates three types of alerts:
1. CRITICAL_FLOAT — critical path activities with near-zero/negative float
2. MATERIAL_SHORTAGE — open resource shortages
3. NDT_OVERDUE — NDT requests past due date
"""

from websocket import manager


class AlertService:
    _pool = None

    @classmethod
    def set_pool(cls, pool):
        cls._pool = pool

    @classmethod
    async def generate_alerts(cls, project_id: str, pool=None):
        """Generate alerts atomically with deduplication and broadcast results."""
        p = pool or cls._pool
        async with p.acquire() as conn:
            async with conn.transaction():
                # Critical path float alerts — skip if identical alert already exists
                await conn.execute(
                    """INSERT INTO schedule_alerts (alert_id, project_id, alert_type, activity_id, alert_title, severity, recommended_action)
                       SELECT gen_random_uuid(), project_id, 'CRITICAL_FLOAT', activity_id,
                              'Critical path activity ' || activity_code || ' has float = ' || COALESCE(total_float::TEXT, 'N/A'),
                              CASE WHEN total_float <= 0 THEN 'CRITICAL' WHEN total_float <= 3 THEN 'HIGH' ELSE 'MEDIUM' END,
                              'Expedite predecessor or add resources'
                       FROM activities
                       WHERE project_id = $1 AND is_critical AND COALESCE(total_float, 0) < 5 AND status != 'COMPLETED'
                       ON CONFLICT DO NOTHING""",
                    project_id)

                # Material shortage alerts
                await conn.execute(
                    """INSERT INTO schedule_alerts (alert_id, project_id, alert_type, activity_id, alert_title, severity, recommended_action)
                       SELECT gen_random_uuid(), project_id, 'MATERIAL_SHORTAGE', NULL,
                              'Material shortage: ' || resource_name || ' shortfall = ' || shortfall::TEXT,
                              CASE WHEN shortfall > 100 THEN 'HIGH' ELSE 'MEDIUM' END,
                              'Expedite procurement or find alternative supplier'
                       FROM resource_shortages WHERE project_id = $1 AND status = 'OPEN'
                       ON CONFLICT DO NOTHING""",
                    project_id)

                # NDT overdue alerts
                await conn.execute(
                    """INSERT INTO schedule_alerts (alert_id, project_id, alert_type, activity_id, alert_title, severity, recommended_action)
                       SELECT gen_random_uuid(), project_id, 'NDT_OVERDUE', activity_id,
                              'NDT request overdue: method=' || ndt_method || ' weld=' || COALESCE(weld_joint_id, 'N/A'),
                              'HIGH',
                              'Schedule inspection immediately'
                       FROM ndt_requests WHERE project_id = $1 AND status NOT IN ('COMPLETED', 'CANCELLED')
                       AND requested_date < CURRENT_DATE - INTERVAL '7 days'
                       ON CONFLICT DO NOTHING""",
                    project_id)

                # Fetch alerts for broadcasting (within transaction to ensure consistency)
                alerts = await conn.fetch(
                    "SELECT * FROM schedule_alerts WHERE project_id = $1 AND is_resolved = FALSE ORDER BY severity",
                    project_id)

        alerts_list = [dict(a) for a in alerts]
        await manager.broadcast_to_project(project_id, {
            "type": "ALERTS_UPDATED",
            "payload": {"alerts": alerts_list, "count": len(alerts_list)},
        })
        return alerts_list
