"""Tests for module structure and imports — no PostgreSQL needed."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestBackendStructure:
    """Verify all modules can be imported and have correct structure."""

    def test_routers_package_exists(self):
        """Routers package should exist."""
        import routers
        assert routers is not None

    def test_all_routers_have_router_attribute(self):
        """Each router module should export a router instance."""
        router_modules = [
            "engineering", "procurement", "construction", "inspection",
            "reports", "equipment", "completion", "commissioning",
            "quality", "safety", "training", "planning",
            "conflict", "stagegate", "feedback", "ai", "traceability_router",
            "auth_router",
        ]
        for mod_name in router_modules:
            mod = __import__(f"routers.{mod_name}", fromlist=["router"])
            assert hasattr(mod, "router"), f"{mod_name} missing 'router' attribute"

    def test_all_routers_have_prefix(self):
        """Each router should have a /api/ prefix."""
        router_modules = [
            ("engineering", "/api/engineering"),
            ("procurement", "/api/procurement"),
            ("construction", "/api/construction"),
            ("inspection", "/api/inspection"),
            ("reports", "/api/reports"),
            ("completion", "/api/completion"),
            ("commissioning", "/api/commissioning"),
            ("quality", "/api/quality"),
            ("safety", "/api/safety"),
            ("training", "/api/training"),
            ("planning", "/api/planning"),
            ("conflict", "/api/conflicts"),
            ("stagegate", "/api/stagegate"),
            ("feedback", "/api/feedback"),
            ("ai", "/api/ai"),
            ("traceability_router", "/api/traceability"),
            ("auth_router", "/api/auth"),
        ]
        for mod_name, expected_prefix in router_modules:
            mod = __import__(f"routers.{mod_name}", fromlist=["router"])
            assert mod.router.prefix == expected_prefix, \
                f"{mod_name} prefix {mod.router.prefix} != {expected_prefix}"

    def test_services_package_exists(self):
        """Services package should exist."""
        import services
        assert services is not None

    def test_ai_engine_has_agent_methods(self):
        """AIEngine should define all agent type methods."""
        from services.ai_engine import AIEngine
        engine = AIEngine()
        methods = [m for m in dir(engine) if not m.startswith('_') and callable(getattr(engine, m, None))]
        expected = ["analyze_schedule_risk", "detect_conflicts", "assess_stage_gate",
                    "compose_weekly_report"]
        for name in expected:
            assert name in methods, f"AIEngine missing method: {name}"

    def test_planning_service_has_methods(self):
        """PlanningService deprecated in Phase 5 — logic moved to routers/planning.py."""
        import pytest
        pytest.skip("PlanningService deprecated — inline in routers/planning.py")

    def test_traceability_service_has_methods(self):
        """TraceabilityService should define all trace methods."""
        from services.traceability_service import TraceabilityService
        methods = [m for m in dir(TraceabilityService) if not m.startswith('_')]
        expected = ["forward_trace", "backward_trace", "impact_analysis",
                    "full_traceability_matrix"]
        for name in expected:
            assert name in methods, f"TraceabilityService missing method: {name}"

    def test_config_has_ai_settings(self):
        """Config should include all AI-related settings."""
        from config import settings
        ai_fields = ["anthropic_api_key", "anthropic_model", "ai_enabled",
                     "ai_max_tokens", "ai_temperature", "langgraph_checkpointer"]
        for field in ai_fields:
            assert hasattr(settings, field), f"Settings missing: {field}"

    def test_routers_count(self):
        """Should have exactly 17 routers + __init__.py in the routers package."""
        import routers
        router_dir = os.path.dirname(routers.__file__)
        py_files = [f for f in os.listdir(router_dir) if f.endswith('.py') and f != '__init__.py']
        assert len(py_files) == 18, f"Expected 18 routers, found {len(py_files)}: {py_files}"
