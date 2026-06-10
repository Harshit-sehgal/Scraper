"""Usage ledger and quota system for billing.

Tracks API usage, enforces quotas, and provides billing-ready data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class UsageType(Enum):
    """Types of usage that can be tracked."""

    JOB_CREATED = "job_created"
    JOB_COMPLETED = "job_completed"
    PAGE_FETCHED = "page_fetched"
    AI_STRUCTURING = "ai_structuring"
    EXPORT_GENERATED = "export_generated"
    API_REQUEST = "api_request"


class QuotaPeriod(Enum):
    """Quota periods."""

    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass
class UsageRecord:
    """Single usage record."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    usage_type: UsageType = UsageType.API_REQUEST
    quantity: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Quota:
    """User quota definition."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    usage_type: UsageType = UsageType.API_REQUEST
    limit: int = 1000
    period: QuotaPeriod = QuotaPeriod.MONTHLY
    current_usage: int = 0
    reset_date: datetime | None = None


class UsageLedger:
    """Tracks API usage for billing and quota enforcement."""

    def __init__(self):
        self._records: list[UsageRecord] = []
        self._quotas: dict[str, Quota] = {}

    def record_usage(
        self,
        user_id: str,
        usage_type: UsageType,
        quantity: int = 1,
        metadata: dict | None = None,
    ) -> UsageRecord:
        """Record usage for a user."""
        record = UsageRecord(
            user_id=user_id,
            usage_type=usage_type,
            quantity=quantity,
            metadata=metadata or {},
        )
        self._records.append(record)
        return record

    def get_usage(
        self,
        user_id: str,
        usage_type: UsageType | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[UsageRecord]:
        """Get usage records for a user."""
        records = [r for r in self._records if r.user_id == user_id]

        if usage_type:
            records = [r for r in records if r.usage_type == usage_type]

        if start_date:
            records = [r for r in records if r.timestamp >= start_date]

        if end_date:
            records = [r for r in records if r.timestamp <= end_date]

        return records

    def get_usage_summary(
        self,
        user_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get usage summary for a user."""
        records = self.get_usage(user_id, start_date=start_date, end_date=end_date)

        summary = {}
        for usage_type in UsageType:
            type_records = [r for r in records if r.usage_type == usage_type]
            total_quantity = sum(r.quantity for r in type_records)
            summary[usage_type.value] = {
                "count": len(type_records),
                "total_quantity": total_quantity,
            }

        return {
            "user_id": user_id,
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "usage": summary,
        }

    def check_quota(
        self,
        user_id: str,
        usage_type: UsageType,
    ) -> tuple[bool, Quota | None]:
        """Check if user has quota available."""
        quota_key = f"{user_id}:{usage_type.value}"
        quota = self._quotas.get(quota_key)

        if not quota:
            return True, None

        return quota.current_usage < quota.limit, quota

    def set_quota(
        self,
        user_id: str,
        usage_type: UsageType,
        limit: int,
        period: QuotaPeriod = QuotaPeriod.MONTHLY,
    ) -> Quota:
        """Set quota for a user."""
        quota_key = f"{user_id}:{usage_type.value}"
        quota = Quota(
            user_id=user_id,
            usage_type=usage_type,
            limit=limit,
            period=period,
        )
        self._quotas[quota_key] = quota
        return quota

    def get_quota(
        self,
        user_id: str,
        usage_type: UsageType,
    ) -> Quota | None:
        """Get quota for a user."""
        quota_key = f"{user_id}:{usage_type.value}"
        return self._quotas.get(quota_key)

    def reset_quotas(self, user_id: str | None = None) -> int:
        """Reset quotas for a user or all users."""
        reset_count = 0
        for key, quota in list(self._quotas.items()):
            if user_id is None or quota.user_id == user_id:
                quota.current_usage = 0
                reset_count += 1
        return reset_count


# Global ledger instance
usage_ledger = UsageLedger()


def get_usage_ledger() -> UsageLedger:
    """Get the global usage ledger."""
    return usage_ledger
