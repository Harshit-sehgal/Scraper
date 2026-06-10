"""Circuit breaker pattern for fault tolerance.

Implements the circuit breaker pattern to prevent cascading failures
when external services (LLM APIs, databases, etc.) are unavailable.

States:
- CLOSED: Normal operation, requests flow through
- OPEN: Service is failing, requests are rejected immediately
- HALF_OPEN: Testing if service has recovered
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    expected_exception: type = Exception


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""


class CircuitBreaker:
    """Circuit breaker implementation.

    Usage:
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

        @breaker
        async def call_external_service():
            # If this fails 3 times, circuit opens for 10 seconds
            ...

        # Or use as context manager
        async with breaker:
            await call_external_service()
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        expected_exception: type = Exception,
    ):
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            expected_exception=expected_exception,
        )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current state, checking if we should transition to half-open."""
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time
            and time.time() - self._last_failure_time >= self.config.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def success_count(self) -> int:
        return self._success_count

    async def __aenter__(self):
        """Context manager entry."""
        await self._check_state()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            await self._on_success()
        elif issubclass(exc_type, self.config.expected_exception):
            await self._on_failure()
        return False

    async def _check_state(self):
        """Check if we should allow the request."""
        current_state = self.state
        if current_state == CircuitState.OPEN:
            msg = f"Circuit breaker '{self.name}' is OPEN. Service unavailable for {self.config.recovery_timeout}s."
            raise CircuitBreakerError(msg)
        if current_state == CircuitState.HALF_OPEN:
            async with self._lock:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    msg = f"Circuit breaker '{self.name}' is HALF_OPEN. Max calls ({self.config.half_open_max_calls}) reached."
                    raise CircuitBreakerError(msg)
                self._half_open_calls += 1

    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                # If we have enough successes, close the circuit
                if self._success_count >= self.config.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                self._success_count += 1

    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open state, reopen circuit
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN

    def __call__(self, func: Callable) -> Callable:
        """Decorator for async functions."""

        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)

        return wrapper

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "half_open_max_calls": self.config.half_open_max_calls,
            },
        }


# Pre-configured circuit breakers for common use cases
llm_circuit_breaker = CircuitBreaker(
    name="llm_api",
    failure_threshold=3,
    recovery_timeout=60.0,
    expected_exception=Exception,
)

database_circuit_breaker = CircuitBreaker(
    name="database",
    failure_threshold=5,
    recovery_timeout=30.0,
    expected_exception=Exception,
)

external_api_circuit_breaker = CircuitBreaker(
    name="external_api",
    failure_threshold=3,
    recovery_timeout=45.0,
    expected_exception=Exception,
)


def get_all_circuit_breakers() -> list[CircuitBreaker]:
    """Get all registered circuit breakers."""
    return [llm_circuit_breaker, database_circuit_breaker, external_api_circuit_breaker]


def get_circuit_breaker_stats() -> dict[str, dict]:
    """Get statistics for all circuit breakers."""
    return {cb.name: cb.get_stats() for cb in get_all_circuit_breakers()}
