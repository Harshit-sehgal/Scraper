"""Price history tracking — stores price snapshots and detects changes.

For recurring jobs on the same product URL, tracks price changes over time
and exposes trends, drops, and volatility metrics.

Uses an in-memory store that is scoped to the current process lifetime.
The store is keyed by URL and optionally by field name so that multiple
price-like fields on the same page (e.g., "price", "original_price",
"shipping_price") are tracked independently.

No remote calls, no database persistence — designed for lightweight
in-process tracking. Callers can persist the snapshot dict externally
if needed.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any


def _parse_price(value: object) -> float | None:
    """Parse a price value from a string or number.

    Handles common formats:
    - "$29.99" (US/UK decimal dot)
    - "29,99 €" (European decimal comma)
    - "1,234.56" (US thousands comma)
    - "1.234,56 €" (European thousands dot)
    - 29.99 (float)
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        # First pass: keep only digits, commas, dots
        numeric = re.sub(r"[^\d,.]", "", raw)
        if not numeric:
            return None

        # Detect European format: comma used as decimal separator.
        # European prices end with comma + 1-2 digits (e.g. "29,99" or "1.234,56").
        # US/UK prices use comma as thousands separator (e.g. "1,234.56").
        if re.search(r",\d{1,2}$", numeric):
            # European: comma is decimal, dots are thousands
            numeric = numeric.replace(".", "")  # remove thousands dots
            numeric = numeric.replace(",", ".")  # replace decimal comma with dot
        else:
            # US/UK: remove commas (thousands), keep dot as decimal
            numeric = numeric.replace(",", "")

        # Final cleanup: remove any remaining non-digit, non-dot characters
        # (handles trailing minus like "10,-" which becomes "10")
        final = re.sub(r"[^\d.]", "", numeric)
        return float(final) if final else None
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class PriceSnapshot:
    """A single price observation at a point in time."""

    price: float
    currency: str = ""
    timestamp: float = 0.0
    url: str = ""
    field_name: str = "price"

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "currency": self.currency,
            "timestamp": self.timestamp or time.time(),
            "url": self.url,
            "field_name": self.field_name,
        }


@dataclass
class PriceTrend:
    """Price movement analysis for a tracked field."""

    current: float | None = None
    previous: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    average_price: float | None = None
    change_amount: float | None = None
    change_pct: float | None = None
    direction: str = "stable"  # "up" | "down" | "stable" | "new"
    volatility: float = 0.0  # std-dev / mean
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "previous": self.previous,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "average_price": self.average_price,
            "change_amount": self.change_amount,
            "change_pct": self.change_pct,
            "direction": self.direction,
            "volatility": round(self.volatility, 4),
            "sample_count": self.sample_count,
        }


