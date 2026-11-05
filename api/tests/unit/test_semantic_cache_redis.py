from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services import semantic_cache


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value


@pytest.fixture
def fake_cache(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(semantic_cache, "_ensure_redis", AsyncMock(return_value=True))
    monkeypatch.setattr(semantic_cache, "_redis", redis)
    return redis


@pytest.mark.anyio
async def test_cache_miss_then_hit(fake_cache):
    assert await semantic_cache.check_cache("review the deployment plan", "m", "user-a") is None
    await semantic_cache.store_cache(
        "review the deployment plan",
        "m",
        {"content": "cached"},
        scope="user-a",
    )
    hit = await semantic_cache.check_cache("review the deployment plan", "m", "user-a")
    assert hit == {"content": "cached"}
    assert await semantic_cache.check_cache("review the deployment plan", "m", "user-b") is None


@pytest.mark.anyio
async def test_cache_skips_short_and_high_risk(fake_cache):
    assert await semantic_cache.check_cache("a", "m", "user-a") is None
    assert await semantic_cache.check_cache("review plan", "m", "user-a", "critical") is None
    await semantic_cache.store_cache("review plan", "m", {"x": 1}, scope="user-a", risk_level="high")
    assert fake_cache.data == {}


@pytest.mark.anyio
async def test_cache_handles_corrupt_payload(fake_cache):
    key = semantic_cache.cache_key("user-a", "m", "review the deployment plan")
    fake_cache.data[key] = "not-json"
    assert await semantic_cache.check_cache("review the deployment plan", "m", "user-a") is None


def test_stats() -> None:
    before = semantic_cache.get_stats()
    semantic_cache.record_hit()
    semantic_cache.record_miss()
    after = semantic_cache.get_stats()
    assert after["total"] == before["total"] + 2
    assert json.dumps(after)