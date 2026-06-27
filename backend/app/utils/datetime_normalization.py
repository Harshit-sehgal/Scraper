"""Datetime normalisation utility — enforce one wire-format across backends.

The SQLite and Postgres backends historically produced subtly different
datetime strings:

* SQLite stored ``"%Y-%m-%d %H:%M:%S"`` (space-separated, no offset, naive UTC)
* Postgres stored ISO 8601 with timezone (often ``"2026-01-15T12:00:00+00:00"``)

A workflow that compares timestamps across both back-ends can silently misorder
records because the same timestamp renders to two different strings. We
centralise the wire-format here so every backend now produces
``2026-01-15T12:00:00+00:00`` (ISO 8601 with explicit UTC offset).

The two public helpers are:

* :func:`format_datetime` — Python datetime → ISO 8601 UTC string
* :func:`parse_datetime` — any of the legacy formats → Python datetime

Callers should never write ``dt.strftime("%Y-%m-%d %H:%M:%S")`` directly;
instead import :func:`format_datetime`.  Callers should never write
``datetime.fromisoformat`` directly; instead they should use
:func:`parse_datetime` which tolerates the legacy SQLite format for
backwards-compatibility read paths.
"""

from __future__ import annotations

from datetime import UTC, datetime

# Wire format — UTC, ISO 8601, with `+00:00` offset, no sub-second.
# Kept as a module-level constant so callers / tests use the same
# string in assertions without reinventing the format string.
WIRE_FORMAT: str = "%Y-%m-%dT%H:%M:%S+00:00"

# Accepted input formats (most-recent-first).  We accept the legacy
# SQLite ``"%Y-%m-%d %H:%M:%S"`` format so older rows still parse.
_LEGACY_INPUT_FORMATS: tuple[str, ...] = (
    WIRE_FORMAT,
    "%Y-%m-%dT%H:%M:%S.%f+00:00",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
)


class DatetimeParseError(ValueError):
    """Raised when a string does not match any known datetime wire format."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"Could not parse datetime string: {value!r}")


def format_datetime(dt: datetime | None) -> str:
    """Return the canonical ISO 8601 UTC representation of ``dt``.

    Naive datetimes are assumed to be UTC.  Aware datetimes are
    converted to UTC.  ``None`` returns ``""`` so callers can
    cleanly pass through ``job.get("created_at")`` without explicit
    None handling.
    """
    if dt is None:
        return ""
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.strftime(WIRE_FORMAT)


def parse_datetime(value: str | None) -> datetime | None:
    """Parse ``value`` into a UTC-aware datetime.

    Tries each format in :data:`_LEGACY_INPUT_FORMATS` in order;
    raises :class:`DatetimeParseError` when no format matches.
    Returns ``None`` when ``value`` is ``None`` or the empty string,
    so callers can chain without explicit None handling.
    """
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    # 1. Fast path: ISO 8601 with offset (and dateutil-style "Z").
    try:
        if stripped.endswith("Z"):
            stripped = stripped[:-1] + "+00:00"
        parsed = datetime.fromisoformat(stripped)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        pass
    # 2. Legacy formats.
    for fmt in _LEGACY_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(stripped, fmt)  # noqa: DTZ007 — timezone set on next line
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    raise DatetimeParseError(value)


def normalize_to_utc(dt: datetime | None) -> datetime | None:
    """Return ``dt`` expressed in UTC; ``None`` passthroughs."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
