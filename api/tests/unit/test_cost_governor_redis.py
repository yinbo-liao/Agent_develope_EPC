from __future__ import annotations

import pytest

from app.services.cost_governor import BudgetTier, CostGovernor


@pytest.mark.anyio
async def test_redis_unavailable_falls_back_to_memory() -> None:
    """When Redis is unreachable, check_budget should use in-memory fallback."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    governor._user_tiers["test-user"] = BudgetTier.STARTER

    allowed, details = await governor.check_budget(
        "test-user", estimated_tokens=100, estimated_cost=0.01
    )
    assert allowed is True
    assert details["tier"] == "starter"


@pytest.mark.anyio
async def test_record_usage_fallback_increments_counters() -> None:
    """When Redis is unavailable, record_usage should use in-memory counters."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    governor._user_tiers["test-user"] = BudgetTier.STARTER

    await governor.record_usage("test-user", "task-1", tokens=500, cost_usd=0.05, model="claude-haiku-3-5")

    usage = governor._current_usage("test-user")
    assert int(usage["tokens"]) == 500
    assert float(usage["cost"]) == 0.05


@pytest.mark.anyio
async def test_record_usage_tracks_multiple_models() -> None:
    """Recording usage with different models should accumulate per-model tokens."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    governor._user_tiers["test-user"] = BudgetTier.PROFESSIONAL

    await governor.record_usage("test-user", "task-1", tokens=300, cost_usd=0.03, model="claude-haiku-3-5")
    await governor.record_usage("test-user", "task-2", tokens=700, cost_usd=0.10, model="claude-sonnet-4-6")

    usage = governor._current_usage("test-user")
    models = usage["models"]
    assert isinstance(models, dict)
    assert int(models.get("claude-haiku-3-5", 0)) == 300
    assert int(models.get("claude-sonnet-4-6", 0)) == 700


@pytest.mark.anyio
async def test_get_status_with_in_memory_fallback() -> None:
    """get_status should work with in-memory fallback and return correct breakdown."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    governor._user_tiers["test-user"] = BudgetTier.PROFESSIONAL

    await governor.record_usage("test-user", "task-1", tokens=1000, cost_usd=0.10, model="claude-sonnet-4-6")

    status = await governor.get_status("test-user")
    assert status["user_id"] == "test-user"
    assert status["budget_tier"] == "professional"
    assert status["tokens_used"] == 1000
    assert status["current_cost_usd"] == 0.10
    assert len(status["model_breakdown"]) >= 1


@pytest.mark.anyio
async def test_check_budget_edge_zero_limits() -> None:
    """Budget check with zero estimated usage should always pass."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    governor._user_tiers["test-user"] = BudgetTier.FREE

    allowed, details = await governor.check_budget(
        "test-user", estimated_tokens=0, estimated_cost=0.0
    )
    assert allowed is True


@pytest.mark.anyio
async def test_check_budget_tracks_multiple_users_independently() -> None:
    """Different users should have independent usage counters."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    governor._user_tiers["user-a"] = BudgetTier.FREE
    governor._user_tiers["user-b"] = BudgetTier.STARTER

    # User A uses almost all their Free tier tokens
    allowed_a, _ = await governor.check_budget(
        "user-a", estimated_tokens=9_000, estimated_cost=0.5
    )
    assert allowed_a is True

    # User B should NOT be affected by User A's usage
    allowed_b, details_b = await governor.check_budget(
        "user-b", estimated_tokens=50_000, estimated_cost=5.0
    )
    assert allowed_b is True
    assert details_b["tier"] == "starter"


@pytest.mark.anyio
async def test_close_sets_redis_unavailable() -> None:
    """After close(), redis should be marked unavailable."""
    governor = CostGovernor(redis_url="redis://invalid-host:9999/0")
    # Force redis init
    await governor._ensure_redis()
    # Close
    await governor.close()
    assert governor._redis_available is False
