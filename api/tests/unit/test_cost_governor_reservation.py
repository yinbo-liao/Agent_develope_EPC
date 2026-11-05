from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.cost_governor import CostGovernor


class FakePipeline:
    def __init__(self) -> None:
        self.operations: list[tuple[str, tuple]] = []

    def incrby(self, *args):
        self.operations.append(("incrby", args))
        return self

    def incrbyfloat(self, *args):
        self.operations.append(("incrbyfloat", args))
        return self

    def hincrby(self, *args):
        self.operations.append(("hincrby", args))
        return self

    def expire(self, *args):
        self.operations.append(("expire", args))
        return self

    async def execute(self):
        return []


class FakeRedis:
    def __init__(self, eval_result):
        self.eval_result = eval_result
        self.eval_calls = 0
        self.pipeline_obj = FakePipeline()

    async def eval(self, *args):
        self.eval_calls += 1
        return self.eval_result

    def pipeline(self):
        return self.pipeline_obj

    async def get(self, key):
        return "0.5"

    async def sismember(self, *args):
        return False

    async def sadd(self, *args):
        return 1

    async def expire(self, *args):
        return True


@pytest.fixture
def governor(monkeypatch):
    governor = CostGovernor("redis://localhost:1/0")
    governor.set_tier("user-1", "starter")
    fake = FakeRedis([1, "100", "0.5", ""])
    monkeypatch.setattr(governor, "_ensure_redis", AsyncMock(return_value=True))
    governor._redis = fake  # type: ignore[assignment]
    return governor, fake


@pytest.mark.anyio
async def test_redis_reservation_allowed(governor):
    governor, fake = governor
    allowed, details = await governor.reserve_budget("user-1", 100, 0.1)
    assert allowed is True
    assert details["reserved_tokens"] == 100
    assert fake.eval_calls == 1


@pytest.mark.anyio
async def test_redis_reservation_denied(governor):
    governor, fake = governor
    fake.eval_result = [0, "5000", "8.0", "Daily token limit exceeded"]
    allowed, details = await governor.reserve_budget("user-1", 100, 0.1)
    assert allowed is False
    assert "Daily token" in details["reason"]


@pytest.mark.anyio
async def test_redis_commit_reconciles(governor):
    governor, fake = governor
    await governor.commit_usage(
        "user-1",
        "task-1",
        reserved_tokens=100,
        reserved_cost=0.1,
        actual_tokens=60,
        actual_cost=0.05,
        model="m",
    )
    ops = dict((name, args) for name, args in fake.pipeline_obj.operations)
    assert ops["incrby"][1] == -40
    assert ops["hincrby"][2] == 60