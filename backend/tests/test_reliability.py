"""Reliability / data-integrity regression tests.

These tests are deliberately offline (no PostgreSQL, no live server). They
cover the pure date/number helpers introduced by the reliability hardening
work and assert static properties of SQL/migration files where a runtime
database is not available.

Run from backend/:
    python -m pytest tests/test_reliability.py -v
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
MIGRATION_005 = REPO_ROOT / "database" / "migrations" / "005_reliability_constraints.sql"


# ── Planning: month arithmetic ────────────────────────────────────────────

def test_add_months_from_november_and_december():
    from routers.planning import add_months

    # Nov 2025 + 1..3 months must roll over the year without month 13.
    assert add_months(date(2025, 11, 1), 1) == date(2025, 12, 1)
    assert add_months(date(2025, 11, 1), 2) == date(2026, 1, 1)
    assert add_months(date(2025, 12, 1), 1) == date(2026, 1, 1)
    assert add_months(date(2025, 12, 1), 2) == date(2026, 2, 1)


def test_add_months_handles_negative_offsets():
    from routers.planning import add_months

    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert add_months(date(2026, 1, 1), -13) == date(2024, 12, 1)


def test_month_bounds_across_year_end():
    from routers.planning import month_bounds

    start, end = month_bounds(date(2025, 12, 15), 1)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 1, 31)

    start, end = month_bounds(date(2026, 1, 1), 0)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 1, 31)


def test_next_week_start_monday_edges():
    from routers.planning import next_week_start

    monday = date(2026, 11, 2)
    assert monday.weekday() == 0
    assert next_week_start(monday) == monday  # Monday stays put

    sunday = monday + timedelta(days=6)
    assert next_week_start(sunday) == monday + timedelta(days=7)

    tuesday = monday + timedelta(days=1)
    assert next_week_start(tuesday).weekday() == 0
    assert next_week_start(tuesday) == monday + timedelta(days=7)


def test_bi_month_and_four_month_starts_roll_over_year():
    from routers.planning import bi_month_start, four_month_start

    assert bi_month_start(date(2025, 11, 15), 0) == date(2025, 11, 1)
    assert bi_month_start(date(2025, 11, 15), 1) == date(2026, 1, 1)
    assert four_month_start(date(2025, 11, 15)) == date(2025, 9, 1)
    assert four_month_start(date(2026, 1, 15)) == date(2026, 1, 1)


def test_build_periods_counts_and_ranges():
    from routers.planning import build_periods

    periods = build_periods(date(2025, 11, 6))
    counts = {}
    for p in periods:
        counts[p["ptype"]] = counts.get(p["ptype"], 0) + 1
        assert p["pstart"] <= p["pend"]
        assert 1 <= p["pstart"].month <= 12
        assert 1 <= p["pend"].month <= 12

    assert counts == {
        "WEEKLY": 16,
        "BI_WEEKLY": 8,
        "MONTHLY": 4,
        "BI_MONTHLY": 2,
        "FOUR_MONTH": 1,
    }


# ── Completion: punch number uniqueness ───────────────────────────────────

def test_punch_numbers_are_unique_across_a_day():
    from routers.completion import (
        punch_number_prefix,
        build_punch_number,
        next_sequence_from,
    )

    prefix = punch_number_prefix("demo-project", date(2026, 11, 6))
    numbers = [build_punch_number(prefix, seq) for seq in range(1, 51)]
    assert len(numbers) == len(set(numbers))

    # Sequences resume correctly from the highest previous number.
    assert next_sequence_from(numbers[-1], prefix) == 51
    assert next_sequence_from(None, prefix) == 1
    assert next_sequence_from("garbage", prefix) == 1


# ── Conflicts: static route registration order ────────────────────────────

def test_conflict_static_routes_are_registered_before_catch_all():
    from routers.conflict import router

    paths = [route.path for route in router.routes]
    summary_idx = paths.index("/api/conflicts/summary/{project_id}")
    actions_idx = paths.index("/api/conflicts/actions/{project_id}")
    catch_all_idx = paths.index("/api/conflicts/{project_id}/{conflict_id}")

    assert summary_idx < catch_all_idx, "summary route is shadowed by the catch-all"
    assert actions_idx < catch_all_idx, "actions route is shadowed by the catch-all"


# ── Alerts: deduplication contract ────────────────────────────────────────

def test_alert_service_uses_partial_unique_conflict_target():
    source = (BACKEND_DIR / "services" / "alert_service.py").read_text(encoding="utf-8")
    assert "ON CONFLICT (project_id, alert_type, entity_id)" in source
    assert "WHERE is_resolved = FALSE DO NOTHING" in source
    assert "run_alert_cycle" in source


def test_migration_005_declares_required_constraints_and_indexes():
    sql = MIGRATION_005.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS entity_id UUID" in sql
    assert "uq_schedule_alerts_unresolved_entity" in sql
    assert "WHERE is_resolved = FALSE" in sql

    required_indexes = [
        "idx_purchase_items_po_material",
        "idx_drawing_materials_drawing_project",
        "idx_material_takeoff_drawing_project",
        "idx_ndt_requests_drawing",
        "idx_weld_tracking_drawing",
        "idx_ai_messages_session",
        "idx_conflicts_project_status",
        "idx_punch_items_project_status",
        "idx_plan_items_period",
    ]
    for name in required_indexes:
        assert name in sql, f"migration 005 is missing {name}"


# ── AI: JSONB serialization ───────────────────────────────────────────────

def test_serialize_tool_calls_produces_valid_json():
    try:
        from routers.ai import serialize_tool_calls
    except ImportError as exc:  # optional AI SDKs may be absent offline
        pytest.skip(f"AI router not importable offline: {exc}")

    raw = [{"name": "query_activities", "args": {"status": "IN_PROGRESS"}, "result_summary": "3 rows"}]
    encoded = serialize_tool_calls(raw)
    assert isinstance(encoded, str)
    assert json.loads(encoded) == raw
    # Python repr is never valid JSON when it contains single quotes.
    assert "'" not in encoded
    assert serialize_tool_calls([]) == "[]"
    assert serialize_tool_calls(None) == "[]"


# ── AI tools: static SQL sanity ───────────────────────────────────────────

def test_query_tools_do_not_reference_nonexistent_columns():
    source = (BACKEND_DIR / "services" / "tools" / "query_tools.py").read_text(encoding="utf-8")
    # Columns that do not exist in the schema (were in the old queries).
    assert "sgc.item_id" not in source
    assert "ncr.title" not in source
    assert "ptr.status" not in source
    # certification_expired: the filter adds no placeholder, so the index used
    # by the trailing LIMIT must not advance.
    assert 'query += " AND ptr.expiry_date < CURRENT_DATE"' in source
    assert "No placeholder is introduced here" in source


def test_stagegate_recalculation_uses_correlated_subquery():
    source = (BACKEND_DIR / "routers" / "stagegate.py").read_text(encoding="utf-8")
    assert "FROM stage_gate_checklist c WHERE c.gate_id = sg.gate_id" in source
    assert "AND sg.project_id = :pid" in source


def test_ai_router_serializes_tool_calls_with_json_dumps():
    source = (BACKEND_DIR / "routers" / "ai.py").read_text(encoding="utf-8")
    assert "json.dumps(tool_calls" in source
    assert "str(tool_calls)" not in source
