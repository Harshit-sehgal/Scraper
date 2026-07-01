"""Unit tests for the cron parser module.

Covers parse_expression, is_valid, matches, next_after, validate,
and all error paths — no third-party dependencies required.
"""

from __future__ import annotations

import datetime

import pytest
from app.utils.cron_parser import (
    CronError,
    is_valid,
    matches,
    next_after,
    parse_expression,
    validate,
)

# ─── parse_expression ──────────────────────────────────────────────────────


class TestParseExpression:
    """parse_expression returns five sets of allowed integer values."""

    def test_every_minute(self) -> None:
        minutes, hours, doms, months, dows = parse_expression("* * * * *")
        assert len(minutes) == 60
        assert len(hours) == 24
        assert len(doms) == 31
        assert len(months) == 12
        assert len(dows) == 7

    def test_specific_minute(self) -> None:
        minutes, hours, doms, months, dows = parse_expression("30 * * * *")
        assert minutes == {30}
        assert len(hours) == 24

    def test_comma_list(self) -> None:
        minutes, _, _, _, _ = parse_expression("0,15,30,45 * * * *")
        assert minutes == {0, 15, 30, 45}

    def test_step_every_five(self) -> None:
        minutes, _, _, _, _ = parse_expression("*/5 * * * *")
        assert minutes == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}

    def test_range(self) -> None:
        _, hours, _, _, _ = parse_expression("* 9-17 * * *")
        assert hours == {9, 10, 11, 12, 13, 14, 15, 16, 17}

    def test_range_with_step(self) -> None:
        _, hours, _, _, _ = parse_expression("* 9-17/2 * * *")
        assert hours == {9, 11, 13, 15, 17}

    def test_named_month(self) -> None:
        *_, months, _ = parse_expression("* * * JAN *")
        assert months == {1}

    def test_named_month_range(self) -> None:
        *_, months, _ = parse_expression("* * * MAR-JUN *")
        assert months == {3, 4, 5, 6}

    def test_named_dow(self) -> None:
        *_, dows = parse_expression("* * * * MON")
        assert dows == {0}  # Python weekday: Monday=0

    def test_named_dow_range(self) -> None:
        *_, dows = parse_expression("* * * * MON-FRI")
        assert dows == {0, 1, 2, 3, 4}

    def test_dow_sunday_is_6(self) -> None:
        """Cron Sunday (0) maps to Python weekday 6."""
        *_, dows = parse_expression("* * * * SUN")
        assert dows == {6}

    def test_aliased_dow_sat_and_sun(self) -> None:
        *_, dows = parse_expression("* * * * SAT,SUN")
        assert dows == {5, 6}

    def test_shortcut_hourly(self) -> None:
        parsed = parse_expression("@hourly")
        minutes, hours, *_ = parsed
        assert minutes == {0}
        assert len(hours) == 24

    def test_shortcut_daily(self) -> None:
        parsed = parse_expression("@daily")
        minutes, hours, *_ = parsed
        assert minutes == {0}
        assert hours == {0}

    def test_shortcut_weekly(self) -> None:
        *_, dows = parse_expression("@weekly")
        assert dows == {6}

    def test_shortcut_monthly(self) -> None:
        parsed = parse_expression("@monthly")
        minutes, hours, doms, months, dows = parsed
        assert minutes == {0}
        assert hours == {0}
        assert doms == {1}
        assert len(months) == 12
        assert len(dows) == 7

    def test_shortcut_yearly(self) -> None:
        minutes, hours, doms, months, dows = parse_expression("@yearly")
        assert minutes == {0}
        assert hours == {0}
        assert doms == {1}
        assert months == {1}

    def test_shortcut_annually(self) -> None:
        minutes, hours, doms, months, dows = parse_expression("@annually")
        assert minutes == {0}
        assert hours == {0}
        assert doms == {1}
        assert months == {1}


# ─── is_valid ──────────────────────────────────────────────────────────────


class TestIsValid:
    def test_valid_expression(self) -> None:
        assert is_valid("*/5 * * * *") is True

    def test_invalid_expression_wrong_field_count(self) -> None:
        assert is_valid("*/5 * * *") is False  # 4 fields

    def test_invalid_expression_empty_string(self) -> None:
        assert is_valid("") is False

    def test_invalid_expression_bad_token(self) -> None:
        assert is_valid("abc * * * *") is False

    def test_invalid_expression_out_of_range(self) -> None:
        assert is_valid("60 * * * *") is False

    def test_invalid_expression_negative_step(self) -> None:
        assert is_valid("*/0 * * * *") is False

    def test_shortcut_is_valid(self) -> None:
        assert is_valid("@daily") is True

    def test_duplicate_token(self) -> None:
        assert is_valid("0,0 * * * *") is False


# ─── validate ──────────────────────────────────────────────────────────────


