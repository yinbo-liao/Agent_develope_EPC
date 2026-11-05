from __future__ import annotations

import pytest

from app.services.semantic_cache import cache_key, check_cache


def test_cache_key_is_scoped() -> None:
    assert cache_key("user-a", "gpt", "review deploy plan") != cache_key(
        "user-b", "gpt", "review deploy plan"
    )
    assert cache_key("user-a", "gpt", "review deploy plan") == cache_key(
        "user-a", "gpt", "review deploy plan"
    )


@pytest.mark.anyio
async def test_high_risk_bypasses_cache() -> None:
    assert await check_cache("review deploy plan", "gpt", "user-a", "critical") is None
    assert await check_cache("review deploy plan", "gpt", "user-a", "high") is None