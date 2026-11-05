from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workflows import nodes


class DummyBreaker:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_run(**overrides):
    values = {
        "id": "task-1",
        "user_id": "user-1",
        "input_query": "review the deployment plan",
        "token_budget": 10_000,
        "total_tokens_used": 0,
        "cost_usd": 0.0,
        "risk_level": "low",
        "retrieval_results": [],
        "final_response": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def common_patches(monkeypatch):
    monkeypatch.setattr(nodes.breaker_registry, "get_llm_breaker", lambda model: DummyBreaker())
    monkeypatch.setattr(nodes.cost_governor, "reserve_budget", AsyncMock(return_value=(True, {})))
    monkeypatch.setattr(nodes.cost_governor, "commit_usage", AsyncMock())
    monkeypatch.setattr(nodes, "store_cache", AsyncMock())
    monkeypatch.setattr(nodes, "record_hit", MagicMock())
    monkeypatch.setattr(nodes, "record_miss", MagicMock())
    monkeypatch.setattr(nodes, "track_llm_cost", MagicMock())


@pytest.mark.anyio
async def test_auto_generate_cache_hit(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_model",
        AsyncMock(return_value={"model": "fast", "estimated_cost": 0.01}),
    )
    monkeypatch.setattr(
        nodes, "check_cache", AsyncMock(return_value={"content": "cached", "tokens_used": 11})
    )
    result = await nodes.auto_generate_response(make_run())
    assert result["current_status"] == "completed"
    assert result["final_response"] == "cached"
    assert result["total_tokens_used"] == 11


@pytest.mark.anyio
async def test_auto_generate_success(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_model",
        AsyncMock(return_value={"model": "fast", "estimated_cost": 0.01}),
    )
    monkeypatch.setattr(nodes, "check_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(
        nodes.LLMClient,
        "generate",
        AsyncMock(
            return_value={
                "content": "generated",
                "tokens_used": 20,
                "cost_usd": 0.02,
                "model": "fast",
            }
        ),
    )
    result = await nodes.auto_generate_response(make_run())
    assert result["final_response"] == "generated"
    assert result["cost_usd"] == 0.02


@pytest.mark.anyio
async def test_auto_generate_budget_guard(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_model",
        AsyncMock(return_value={"model": "fast", "estimated_cost": 0.01}),
    )
    monkeypatch.setattr(
        nodes.cost_governor,
        "reserve_budget",
        AsyncMock(return_value=(False, {"reason": "daily token limit exceeded"})),
    )
    result = await nodes.auto_generate_response(make_run())
    assert result["current_status"] == "failed"
    assert result["current_step"] == "budget_guard"


@pytest.mark.anyio
async def test_auto_generate_releases_reservation_on_error(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_model",
        AsyncMock(return_value={"model": "fast", "estimated_cost": 0.01}),
    )
    monkeypatch.setattr(nodes, "check_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(nodes.LLMClient, "generate", AsyncMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        await nodes.auto_generate_response(make_run())
    nodes.cost_governor.commit_usage.assert_awaited()


@pytest.mark.anyio
async def test_complex_analysis_first_tier(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_cascade",
        AsyncMock(return_value={"models": ["m1"], "model": "m1"}),
    )
    monkeypatch.setattr(nodes.model_router, "estimate_cost", MagicMock(return_value=0.01))
    monkeypatch.setattr(nodes, "score_confidence", MagicMock(return_value=0.9))
    monkeypatch.setattr(
        nodes.LLMClient,
        "generate",
        AsyncMock(
            return_value={"content": "analysis", "tokens_used": 30, "cost_usd": 0.03, "model": "m1"}
        ),
    )
    result = await nodes.complex_analysis(make_run(risk_level="high"))
    assert result["current_status"] == "completed"
    assert result["final_response"] == "analysis"


@pytest.mark.anyio
async def test_complex_analysis_escalates_after_circuit(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_cascade",
        AsyncMock(return_value={"models": ["m1", "m2"], "model": "m1"}),
    )
    monkeypatch.setattr(nodes.model_router, "estimate_cost", MagicMock(return_value=0.01))
    monkeypatch.setattr(nodes, "score_confidence", MagicMock(return_value=0.9))
    monkeypatch.setattr(
        nodes.LLMClient,
        "generate",
        AsyncMock(
            side_effect=[
                RuntimeError("circuit open"),
                {"content": "second", "tokens_used": 5, "cost_usd": 0.01, "model": "m2"},
            ]
        ),
    )
    result = await nodes.complex_analysis(make_run(risk_level="high"))
    assert result["final_response"] == "second"


@pytest.mark.anyio
async def test_complex_analysis_budget_denied(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_cascade",
        AsyncMock(return_value={"models": ["m1"], "model": "m1"}),
    )
    monkeypatch.setattr(nodes.model_router, "estimate_cost", MagicMock(return_value=0.01))
    monkeypatch.setattr(
        nodes.cost_governor,
        "reserve_budget",
        AsyncMock(return_value=(False, {"reason": "cost limit"})),
    )
    result = await nodes.complex_analysis(make_run(risk_level="high"))
    assert result["current_status"] == "failed"


@pytest.mark.anyio
async def test_complex_analysis_all_tiers_fail(monkeypatch):
    monkeypatch.setattr(
        nodes.model_router,
        "select_cascade",
        AsyncMock(return_value={"models": ["m1"], "model": "m1"}),
    )
    monkeypatch.setattr(nodes.model_router, "estimate_cost", MagicMock(return_value=0.01))
    monkeypatch.setattr(nodes.LLMClient, "generate", AsyncMock(side_effect=RuntimeError("open")))
    result = await nodes.complex_analysis(make_run(risk_level="high"))
    assert result["current_status"] == "failed"


@pytest.mark.anyio
async def test_validate_and_quality_helpers():
    assert (await nodes.validate_input(make_run(input_query="   ")))["current_status"] == "failed"
    assert (await nodes.validate_input(make_run()))["current_status"] == "retrieving"
    short = await nodes.evaluate_output_quality(make_run(final_response="short"))
    assert short["needs_refinement"] is True
    long = await nodes.evaluate_output_quality(
        make_run(final_response="Step one: do this. You should try to do that. " * 2)
    )
    assert long["needs_refinement"] is False


@pytest.mark.anyio
async def test_meta_review_paths(monkeypatch):
    empty = await nodes.meta_review_node(make_run(final_response=""))
    assert empty["needs_regeneration"] is True
    monkeypatch.setattr(
        nodes.LLMClient,
        "generate",
        AsyncMock(return_value={"content": "YES, acceptable"}),
    )
    passed = await nodes.meta_review_node(make_run(final_response="some response"))
    assert passed["review_passed"] is True
    monkeypatch.setattr(
        nodes.LLMClient,
        "generate",
        AsyncMock(side_effect=RuntimeError("circuit")),
    )
    skipped = await nodes.meta_review_node(make_run(final_response="some response"))
    assert skipped["review_passed"] is True


def test_risk_bias_adjustment():
    nodes.adjust_risk_bias("pattern", "approved")
    assert nodes.get_risk_biases()["pattern"] < 1.0
    nodes.adjust_risk_bias("pattern", "rejected")
    nodes.adjust_risk_bias("pattern", "rejected")
    assert nodes.get_risk_biases()["pattern"] > 1.0