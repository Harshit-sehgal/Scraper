"""Shared UTC timestamp helper.

Centralises the ``_now_iso()`` / ``_utc_now_iso()`` one-liner that was
duplicated across 8+ modules so timezone formatting lives in one place.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as ISO-8601."""
    return datetime.now(UTC).isoformat()
