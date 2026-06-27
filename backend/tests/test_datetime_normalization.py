"""Tests for the datetime normalization utility."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.utils.datetime_normalization import (
    WIRE_FORMAT,
    DatetimeParseError,
    format_datetime,
    normalize_to_utc,
    parse_datetime,
)


def test_format_aware_datetime():
    dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    assert format_datetime(dt) == "2026-01-15T12:00:00+00:00"


def test_format_naive_assumed_utc():
    dt = datetime(2026, 1, 15, 12, 0, 0)  # noqa: DTZ001 — intentionally testing naive→UTC conversion
    assert format_datetime(dt) == "2026-01-15T12:00:00+00:00"


def test_format_none_returns_empty():
    assert format_datetime(None) == ""


def test_format_converts_other_timezones_to_utc():
    dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC) + timedelta(hours=5)
    # +05:00 wallclock should still encode as UTC since astimezone
    # normalises to UTC.
    formatted = format_datetime(dt)
    assert "T17:00:00+00:00" in formatted


def test_parse_iso8601_with_offset():
    assert parse_datetime("2026-01-15T12:00:00+00:00") == datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def test_parse_iso8601_with_z_suffix():
    parsed = parse_datetime("2026-01-15T12:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_parse_legacy_sqlite_format():
    parsed = parse_datetime("2026-01-15 12:00:00")
    assert parsed == datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def test_parse_iso8601_with_subseconds():
    parsed = parse_datetime("2026-01-15T12:00:00.500000+00:00")
    assert parsed is not None
    assert parsed.microsecond == 500000


def test_parse_empty_returns_none():
    assert parse_datetime("") is None
    assert parse_datetime(None) is None


def test_parse_invalid_raises():
    with pytest.raises(DatetimeParseError):
        parse_datetime("not-a-timestamp")


def test_round_trip():
    original = datetime(2026, 6, 27, 11, 30, 0, tzinfo=UTC)
    as_string = format_datetime(original)
    assert parse_datetime(as_string) == original


def test_wire_format_constant():
    assert WIRE_FORMAT == "%Y-%m-%dT%H:%M:%S+00:00"


def test_normalize_none_returns_none():
    assert normalize_to_utc(None) is None


def test_normalize_naive_to_utc():
    dt = datetime(2026, 1, 15, 12, 0, 0)  # noqa: DTZ001 — intentionally testing naive->UTC conversion
    result = normalize_to_utc(dt)
    assert result is not None
    assert result.tzinfo == UTC
    assert result.utcoffset() == timedelta(0)


def test_normalize_aware_to_utc_unchanged():
    dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    assert normalize_to_utc(dt) == dt