class PriceHistory:
    """Process-local price history store.

    Thread-safe for concurrent access. Stores snapshots indexed by
    ``(url, field_name)`` and keeps a bounded history (last 100 snapshots
    per key).

    Usage::

        history = PriceHistory()
        history.record("https://example.com/product/1", 29.99, currency="USD")
        trend = history.get_trend("https://example.com/product/1")
        all_snapshots = history.get_history("https://example.com/product/1")
    """

    def __init__(self, max_snapshots_per_key: int = 100) -> None:
        self._max = max_snapshots_per_key
        self._store: dict[tuple[str, str], list[PriceSnapshot]] = {}
        self._lock: Any = None  # lazy-import threading.Lock
        self._init_lock()

    def _init_lock(self) -> None:
        import threading

        self._lock = threading.Lock()

    def _key(self, url: str, field_name: str = "price") -> tuple[str, str]:
        return (url, field_name)

    def record(
        self,
        url: str,
        price: float | None,
        *,
        currency: str = "",
        field_name: str = "price",
        timestamp: float | None = None,
    ) -> PriceSnapshot | None:
        """Record a price observation.

        Returns the snapshot if a valid price was recorded, ``None`` if
        the price was ``None`` or unparseable.
        """
        if price is None:
            return None
        parsed = _parse_price(price)
        if parsed is None:
            return None
        snap = PriceSnapshot(
            price=parsed,
            currency=currency,
            timestamp=timestamp or time.time(),
            url=url,
            field_name=field_name,
        )
        with self._lock:
            key = self._key(url, field_name)
            chain = self._store.setdefault(key, [])
            chain.append(snap)
            # Keep bounded
            if len(chain) > self._max:
                self._store[key] = chain[-self._max :]
        return snap

    def record_from_record(
        self,
        url: str,
        record: dict[str, Any],
        *,
        price_fields: tuple[str, ...] = ("price", "total_price", "amount", "fare"),
        currency_field: str = "currency",
    ) -> list[PriceSnapshot]:
        """Record all prices found in an extraction record dict.

        Scans the record for known price-like field names and records
        each one independently.
        """
        snaps: list[PriceSnapshot] = []
        currency = str(record.get(currency_field, ""))
        for field in price_fields:
            raw = record.get(field)
            if raw is not None:
                snap = self.record(url, _parse_price(raw), currency=currency, field_name=field)
                if snap:
                    snaps.append(snap)
        return snaps

    def get_history(
        self,
        url: str,
        field_name: str = "price",
        *,
        limit: int = 0,
    ) -> list[PriceSnapshot]:
        """Return price snapshots for a URL, newest first.

        Args:
            url: The product URL.
            field_name: The price field name to query.
            limit: Maximum number of snapshots. 0 means all.

        Returns:
            List of snapshots sorted newest-first.
        """
        with self._lock:
            key = self._key(url, field_name)
            chain = list(self._store.get(key, []))
        chain.sort(key=lambda s: s.timestamp, reverse=True)
        if limit > 0:
            chain = chain[:limit]
        return chain

    def get_trend(
        self,
        url: str,
        field_name: str = "price",
    ) -> PriceTrend:
        """Compute price trend analysis for a tracked URL/field.

        Returns a ``PriceTrend`` with current, previous, min, max,
        average, change (amount and pct), direction, and volatility.
        Returns a zero-valued trend if no snapshots exist.
        """
        with self._lock:
            key = self._key(url, field_name)
            chain = list(self._store.get(key, []))
        if not chain:
            return PriceTrend(direction="new")

        prices = [s.price for s in chain]
        sorted_asc = sorted(prices)
        n = len(prices)
        mean = sum(prices) / n
        variance = sum((p - mean) ** 2 for p in prices) / n
        volatility = (variance**0.5) / mean if mean else 0.0

        latest = sorted(chain, key=lambda s: s.timestamp, reverse=True)
        current_price = latest[0].price
        previous_price = latest[1].price if len(latest) > 1 else None

        change_amount: float | None = None
        change_pct: float | None = None
        direction: str = "new"
        if previous_price is not None:
            change_amount = round(current_price - previous_price, 4)
            change_pct = round((change_amount / previous_price) * 100, 4) if previous_price else None
            if change_amount > 0:
                direction = "up"
            elif change_amount < 0:
                direction = "down"
            else:
                direction = "stable"

        return PriceTrend(
            current=current_price,
            previous=previous_price,
            min_price=sorted_asc[0],
            max_price=sorted_asc[-1],
            average_price=round(mean, 4),
            change_amount=change_amount,
            change_pct=change_pct,
            direction=direction,
            volatility=round(volatility, 4),
            sample_count=n,
        )

    def clear(self, url: str | None = None, field_name: str = "price") -> int:
        """Clear price history.

        Args:
            url: If given, clear only this URL. If ``None``, clear all.
            field_name: The price field name (only used when url is given).

        Returns:
            Number of entries removed.
        """
        with self._lock:
            if url is None:
                count = len(self._store)
                self._store.clear()
                return count
            key = self._key(url, field_name)
            chain = self._store.pop(key, [])
            return len(chain)

    def get_all_keys(self) -> list[tuple[str, str]]:
        """Return all tracked (url, field_name) keys."""
        with self._lock:
            return list(self._store.keys())


# Module-level singleton
_PRICE_HISTORY: PriceHistory | None = None
_PRICE_HISTORY_LOCK = threading.Lock()


def get_price_history() -> PriceHistory:
    """Get or create the process-wide price history store.

    Double-checked under :data:`_PRICE_HISTORY_LOCK` so concurrent first-callers
    do not both build a fresh ``PriceHistory`` and discard the other's
    accumulated in-memory state.
    """
    global _PRICE_HISTORY
    if _PRICE_HISTORY is not None:
        return _PRICE_HISTORY
    with _PRICE_HISTORY_LOCK:
        if _PRICE_HISTORY is None:
            _PRICE_HISTORY = PriceHistory()
        return _PRICE_HISTORY


def reset_price_history_for_testing() -> None:
    """Reset the singleton — for test teardown only."""
    global _PRICE_HISTORY
    _PRICE_HISTORY = None
