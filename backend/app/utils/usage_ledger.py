"""Usage ledger and quota system for billing.

Tracks usage events, enforces quotas atomically, and can persist usage
events/quotas to SQLite for billing-ready metering.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class UsageType(Enum):
    """Types of usage that can be tracked."""

    JOB_CREATED = "job_created"
    JOB_COMPLETED = "job_completed"
    PAGE_FETCHED = "page_fetched"
    BROWSER_MINUTE = "browser_minute"
    SCHEDULED_JOB = "scheduled_job"
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
    org_id: str = ""
    project_id: str = ""
    api_key_id: str = ""
    period_start: datetime | None = None
    period_end: datetime | None = None
    idempotency_key: str = ""


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
    org_id: str = ""
    project_id: str = ""
    api_key_id: str = ""
    period_start: datetime | None = None
    period_end: datetime | None = None


class UsageLedger:
    """Tracks API usage for billing and quota enforcement."""

    def __init__(self, storage_path: str | Path | None = None):
        self._records: list[UsageRecord] = []
        self._quotas: dict[str, Quota] = {}
        self._idempotency: dict[str, UsageRecord] = {}
        self._lock = threading.RLock()
        self._storage_path = Path(storage_path) if storage_path is not None else None
        if self._storage_path is not None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_storage()
            self._load_storage()

    def _quota_key(self, user_id: str, usage_type: UsageType) -> str:
        return f"{user_id}:{usage_type.value}"

    def _idempotency_key(self, user_id: str, usage_type: UsageType, idempotency_key: str) -> str:
        return f"{user_id}:{usage_type.value}:{idempotency_key}"

    def _connect(self) -> sqlite3.Connection:
        if self._storage_path is None:
            msg = "Usage ledger storage is not configured"
            raise RuntimeError(msg)
        conn = sqlite3.connect(str(self._storage_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_storage(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_quotas (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    api_key_id TEXT NOT NULL DEFAULT '',
                    usage_type TEXT NOT NULL,
                    limit_value INTEGER NOT NULL,
                    period TEXT NOT NULL,
                    current_usage INTEGER NOT NULL DEFAULT 0,
                    period_start TEXT DEFAULT NULL,
                    period_end TEXT DEFAULT NULL,
                    reset_date TEXT DEFAULT NULL,
                    UNIQUE(user_id, usage_type)
                )
                """,
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    api_key_id TEXT NOT NULL DEFAULT '',
                    usage_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    timestamp TEXT NOT NULL,
                    period_start TEXT DEFAULT NULL,
                    period_end TEXT DEFAULT NULL,
                    idempotency_key TEXT NOT NULL DEFAULT ''
                )
                """,
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_user_type ON usage_events(user_id, usage_type)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_events_idempotency "
                "ON usage_events(user_id, usage_type, idempotency_key) WHERE idempotency_key != ''",
            )

    def _load_storage(self) -> None:
        with self._lock, self._connect() as conn:
            quotas: dict[str, Quota] = {}
            for row in conn.execute("SELECT * FROM usage_quotas").fetchall():
                quota = Quota(
                    id=str(row["id"]),
                    user_id=str(row["user_id"]),
                    org_id=str(row["org_id"] or ""),
                    project_id=str(row["project_id"] or ""),
                    api_key_id=str(row["api_key_id"] or ""),
                    usage_type=UsageType(str(row["usage_type"])),
                    limit=int(row["limit_value"]),
                    period=QuotaPeriod(str(row["period"])),
                    current_usage=int(row["current_usage"] or 0),
                    period_start=_parse_dt(row["period_start"]),
                    period_end=_parse_dt(row["period_end"]),
                    reset_date=_parse_dt(row["reset_date"]),
                )
                quotas[self._quota_key(quota.user_id, quota.usage_type)] = quota

            records: list[UsageRecord] = []
            idempotency: dict[str, UsageRecord] = {}
            for row in conn.execute("SELECT * FROM usage_events ORDER BY timestamp ASC").fetchall():
                record = UsageRecord(
                    id=str(row["id"]),
                    user_id=str(row["user_id"]),
                    org_id=str(row["org_id"] or ""),
                    project_id=str(row["project_id"] or ""),
                    api_key_id=str(row["api_key_id"] or ""),
                    usage_type=UsageType(str(row["usage_type"])),
                    quantity=int(row["quantity"] or 0),
                    metadata=json.loads(row["metadata"] or "{}"),
                    timestamp=_parse_dt(row["timestamp"]) or datetime.now(UTC),
                    period_start=_parse_dt(row["period_start"]),
                    period_end=_parse_dt(row["period_end"]),
                    idempotency_key=str(row["idempotency_key"] or ""),
                )
                records.append(record)
                if record.idempotency_key:
                    idempotency[self._idempotency_key(record.user_id, record.usage_type, record.idempotency_key)] = record

            self._quotas = quotas
            self._records = records
            self._idempotency = idempotency

    def _persist_quota(self, conn: sqlite3.Connection, quota: Quota) -> None:
        conn.execute(
            """
            INSERT INTO usage_quotas (
                id, user_id, org_id, project_id, api_key_id, usage_type,
                limit_value, period, current_usage, period_start, period_end, reset_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, usage_type) DO UPDATE SET
                id=excluded.id,
                org_id=excluded.org_id,
                project_id=excluded.project_id,
                api_key_id=excluded.api_key_id,
                limit_value=excluded.limit_value,
                period=excluded.period,
                current_usage=excluded.current_usage,
                period_start=excluded.period_start,
                period_end=excluded.period_end,
                reset_date=excluded.reset_date
            """,
            (
                quota.id,
                quota.user_id,
                quota.org_id,
                quota.project_id,
                quota.api_key_id,
                quota.usage_type.value,
                quota.limit,
                quota.period.value,
                quota.current_usage,
                _format_dt(quota.period_start),
                _format_dt(quota.period_end),
                _format_dt(quota.reset_date),
            ),
        )

    def _persist_record(self, conn: sqlite3.Connection, record: UsageRecord) -> None:
        conn.execute(
            """
            INSERT INTO usage_events (
                id, user_id, org_id, project_id, api_key_id, usage_type,
                quantity, metadata, timestamp, period_start, period_end, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.user_id,
                record.org_id,
                record.project_id,
                record.api_key_id,
                record.usage_type.value,
                record.quantity,
                json.dumps(record.metadata, default=str, sort_keys=True),
                _format_dt(record.timestamp),
                _format_dt(record.period_start),
                _format_dt(record.period_end),
                record.idempotency_key,
            ),
        )

    def record_usage(
        self,
        user_id: str,
        usage_type: UsageType,
        quantity: int = 1,
        metadata: dict | None = None,
        *,
        idempotency_key: str = "",
        org_id: str = "",
        project_id: str = "",
        api_key_id: str = "",
    ) -> UsageRecord:
        """Record usage for a user and increment any matching quota."""
        if quantity < 0:
            msg = "usage quantity must be non-negative"
            raise ValueError(msg)

        with self._lock:
            if idempotency_key:
                existing = self._idempotency.get(self._idempotency_key(user_id, usage_type, idempotency_key))
                if existing is not None:
                    return existing

            quota_key = self._quota_key(user_id, usage_type)
            quota = self._quotas.get(quota_key)
            if quota is not None and quota.current_usage + quantity > quota.limit:
                msg = f"quota exceeded for {usage_type.value}: {quota.current_usage + quantity}/{quota.limit}"
                raise ValueError(msg)

            record = UsageRecord(
                user_id=user_id,
                usage_type=usage_type,
                quantity=quantity,
                metadata=metadata or {},
                org_id=org_id,
                project_id=project_id,
                api_key_id=api_key_id,
                idempotency_key=idempotency_key,
            )
            self._records.append(record)
            if idempotency_key:
                self._idempotency[self._idempotency_key(user_id, usage_type, idempotency_key)] = record
            if quota is not None:
                quota.current_usage += quantity

            if self._storage_path is not None:
                with self._connect() as conn:
                    self._persist_record(conn, record)
                    if quota is not None:
                        self._persist_quota(conn, quota)

            return record

    def get_usage(
        self,
        user_id: str,
        usage_type: UsageType | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[UsageRecord]:
        """Get usage records for a user."""
        with self._lock:
            records = [r for r in self._records if r.user_id == user_id]

            if usage_type:
                records = [r for r in records if r.usage_type == usage_type]

            if start_date:
                records = [r for r in records if r.timestamp >= start_date]

            if end_date:
                records = [r for r in records if r.timestamp <= end_date]

            return list(records)

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
        *,
        amount: int = 1,
    ) -> tuple[bool, Quota | None]:
        """Check if user has quota available for the requested amount."""
        with self._lock:
            quota = self._quotas.get(self._quota_key(user_id, usage_type))

            if not quota:
                return True, None

            return quota.current_usage + amount <= quota.limit, quota

    def set_quota(
        self,
        user_id: str,
        usage_type: UsageType,
        limit: int,
        period: QuotaPeriod = QuotaPeriod.MONTHLY,
        *,
        org_id: str = "",
        project_id: str = "",
        api_key_id: str = "",
    ) -> Quota:
        """Set quota for a user."""
        if limit < 0:
            msg = "quota limit must be non-negative"
            raise ValueError(msg)
        with self._lock:
            quota = Quota(
                user_id=user_id,
                usage_type=usage_type,
                limit=limit,
                period=period,
                org_id=org_id,
                project_id=project_id,
                api_key_id=api_key_id,
            )
            self._quotas[self._quota_key(user_id, usage_type)] = quota
            if self._storage_path is not None:
                with self._connect() as conn:
                    self._persist_quota(conn, quota)
            return quota

    def get_quota(
        self,
        user_id: str,
        usage_type: UsageType,
    ) -> Quota | None:
        """Get quota for a user."""
        with self._lock:
            return self._quotas.get(self._quota_key(user_id, usage_type))

    def reset_quotas(self, user_id: str | None = None) -> int:
        """Reset quotas for a user or all users."""
        with self._lock:
            reset_count = 0
            changed: list[Quota] = []
            for quota in list(self._quotas.values()):
                if user_id is None or quota.user_id == user_id:
                    quota.current_usage = 0
                    reset_count += 1
                    changed.append(quota)
            if self._storage_path is not None and changed:
                with self._connect() as conn:
                    for quota in changed:
                        self._persist_quota(conn, quota)
            return reset_count


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


# Global ledger instance
usage_ledger = UsageLedger()


def get_usage_ledger() -> UsageLedger:
    """Get the global usage ledger."""
    return usage_ledger


def reset_usage_ledger(user_id: str | None = None) -> int:
    """Reset the global usage ledger for a specific user or all users.

    Primarily used by test fixtures to ensure quota state does not leak
    between tests. Returns the number of quotas reset.
    """
    return usage_ledger.reset_quotas(user_id=user_id)
