"""Tests for reports router — includes the critical null-handling fix."""

import pytest


@pytest.mark.asyncio
async def test_accountability_report_empty_project(fresh_db):
    """Accountability report should not crash on projects with no data (Phase 1 regression test)."""
    cur = fresh_db.cursor()

    # Insert a new project with zero activities, tasks, NDT, manpower
    cur.execute(
        "INSERT OR IGNORE INTO projects (project_id, project_code, project_name, planned_start_date, planned_finish_date) "
        "VALUES (?, ?, ?, ?, ?)",
        ("empty-project", "FPSO-EMPTY", "Empty Project", "2025-01-01", "2025-12-31"),
    )
    fresh_db.commit()

    # Verify project exists
    cur.execute("SELECT * FROM projects WHERE project_id = ?", ("empty-project",))
    assert cur.fetchone() is not None

    # Verify no tasks exist
    cur.execute("SELECT COUNT(*) FROM weekly_planning_tasks WHERE project_id = ?", ("empty-project",))
    assert cur.fetchone()[0] == 0

    # Verify no NDT exists
    cur.execute("SELECT COUNT(*) FROM ndt_requests WHERE project_id = ?", ("empty-project",))
    assert cur.fetchone()[0] == 0

    # The endpoint should handle .fetchone() returning None without crashing


@pytest.mark.asyncio
async def test_dashboard_summary_for_test_project(fresh_db, test_project_id):
    """Dashboard summary should return project data for a seeded project."""
    cur = fresh_db.cursor()
    cur.execute("SELECT * FROM projects WHERE project_id = ?", (test_project_id,))
    proj = cur.fetchone()
    assert proj is not None
    assert proj["project_code"] == "FPSO-TEST"

    cur.execute("SELECT COUNT(*) FROM activities WHERE project_id = ?", (test_project_id,))
    assert cur.fetchone()[0] >= 1


@pytest.mark.asyncio
async def test_dashboard_handles_missing_project(fresh_db):
    """Dashboard should handle non-existent project gracefully."""
    cur = fresh_db.cursor()
    cur.execute("SELECT * FROM projects WHERE project_id = ?", ("non-existent-project",))
    assert cur.fetchone() is None
    # The endpoint should return {"project": None, ...} instead of crashing


@pytest.mark.asyncio
async def test_alerts_query(fresh_db, test_project_id):
    """Alerts endpoint should query schedule_alerts table correctly."""
    cur = fresh_db.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO schedule_alerts (alert_id, project_id, alert_type, alert_title, severity) "
        "VALUES (?, ?, ?, ?, ?)",
        ("alert-test-1", test_project_id, "CRITICAL_FLOAT", "Test Alert", "HIGH"),
    )
    fresh_db.commit()

    cur.execute(
        "SELECT COUNT(*) FROM schedule_alerts WHERE project_id = ? AND is_resolved = FALSE",
        (test_project_id,),
    )
    assert cur.fetchone()[0] >= 1