class TestValidate:
    def test_valid_returns_none(self) -> None:
        # validate returns None on success; no exception is the pass condition
        validate("0 9 * * 1-5")

    def test_invalid_raises(self) -> None:
        with pytest.raises(CronError, match="cron expression must have 5 fields"):
            validate("0 9 * *")

    def test_empty_raises(self) -> None:
        with pytest.raises(CronError, match="cron expression is empty"):
            validate("")


# ─── error paths ──────────────────────────────────────────────────────────


class TestParseExpressionErrors:
    def test_empty_string(self) -> None:
        with pytest.raises(CronError, match="cron expression is empty"):
            parse_expression("")

    def test_none_expression(self) -> None:
        with pytest.raises(CronError, match="cron expression is empty"):
            parse_expression(None)  # type: ignore[arg-type]

    def test_too_few_fields(self) -> None:
        with pytest.raises(CronError, match="cron expression must have 5 fields"):
            parse_expression("0 9 * *")

    def test_too_many_fields(self) -> None:
        with pytest.raises(CronError, match="cron expression must have 5 fields"):
            parse_expression("0 9 * * * extra")

    def test_invalid_minute_value(self) -> None:
        with pytest.raises(CronError, match="out of range"):
            parse_expression("60 * * * *")

    def test_invalid_hour_value(self) -> None:
        with pytest.raises(CronError, match="out of range"):
            parse_expression("* 24 * * *")

    def test_invalid_dom_value(self) -> None:
        with pytest.raises(CronError, match="out of range"):
            parse_expression("* * 32 * *")

    def test_invalid_month_value(self) -> None:
        with pytest.raises(CronError, match="out of range"):
            parse_expression("* * * 13 *")

    def test_invalid_dow_value(self) -> None:
        with pytest.raises(CronError, match="out of range"):
            parse_expression("* * * * 7")

    def test_non_numeric_token(self) -> None:
        with pytest.raises(CronError, match="invalid cron value"):
            parse_expression("abc * * * *")

    def test_empty_field(self) -> None:
        """A comma-only field raises 'empty cron field' because all tokens are empty."""
        with pytest.raises(CronError, match="empty cron field"):
            parse_expression("* * , * *")

    def test_malformed_range(self) -> None:
        with pytest.raises(CronError, match="malformed range"):
            parse_expression("* * * 1- *")

    def test_zero_step(self) -> None:
        with pytest.raises(CronError, match="step must be positive"):
            parse_expression("*/0 * * * *")

    def test_negative_step(self) -> None:
        with pytest.raises(CronError, match="step must be positive"):
            parse_expression("*/-5 * * * *")


# ─── matches ───────────────────────────────────────────────────────────────


class TestMatches:
    def test_exact_match(self) -> None:
        dt = datetime.datetime(2026, 6, 15, 9, 30, tzinfo=datetime.UTC)
        assert matches(dt, "30 9 * * *") is True

    def test_minute_mismatch(self) -> None:
        dt = datetime.datetime(2026, 6, 15, 9, 31, tzinfo=datetime.UTC)
        assert matches(dt, "30 9 * * *") is False

    def test_hour_mismatch(self) -> None:
        dt = datetime.datetime(2026, 6, 15, 10, 30, tzinfo=datetime.UTC)
        assert matches(dt, "30 9 * * *") is False

    def test_month_mismatch(self) -> None:
        dt = datetime.datetime(2026, 7, 1, 0, 0, tzinfo=datetime.UTC)
        assert matches(dt, "0 0 1 * *") is True  # July 1st matches '1st of any month'

    def test_day_of_week_match(self) -> None:
        # 2026-06-15 is a Monday
        dt = datetime.datetime(2026, 6, 15, 9, 0, tzinfo=datetime.UTC)
        assert matches(dt, "0 9 * * 1") is True  # Monday

    def test_day_of_week_mismatch(self) -> None:
        # 2026-06-15 is a Monday
        dt = datetime.datetime(2026, 6, 15, 9, 0, tzinfo=datetime.UTC)
        assert matches(dt, "0 9 * * 0") is False  # Sunday

    def test_wildcard_matches_always(self) -> None:
        dt = datetime.datetime(2026, 6, 15, 14, 22, tzinfo=datetime.UTC)
        assert matches(dt, "* * * * *") is True

    def test_naive_datetime_treated_as_utc(self) -> None:
        dt = datetime.datetime(2026, 6, 15, 14, 22)  # noqa: DTZ001
        assert matches(dt, "22 14 * * *") is True


# ─── next_after ────────────────────────────────────────────────────────────


