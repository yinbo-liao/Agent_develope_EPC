from __future__ import annotations

import asyncio

import pytest

from app.services.cost_governor import CostGovernor


@pytest.fixture
def governor(monkeypatch: pytest.MonkeyPatch) -> CostGovernor:
    governor = CostGovernor("redis://localhost:1/0")

    async def no_redis() -> bool:
        return False

    monkeypatch.setattr(governor, "_ensure_redis", no_redis)
    governor.set_tier("budget-user", "free")
    return governor


@pytest.mark.anyio
async def test_reservation_enforces_limit(governor: CostGovernor) -> None:
    allowed, _ = await governor.reserve_budget("budget-user", 6_000, 0.2)
    assert allowed is True
    denied, details = await governor.reserve_budget("budget-user", 5_000, 0.2)
    assert denied is False
    assert "limit" in str(details["reason"]).lower()


@pytest.mark.anyio
async def test_commit_adjusts_to_actual_usage(governor: CostGovernor) -> None:
    allowed, _ = await governor.reserve_budget("budget-user", 6_000, 0.5)
    assert allowed is True
    await governor.commit_usage(
        "budget-user",
        "task-1",
        reserved_tokens=6_000,
        reserved_cost=0.5,
        actual_tokens=1_000,
        actual_cost=0.1,
        model="claude-haiku-3-5",
    )
    # 9k of the 10k token budget is still available.
    allowed, _ = await governor.reserve_budget("budget-user", 9_000, 0.1)
    assert allowed is True


@pytest.mark.anyio
async def test_failed_call_releases_reservation(governor: CostGovernor) -> None:
    allowed, _ = await governor.reserve_budget("budget-user", 8_000, 0.2)
    assert allowed is True
    await governor.commit_usage(
        "budget-user",
        "task-1",
        reserved_tokens=8_000,
        reserved_cost=0.2,
        actual_tokens=0,
        actual_cost=0.0,
        model="claude-haiku-3-5",
    )
    allowed, _ = await governor.reserve_budget("budget-user", 9_000, 0.2)
    assert allowed is True


@pytest.mark.anyio
async def test_concurrent_reservations_are_atomic(governor: CostGovernor) -> None:
    async def attempt() -> bool:
        allowed, _ = await governor.reserve_budget("budget-user", 6_000, 0.2)
        return allowed

    results = await asyncio.gather(*(attempt() for _ in range(10)))
    assert sum(1 for allowed in results if allowed) == 1