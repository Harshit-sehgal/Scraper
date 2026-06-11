"""Unit tests for the circuit breaker implementation in ``app.utils.circuit_breaker``."""

from __future__ import annotations

import asyncio

import pytest
from app.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    get_all_circuit_breakers,
    get_circuit_breaker_stats,
)


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_initial_state_closed(self) -> None:
        """Verify the circuit breaker starts in the CLOSED state."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=2)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    async def test_successful_calls_remain_closed(self) -> None:
        """Verify successful calls keep the circuit CLOSED and increment success count."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=2)

        async with breaker:
            pass

        assert breaker.state == CircuitState.CLOSED
        assert breaker.success_count == 1

    async def test_failures_below_threshold_remain_closed(self) -> None:
        """Verify failures below threshold keep the circuit CLOSED."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=3)

        for _ in range(2):
            try:
                async with breaker:
                    msg = "temporary error"
                    raise ValueError(msg)
            except ValueError:
                pass

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 2

    async def test_failures_at_threshold_trips_to_open(self) -> None:
        """Verify the circuit trips to OPEN once the failure threshold is reached."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=2)

        for _ in range(2):
            try:
                async with breaker:
                    msg = "critical error"
                    raise ValueError(msg)
            except ValueError:
                pass

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 2

        # Subsequent calls should immediately raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError, match="is OPEN"):
            async with breaker:
                pass

    async def test_open_to_half_open_transition(self) -> None:
        """Verify circuit transitions to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=1, recovery_timeout=0.01)

        try:
            async with breaker:
                msg = "fail"
                raise ValueError(msg)
        except ValueError:
            pass

        assert breaker.state == CircuitState.OPEN

        # Sleep to exceed recovery timeout
        await asyncio.sleep(0.02)

        assert breaker.state == CircuitState.HALF_OPEN

    async def test_half_open_success_closes_circuit(self) -> None:
        """Verify success in HALF_OPEN closes the circuit."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=1, recovery_timeout=0.01)

        try:
            async with breaker:
                msg = "fail"
                raise ValueError(msg)
        except ValueError:
            pass

        await asyncio.sleep(0.02)
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful call
        async with breaker:
            pass

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    async def test_half_open_failure_reopens_circuit(self) -> None:
        """Verify failure in HALF_OPEN immediately reopens the circuit."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout=0.01)

        # Trip to OPEN
        for _ in range(2):
            try:
                async with breaker:
                    msg = "fail"
                    raise ValueError(msg)
            except ValueError:
                pass

        await asyncio.sleep(0.02)
        assert breaker.state == CircuitState.HALF_OPEN

        # Failed call in HALF_OPEN
        try:
            async with breaker:
                msg = "fail again"
                raise ValueError(msg)
        except ValueError:
            pass

        assert breaker.state == CircuitState.OPEN

    async def test_decorator_usage(self) -> None:
        """Verify circuit breaker can be used as a decorator."""
        breaker = CircuitBreaker(name="test_cb", failure_threshold=1)

        @breaker
        async def decorated_func(val: int) -> int:
            if val < 0:
                msg = "invalid val"
                raise ValueError(msg)
            return val

        assert await decorated_func(5) == 5

        # Fail once to trip circuit
        with pytest.raises(ValueError, match="invalid val"):
            await decorated_func(-1)

        assert breaker.state == CircuitState.OPEN

        # Subsequent call raises CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await decorated_func(5)

    async def test_get_stats_and_global_breakers(self) -> None:
        """Verify retrieval of all registered breakers and their stats."""
        breakers = get_all_circuit_breakers()
        assert len(breakers) >= 3

        stats = get_circuit_breaker_stats()
        assert "llm_api" in stats
        assert "database" in stats
        assert "external_api" in stats

        assert stats["database"]["state"] == "closed"