class TestNextAfter:
    def test_every_5_minutes(self) -> None:
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        result = next_after(base, "*/5 * * * *")
        assert result == datetime.datetime(2026, 1, 1, 0, 5, tzinfo=datetime.UTC)

    def test_weekday_9am(self) -> None:
        # 2026-01-01 is a Thursday
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 9 * * 1-5")
        assert result == datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)

    def test_weekday_from_weekend(self) -> None:
        # 2026-01-03 is a Saturday
        base = datetime.datetime(2026, 1, 3, 12, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 9 * * 1-5")
        # Next weekday is Monday 2026-01-05
        assert result == datetime.datetime(2026, 1, 5, 9, 0, tzinfo=datetime.UTC)

    def test_first_of_month(self) -> None:
        base = datetime.datetime(2026, 1, 15, 12, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 0 1 * *")
        assert result == datetime.datetime(2026, 2, 1, 0, 0, tzinfo=datetime.UTC)

    def test_specific_date(self) -> None:
        base = datetime.datetime(2026, 7, 1, 8, 0, tzinfo=datetime.UTC)
        result = next_after(base, "30 9 15 * *")
        assert result == datetime.datetime(2026, 7, 15, 9, 30, tzinfo=datetime.UTC)

    def test_cross_year_boundary(self) -> None:
        base = datetime.datetime(2026, 12, 31, 23, 30, tzinfo=datetime.UTC)
        result = next_after(base, "0 0 1 1 *")
        assert result == datetime.datetime(2027, 1, 1, 0, 0, tzinfo=datetime.UTC)

    def test_exact_match_returns_next(self) -> None:
        """next_after returns the *next* occurrence strictly after base."""
        base = datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 9 * * *")
        assert result == datetime.datetime(2026, 1, 2, 9, 0, tzinfo=datetime.UTC)

    def test_hourly_shortcut(self) -> None:
        base = datetime.datetime(2026, 1, 1, 8, 15, tzinfo=datetime.UTC)
        result = next_after(base, "@hourly")
        assert result.minute == 0
        assert result.hour == 9
        assert result.day == 1

    def test_daily_shortcut(self) -> None:
        base = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC)
        result = next_after(base, "@daily")
        assert result == datetime.datetime(2026, 1, 2, 0, 0, tzinfo=datetime.UTC)

    def test_now_parameter_overrides_base(self) -> None:
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        now = datetime.datetime(2026, 1, 1, 0, 30, tzinfo=datetime.UTC)
        result = next_after(base, "*/5 * * * *", now=now)
        assert result == datetime.datetime(2026, 1, 1, 0, 35, tzinfo=datetime.UTC)

    def test_naive_datetime(self) -> None:
        """Naive datetimes are treated as UTC."""
        base = datetime.datetime(2026, 1, 1, 0, 0)  # noqa: DTZ001
        result = next_after(base, "0 9 * * *")
        assert result == datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)

    def test_dom_only_restriction(self) -> None:
        """0 0 15 * * matches only the 15th of any month."""
        base = datetime.datetime(2026, 1, 14, 12, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 0 15 * *")
        assert result == datetime.datetime(2026, 1, 15, 0, 0, tzinfo=datetime.UTC)
        # The 16th should NOT match
        next_after_base = datetime.datetime(2026, 1, 15, 12, 0, tzinfo=datetime.UTC)
        result2 = next_after(next_after_base, "0 0 15 * *")
        assert result2 == datetime.datetime(2026, 2, 15, 0, 0, tzinfo=datetime.UTC)

    def test_dow_only_restriction(self) -> None:
        """0 0 * * 0 matches only Sundays."""
        # 2026-01-04 is a Sunday
        base = datetime.datetime(2026, 1, 3, 12, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 0 * * 0")
        assert result == datetime.datetime(2026, 1, 4, 0, 0, tzinfo=datetime.UTC)

    def test_both_dom_and_dow_restricted(self) -> None:
        """When both are restricted, the AND interpretation applies."""
        # Match 15th AND Sunday — 2026-02-15 is a Sunday? Let's check.
        # 2026-02-15 is a Sunday (Feb 1 2026 is Sunday)
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 0 15 * 0")
        # 2026-02-15 is a Sunday
        assert result == datetime.datetime(2026, 2, 15, 0, 0, tzinfo=datetime.UTC)

    def test_sun_to_sat_dow_wrap(self) -> None:
        """Range SAT-SUN (6-0) should wrap around in cron convention."""
        *_, dows = parse_expression("* * * * 6-0")
        assert dows == {5, 6}

    def test_quarter_hourly(self) -> None:
        base = datetime.datetime(2026, 1, 1, 0, 10, tzinfo=datetime.UTC)
        result = next_after(base, "*/15 * * * *")
        assert result == datetime.datetime(2026, 1, 1, 0, 15, tzinfo=datetime.UTC)

    def test_twice_daily(self) -> None:
        base = datetime.datetime(2026, 1, 1, 6, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 9,21 * * *")
        assert result == datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)

    def test_every_2_hours(self) -> None:
        base = datetime.datetime(2026, 1, 1, 1, 0, tzinfo=datetime.UTC)
        result = next_after(base, "0 */2 * * *")
        assert result.hour == 2

    def test_no_match_within_horizon_raises(self) -> None:
        """A pattern that can never match should raise CronError."""
        base = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC)
        # 31st of February never exists
        with pytest.raises(CronError, match="No scheduled time found"):
            next_after(base, "0 0 31 2 *")
