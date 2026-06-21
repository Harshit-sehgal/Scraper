"""Monitoring and alerting for data retention enforcement."""

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RetentionMonitor:
    """Track retention enforcement health and alert on failures."""

    def __init__(self):
        self.last_run_at: datetime.datetime | None = None
        self.last_success_at: datetime.datetime | None = None
        self.failure_count = 0
        self.total_items_purged = 0
        self.last_result: dict[str, int] | None = None

    def record_enforcement(self, result: dict[str, int] | None, error: Exception | None = None) -> None:
        """Record a retention enforcement run."""
        now = datetime.datetime.now(datetime.UTC)
        self.last_run_at = now

        if error:
            self.failure_count += 1
            logger.warning(
                "Data retention enforcement failed: %s (failure #%d)",
                error,
                self.failure_count,
            )
            if self.failure_count >= 3:
                logger.error(
                    "Data retention has failed %d times; check configuration and database connectivity",
                    self.failure_count,
                )
                self._alert_critical_retention_failure()
        else:
            self.failure_count = 0
            self.last_success_at = now
            self.last_result = result or {}

            if result:
                total = result.get("jobs_purged", 0) + result.get("recycle_purged", 0)
                self.total_items_purged += total

                logger.info(
                    "Data retention enforcement completed: %d jobs, %d recycle items purged",
                    result.get("jobs_purged", 0),
                    result.get("recycle_purged", 0),
                )

    def get_health_check(self) -> dict[str, Any]:
        """Return retention monitoring health."""
        now = datetime.datetime.now(datetime.UTC)

        health_ok = True
        status_msg = "ok"

        if self.last_run_at is None:
            health_ok = False
            status_msg = "Never run"
        else:
            hours_since_last_run = (now - self.last_run_at).total_seconds() / 3600
            if hours_since_last_run > 25:  # More than 1 day
                health_ok = False
                status_msg = f"Last run was {hours_since_last_run:.1f} hours ago"
            elif self.failure_count >= 3:
                health_ok = False
                status_msg = f"Failed {self.failure_count} times"
            elif self.last_success_at and self.last_result:
                jobs_purged = self.last_result.get("jobs_purged", 0)
                recycle_purged = self.last_result.get("recycle_purged", 0)

                # Alert if nothing was purged in 7 days (likely misconfiguration)
                days_since_last_purge = (now - self.last_success_at).total_seconds() / 86400
                if jobs_purged == 0 and recycle_purged == 0 and days_since_last_purge > 7:
                    logger.warning(
                        "Data retention: No items purged in 7 days (may indicate misconfiguration)"
                    )

        return {
            "ok": health_ok,
            "status": status_msg,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "failure_count": self.failure_count,
            "total_purged": self.total_items_purged,
        }

    def _alert_critical_retention_failure(self) -> None:
        """Alert operators of critical retention failure."""
        from app.audit_logger import log_admin_action

        log_admin_action(
            actor="system",
            action="retention_critical_failure",
            resource="retention",
            details={
                "failure_count": self.failure_count,
                "message": "Data retention enforcement has failed multiple times",
            },
        )


# Global singleton
_retention_monitor = RetentionMonitor()


def get_retention_monitor() -> RetentionMonitor:
    """Get the global retention monitor."""
    return _retention_monitor


def record_retention_run(result: dict[str, int] | None = None, error: Exception | None = None) -> None:
    """Record a data retention enforcement run."""
    _retention_monitor.record_enforcement(result, error)
