from __future__ import annotations


import pytest

from app.core.circuit_breaker import CircuitBreaker


@pytest.mark.anyio
async def test_circuit_breaker_starts_closed() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    async with breaker:
        pass
    # No exception raised means the breaker allowed the call


@pytest.mark.anyio
async def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=30)

    for _ in range(2):
        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("Simulated failure")

    # Third call should be blocked because the breaker is open
    with pytest.raises(RuntimeError, match="CircuitBreaker"):
        async with breaker:
            pass


@pytest.mark.anyio
async def test_circuit_breaker_resets_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

    # One failure
    with pytest.raises(ValueError):
        async with breaker:
            raise ValueError("Failure")

    # One success should reset the failure count
    async with breaker:
        pass

    # Now it should take 3 more failures to open
    for _ in range(2):
        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("Failure")

    # Still closed (only 3 total failures, but one was reset)
    async with breaker:
        pass


@pytest.mark.anyio
async def test_circuit_breaker_half_open_recovery() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0)  # 0s timeout

    # Open the breaker
    with pytest.raises(ValueError):
        async with breaker:
            raise ValueError("Failure")

    # Since timeout is 0, it should be in half-open (recovery_timeout passed immediately)
    # Next call should work if successful
    async with breaker:
        pass
    # Breaker should now be closed again
