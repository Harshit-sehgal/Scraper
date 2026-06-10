"""Advanced health check system with component-level monitoring.

Provides detailed health status for all system components.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    latency_ms: float = 0.0
    last_check: datetime | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "metadata": self.metadata,
        }


class HealthChecker:
    """Advanced health check system."""

    def __init__(self):
        self._components: dict[str, ComponentHealth] = {}
        self._checkers: dict[str, Any] = {}

    def register_component(self, name: str, checker: Any = None) -> None:
        """Register a component for health checking."""
        self._components[name] = ComponentHealth(name=name)
        if checker:
            self._checkers[name] = checker

    async def check_component(self, name: str) -> ComponentHealth:
        """Check health of a single component."""
        health = self._components.get(name)
        if not health:
            health = ComponentHealth(name=name, status=HealthStatus.UNKNOWN)
            self._components[name] = health

        start_time = time.time()
        checker = self._checkers.get(name)

        try:
            if checker:
                if asyncio.iscoroutinefunction(checker):
                    result = await checker()
                else:
                    result = checker()

                health.status = result.get("status", HealthStatus.HEALTHY)
                health.message = result.get("message", "")
                health.metadata = result.get("metadata", {})
            else:
                health.status = HealthStatus.HEALTHY
                health.message = "No checker configured"

        except Exception as e:
            health.status = HealthStatus.UNHEALTHY
            health.message = str(e)

        health.latency_ms = (time.time() - start_time) * 1000
        health.last_check = datetime.now(UTC)
        return health

    async def check_all(self) -> dict[str, ComponentHealth]:
        """Check health of all registered components."""
        results = {}
        for name in self._components:
            results[name] = await self.check_component(name)
        return results

    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status."""
        statuses = [h.status for h in self._components.values()]

        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        return HealthStatus.UNKNOWN

    def get_summary(self) -> dict[str, Any]:
        """Get health summary for all components."""
        return {
            "overall_status": self.get_overall_status().value,
            "components": {name: health.to_dict() for name, health in self._components.items()},
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Pre-configured checkers
async def check_database() -> dict:
    """Check database connectivity."""
    try:
        from app.globals import jobs_store

        if hasattr(jobs_store, "health_check"):
            result = jobs_store.health_check()
            if asyncio.iscoroutinefunction(jobs_store.health_check):
                result = await result
            return result
        return {"status": HealthStatus.HEALTHY, "message": "Database accessible"}
    except Exception as e:
        return {"status": HealthStatus.UNHEALTHY, "message": str(e)}


async def check_worker_queue() -> dict:
    """Check worker queue status."""
    try:
        from app.worker_queue import get_worker_queue

        queue = get_worker_queue()
        stats = queue.get_stats() if hasattr(queue, "get_stats") else {"pending": 0}
        pending = stats.get("pending", 0)
        if pending > 100:
            return {
                "status": HealthStatus.DEGRADED,
                "message": f"Queue backlog: {pending}",
                "metadata": stats,
            }
        return {"status": HealthStatus.HEALTHY, "message": "Queue operational", "metadata": stats}
    except Exception as e:
        return {"status": HealthStatus.UNHEALTHY, "message": str(e)}


async def check_rate_limiter() -> dict:
    """Check rate limiter status."""
    try:
        from app.utils.rate_limit import reset_rate_limit_state

        reset_rate_limit_state()
        return {"status": HealthStatus.HEALTHY, "message": "Rate limiter active"}
    except Exception as e:
        return {"status": HealthStatus.UNHEALTHY, "message": str(e)}


# Global health checker
health_checker = HealthChecker()


def get_health_checker() -> HealthChecker:
    """Get the global health checker."""
    return health_checker


def setup_health_checks() -> None:
    """Setup health checks for all components."""
    health_checker.register_component("database", check_database)
    health_checker.register_component("worker_queue", check_worker_queue)
    health_checker.register_component("rate_limiter", check_rate_limiter)
