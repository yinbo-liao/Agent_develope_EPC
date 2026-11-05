"""Tests for AIEngine — rule-based fallback methods (AI disabled by default)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from services.ai_engine import AIEngine


class TestAIEngineInit:
    """Tests for AIEngine initialization."""

    def test_engine_created(self):
        """AIEngine should instantiate without error."""
        engine = AIEngine()
        assert engine is not None

    def test_ai_disabled_by_default(self):
        """AI should be disabled when not configured."""
        engine = AIEngine()
        assert engine.enabled is False

    def test_client_is_none_when_disabled(self):
        """Client should be None when AI is disabled."""
        engine = AIEngine()
        assert engine._client is None


class TestBasicScheduleAnalysis:
    """Tests for _basic_schedule_analysis fallback."""

    def test_low_risk_when_no_issues(self):
        engine = AIEngine()
        activities = [
            {"total_float": 10, "status": "IN_PROGRESS", "remaining_duration": 50, "original_duration": 100},
        ]
        result = engine._basic_schedule_analysis(activities, [])
        assert result["risk_level"] == "LOW"
        assert result["generated_by"] == "rule_based"

    def test_high_risk_when_negative_float(self):
        engine = AIEngine()
        activities = [
            {"total_float": -2, "status": "IN_PROGRESS", "remaining_duration": 50, "original_duration": 100},
            {"total_float": -1, "status": "IN_PROGRESS", "remaining_duration": 30, "original_duration": 50},
        ]
        shortages = [{"shortfall": 200, "status": "OPEN"}]
        result = engine._basic_schedule_analysis(activities, shortages)
        assert result["risk_level"] == "HIGH"
        assert len(result["risks"]) >= 2

    def test_medium_risk_when_delayed(self):
        engine = AIEngine()
        activities = [
            {"total_float": 5, "status": "IN_PROGRESS", "remaining_duration": 120, "original_duration": 100},
        ]
        result = engine._basic_schedule_analysis(activities, [])
        assert result["risk_level"] == "MEDIUM"

    def test_includes_recommendations(self):
        engine = AIEngine()
        result = engine._basic_schedule_analysis([], [])
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)


class TestBasicGateAssessment:
    """Tests for _basic_gate_assessment fallback."""

    def test_high_score_when_all_complete(self):
        engine = AIEngine()
        gate = {"gate_name": "Test Gate", "from_phase": "ENGINEERING", "to_phase": "PROCUREMENT"}
        checklist = [{"is_complete": True}, {"is_complete": True}, {"is_complete": True}]
        result = engine._basic_gate_assessment(gate, checklist, 0, 0, {"ordered": 100, "received": 100}, 0)
        assert result["ai_readiness_score"] >= 7.0
        assert "APPROVE" in result["recommendation"]

    def test_low_score_when_many_open_ncrs(self):
        engine = AIEngine()
        gate = {"gate_name": "Test Gate"}
        checklist = [{"is_complete": False}] * 5
        result = engine._basic_gate_assessment(gate, checklist, 20, 10, {}, 3)
        assert result["ai_readiness_score"] < 5.0

    def test_rule_based_flag(self):
        engine = AIEngine()
        result = engine._basic_gate_assessment({}, [], 0, 0, {}, 0)
        assert result["generated_by"] == "rule_based"


class TestBasicReport:
    """Tests for _basic_report fallback."""

    def test_generates_markdown_report(self):
        engine = AIEngine()
        report = engine._basic_report(
            "test-project",
            __import__("datetime").date.today(),
            {"project_name": "Test FPSO", "current_status": "ACTIVE"},
            {"total": 10, "completed": 5, "avg_actual": 75.0},
            [{"ndt_method": "UT", "total": 5, "avg_pct": 80.0}],
            [],
            [{"resource_name": "Steel", "shortfall": 500, "status": "OPEN"}],
            [{"incident_type": "NEAR_MISS", "cnt": 2}],
        )
        assert isinstance(report, str)
        assert "Test FPSO" in report
        assert "Weekly Accountability Report" in report
        assert "NDT Progress" in report
        assert "Steel" in report
        assert "NEAR_MISS" in report


class TestParseOrFallback:
    """Tests for _parse_or_fallback."""

    def test_parses_valid_json(self):
        engine = AIEngine()
        result = engine._parse_or_fallback('{"key": "value"}', "test", {"fallback": True})
        assert result == {"key": "value"}

    def test_falls_back_on_invalid_json(self):
        engine = AIEngine()
        fallback = {"fallback": True}
        result = engine._parse_or_fallback("not json", "test", fallback)
        assert result == fallback

    def test_passes_through_none(self):
        """None is not a string, so it passes through the 'else raw_result' branch."""
        engine = AIEngine()
        result = engine._parse_or_fallback(None, "test", {"fallback": True})
        assert result is None  # None passes through as-is (not a str)

    def test_report_composer_returns_raw(self):
        engine = AIEngine()
        raw_report = "# My Report\nContent here"
        result = engine._parse_or_fallback(raw_report, "report_composer", "fallback")
        assert result == raw_report  # Report composer returns raw text, not JSON
