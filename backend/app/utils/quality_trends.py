"""Quality-trend tracking: in-memory, bounded time-series of extraction quality scores.

Keyed by ``(domain, schema_hash)`` so the same source can be tracked across
jobs.  Thread-safe via a reentrant lock.  FIFO eviction when per-key
deque exceeds ``max_samples``.

Public API:
    - ``get_trend_store()`` — return the process-wide singleton.
    - ``reset_default_store()`` — clear it (for tests).
    - ``configure_default_store(store)`` — replace it (for DI / tests).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import threading
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.models import SchemaField

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrendSample:
    """A single quality observation at a point in time."""

    timestamp: str  # ISO 8601 UTC
    score: float  # 0..1
    job_id: str
    field_scores: dict[str, float]  # field_name -> 0..1
    schema_hash: str


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class QualityTrendStore:
    """In-memory, thread-safe, bounded time-series of quality scores.

    Each entry is keyed by ``f"{domain}{delimiter}{schema_hash}"``.
    Values are :class:`deque` objects capped at ``max_samples``.
    """

    def __init__(
        self,
        *,
        max_samples: int | None = None,
        window_days: int | None = None,
        alert_threshold: float | None = None,
        page_limit: int | None = None,
        delimiter: str | None = None,
    ) -> None:
        self._max_samples = max_samples if max_samples is not None else settings.QUALITY_TREND_MAX_SAMPLES
        self._window_days = window_days if window_days is not None else settings.QUALITY_TREND_WINDOW_DAYS
        self._alert_threshold = alert_threshold if alert_threshold is not None else settings.QUALITY_TREND_ALERT_THRESHOLD
        self._page_limit = page_limit if page_limit is not None else settings.QUALITY_TREND_PAGE_LIMIT
        self._delimiter = delimiter if delimiter is not None else settings.QUALITY_TREND_DOMAIN_KEY_DELIMITER
        self._lock = threading.RLock()
        self._data: dict[str, deque[TrendSample]] = {}

    # ── Key helpers ──────────────────────────────────────────────────────

    @staticmethod
    def domain_for_url(url: str) -> str:
        """Extract the domain (netloc) from a URL, lowercased."""
        try:
            parsed = urlparse(url)
            return (parsed.netloc or "unknown").lower()
        except (ValueError, UnicodeDecodeError):
            return "unknown"

    @staticmethod
    def schema_hash(schema_fields: list[SchemaField]) -> str:
        """Stable, order-independent hash of a schema definition."""
        canonical = sorted([(f.name, f.field_type.value, f.required) for f in schema_fields])
        payload = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _key(self, domain: str, schema_hash: str) -> str:
        return f"{domain}{self._delimiter}{schema_hash}"

    # ── Write ───────────────────────────────────────────────────────────

    def record(
        self,
        *,
        domain: str,
        schema_hash: str,
        score: float,
        job_id: str,
        field_scores: dict[str, float] | None = None,
        timestamp: str | None = None,
    ) -> bool:
        """Append a new sample and return True if a quality regression is detected.

        A regression is flagged when the new score drops below
        ``alert_threshold`` OR the new score is more than 0.20 below the
        rolling average of the last 10 samples (even if above threshold).
        The first sample for a key always returns True if below threshold.
        """
        ts = timestamp or datetime.datetime.now(datetime.UTC).isoformat()
        sample = TrendSample(
            timestamp=ts,
            score=score,
            job_id=job_id,
            field_scores=field_scores or {},
            schema_hash=schema_hash,
        )

        with self._lock:
            key = self._key(domain, schema_hash)
            dq = self._data.get(key)
            if dq is None:
                dq = deque(maxlen=self._max_samples)
                self._data[key] = dq

            # Compute regression before appending the new sample
            regressed = False
            if len(dq) == 0:
                # First sample: alert only if below threshold
                if score < self._alert_threshold:
                    regressed = True
            else:
                recent = list(dq)[-10:]
                avg = sum(s.score for s in recent) / len(recent)
                if score < self._alert_threshold or score < (avg - 0.20):
                    regressed = True

            dq.append(sample)
            # Prune old samples outside the window
            self._prune_locked(key, dq)
            return regressed

    # ── Read ────────────────────────────────────────────────────────────

    def history(
        self,
        domain: str,
        schema_hash: str,
        *,
        limit: int | None = None,
        since_ts: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to *limit* samples for the key, most-recent first.

        If *since_ts* is given, only samples at or after that ISO
        timestamp are returned.
        """
        lim = limit or self._page_limit
        with self._lock:
            key = self._key(domain, schema_hash)
            dq = self._data.get(key)
            if not dq:
                return []
            items = list(dq)
        # Reverse for most-recent-first
        items.reverse()
        if since_ts:
            items = [s for s in items if s.timestamp >= since_ts]
        items = items[:lim]
        return [asdict(s) for s in items]

    def summary(self, domain: str, schema_hash: str) -> dict[str, Any]:
        """Compute aggregate stats for the given key."""
        with self._lock:
            key = self._key(domain, schema_hash)
            dq = self._data.get(key)
            if not dq:
                return {
                    "count": 0,
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "last_sample_ts": None,
                }
            scores = [s.score for s in dq]
        return {
            "count": len(scores),
            "mean": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "min": round(min(scores), 3) if scores else 0.0,
            "max": round(max(scores), 3) if scores else 0.0,
            "last_sample_ts": dq[-1].timestamp if dq else None,
        }

    def keys(self) -> list[tuple[str, str]]:
        """Return all (domain, schema_hash) pairs currently stored."""
        with self._lock:
            result = []
            for composite in self._data:
                parts = composite.split(self._delimiter, 1)
                if len(parts) == 2:
                    result.append((parts[0], parts[1]))
                else:
                    result.append((composite, ""))
            return result

    def reset(self) -> None:
        """Clear all stored data. Primarily for testing."""
        with self._lock:
            self._data.clear()

    # ── Internal ────────────────────────────────────────────────────────

    def _prune_locked(self, key: str, dq: deque[TrendSample]) -> None:
        """Remove samples older than the window (caller holds the lock)."""
        cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=self._window_days)).isoformat()
        while dq and dq[0].timestamp < cutoff:
            dq.popleft()


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, thread-safe)
# ---------------------------------------------------------------------------

_default_store: QualityTrendStore | None = None
_store_lock = threading.Lock()


def get_trend_store() -> QualityTrendStore:
    """Return the process-wide :class:`QualityTrendStore` singleton."""
    global _default_store
    if _default_store is None:
        with _store_lock:
            if _default_store is None:
                _default_store = QualityTrendStore()
    return _default_store


def reset_default_store() -> None:
    """Clear and recreate the process-wide singleton (for tests)."""
    global _default_store
    with _store_lock:
        if _default_store is not None:
            _default_store.reset()
        _default_store = None


def configure_default_store(store: QualityTrendStore) -> None:
    """Replace the process-wide singleton (for DI / tests)."""
    global _default_store
    with _store_lock:
        _default_store = store
