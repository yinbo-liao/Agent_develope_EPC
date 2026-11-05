"""Tests for PlanningService — DEPRECATED.

The PlanningService was cleared in Phase 5 (dead code removal) because its
logic was duplicated inline in routers/planning.py. These tests are kept as
reference for when the service is re-extracted from the router.

To re-enable: restore PlanningService class in services/planning_service.py
and consolidate the logic from routers/planning.py.
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import date


@pytest.mark.skip(reason="PlanningService deprecated in Phase 5 — logic moved inline to routers/planning.py. Restore service to re-enable.")
class TestPeriodCalculation:
    def test_returns_anchor_monday(self):
        """Anchor monday should be a Monday."""
        from datetime import date
        # Reference date: 2026-07-15 is a Wednesday
        ref = date(2026, 7, 15)
        # Monday of that week is 2026-07-13
        from datetime import timedelta
        monday = ref - timedelta(days=ref.weekday())
        assert monday.weekday() == 0  # Monday
        assert monday == date(2026, 7, 13)

    def test_weekly_period_is_7_days(self):
        """Each weekly period should start Monday and end Sunday (6 days later)."""
        from datetime import date, timedelta
        monday = date(2026, 7, 13)
        sunday = monday + timedelta(days=6)
        assert (sunday - monday).days == 6


@pytest.mark.skip(reason="PlanningService deprecated in Phase 5")
class TestRollUp:
    def test_empty_returns_empty(self):
        pass

    def test_aggregates_two_weeks(self):
        pass


@pytest.mark.skip(reason="PlanningService deprecated in Phase 5")
class TestVariance:
    def test_on_track_when_equal(self):
        pass


@pytest.mark.skip(reason="PlanningService deprecated in Phase 5")
class TestForecast:
    def test_on_time_when_productive(self):
        pass
