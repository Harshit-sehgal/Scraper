"""Minimal standard-cron (5-field) parser.

Supports the subset of POSIX cron syntax we actually need:

* Field 0: minute (0-59)
* Field 1: hour (0-23)
* Field 2: day-of-month (1-31)
* Field 3: month (1-12)
* Field 4: day-of-week (0-6, 0 = Sunday)

Each field accepts:

* ``*`` — every step in the field's range
* ``*/N`` — every N steps (e.g. ``*/15`` for every 15 minutes)
* ``A,B,C`` — discrete values
* ``A-B`` — inclusive ranges
* ``A-B/N`` — ranges with step
* plain integers / names (``JAN``, ``MON``, ``SUN``)

The parser also accepts an optional ``@`` shortcut (e.g. ``@hourly``,
``@daily``, ``@weekly``, ``@monthly``) so that existing enum-style
frequencies remain usable through the same API.

``next_after(base, now=None)`` returns the next UTC datetime strictly after
``base`` (or after ``now`` if supplied) that matches the cron expression.

This module has no third-party dependencies by design — the platform's
deployment surface is tight enough that adding ``croniter`` for a
five-field subset has not been worth the cost.
"""

import datetime
import re
from collections.abc import Sequence

# ── Field metadata ────────────────────────────────────────────────────

_FIELD_RANGES: tuple[tuple[int, int], ...] = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 6),  # day of week
)

_MONTH_NAMES: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_DOW_NAMES: dict[str, int] = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}

# Cron convention: 0=Sunday, 1=Monday, …, 6=Saturday
# Python convention: 0=Monday, …, 6=Sunday
_CRON_DOW_TO_PYTHON: dict[int, int] = {
    0: 6,  # Sunday
    1: 0,  # Monday
    2: 1,  # Tuesday
    3: 2,  # Wednesday
    4: 3,  # Thursday
    5: 4,  # Friday
    6: 5,  # Saturday
}

_AT_SHORTCUTS: dict[str, str] = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}


class CronError(ValueError):
    """Raised when a cron expression cannot be parsed."""


# ── Low-level field expansion ────────────────────────────────────────


_EMPTY_TOKEN = "empty cron token"  # nosec B105
_INVALID_STEP = "step must be positive: {step}"
_INVALID_VALUE_TPL = "invalid cron value: {token}"
_OUT_OF_RANGE_TPL = "value {value} out of range {lo}-{hi}"
_MALFORMED_RANGE_TPL = "malformed range: {token}"
_NO_NEXT_RUN_TPL = "no scheduled time found within 8 years for cron expression: {expression}"
_EMPTY_FIELD_TPL = "empty cron field at position {idx}"
_DUPLICATE_TOKEN_TPL = "duplicate token {token!r} in cron field {idx}"  # nosec B105
_EXPR_EMPTY = "cron expression is empty"
_FIELDS_REQUIRED_TPL = "cron expression must have 5 fields (minute hour dom month dow), got {n}"


def _expand_token(token: str, lo: int, hi: int, names: dict[str, int] | None = None) -> set[int]:
    """Expand a single comma-free token (``*``, ``*/N``, ``A-B``/``A-B/N``, ``V``)."""
    token = token.strip().upper()
    if not token:
        raise CronError(_EMPTY_TOKEN)

    # Replace known names with numbers; tolerate them only in expected fields.
    if names and token in names:
        return {names[token]}

    # Step syntax: ``*/N`` or ``A-B/N``
    # Bail early if token ends with `/` but no step value follows.
    if token.endswith("/"):
        raise CronError(_INVALID_VALUE_TPL.format(token=token))
    step_match = re.match(r"^(.+)/(\d+)$", token)
    if step_match:
        range_part, step_str = step_match.group(1), step_match.group(2)
        step = int(step_str)
        if step <= 0:
            raise CronError(_INVALID_STEP.format(step=step))
        if range_part == "*":
            return set(range(lo, hi + 1, step))
        # Range form: e.g. 1-10/2
        rng = _parse_range(range_part, lo, hi, names)
        if not rng:
            return set()
        return {v for v in range(min(rng), max(rng) + 1, step) if v in rng}

    if token == "*":  # nosec B105
        return set(range(lo, hi + 1))

    # Plain range: ``A-B``
    if "-" in token:
        return _parse_range(token, lo, hi, names)

    # Plain single value
    try:
        value = int(token)
    except ValueError as exc:
        raise CronError(_INVALID_VALUE_TPL.format(token=token)) from exc
    if value < lo or value > hi:
        msg = _OUT_OF_RANGE_TPL.format(value=value, lo=lo, hi=hi)
        raise CronError(msg)
    return {value}


def _parse_range(token: str, lo: int, hi: int, names: dict[str, int] | None) -> set[int]:
    parts = token.split("-")
    if len(parts) != 2:
        raise CronError(_MALFORMED_RANGE_TPL.format(token=token))
    a_raw, b_raw = parts[0], parts[1]
    if not a_raw or not b_raw:
        raise CronError(_MALFORMED_RANGE_TPL.format(token=token))
    try:
        a = names[a_raw.upper()] if names and a_raw.upper() in names else int(a_raw)
        b = names[b_raw.upper()] if names and b_raw.upper() in names else int(b_raw)
    except ValueError as exc:
        raise CronError(_MALFORMED_RANGE_TPL.format(token=token)) from exc
    if a > b:
        # Wrap-around like SAT(6)-SUN(0); store both endpoints and expand modulo 7.
        a_norm = a % (hi + 1)
        b_norm = b % (hi + 1)
        vals = set(range(a_norm, hi + 1)) | set(range(b_norm + 1))
        return {v for v in vals if lo <= v <= hi}
    if a < lo or b > hi:
        msg = _OUT_OF_RANGE_TPL.format(value=f"{a}-{b}", lo=lo, hi=hi)
        raise CronError(msg)
    return set(range(a, b + 1))


def _expand_field(field: str, idx: int) -> set[int]:
    lo, hi = _FIELD_RANGES[idx]
    names = _MONTH_NAMES if idx == 3 else (_DOW_NAMES if idx == 4 else None)
    tokens = [t.strip() for t in field.split(",") if t.strip()]
    if not tokens:
        raise CronError(_EMPTY_FIELD_TPL.format(idx=idx))
    values: set[int] = set()
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            raise CronError(_DUPLICATE_TOKEN_TPL.format(token=token, idx=idx))
        seen.add(token)
        values.update(_expand_token(token, lo, hi, names))
    return values


# ── Public API ───────────────────────────────────────────────────────


def parse_expression(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Parse a cron expression into five sets of allowed integers.

    Raises:
        CronError: if the expression is not a valid cron string.
    """
    raw = (expression or "").strip()
    if not raw:
        raise CronError(_EXPR_EMPTY)
    if raw in _AT_SHORTCUTS:
        raw = _AT_SHORTCUTS[raw]
    fields = raw.split()
    if len(fields) != 5:
        raise CronError(_FIELDS_REQUIRED_TPL.format(n=len(fields)))
    cron_dow = _expand_field(fields[4], 4)
    python_dow = {_CRON_DOW_TO_PYTHON.get(d, d) for d in cron_dow}
    return (
        _expand_field(fields[0], 0),  # minute
        _expand_field(fields[1], 1),  # hour
        _expand_field(fields[2], 2),  # day of month
        _expand_field(fields[3], 3),  # month
        python_dow,  # day of week (converted to Python weekday)
    )


def validate(expression: str) -> None:
    """Validate a cron expression. Raises CronError on failure, returns None on success."""
    parse_expression(expression)


def next_after(
    base: datetime.datetime,
    expression: str,
    *,
    now: datetime.datetime | None = None,
) -> datetime.datetime:
    """Return the first datetime strictly after ``base`` that matches ``expression``.

    Naive datetimes are treated as UTC.  The search advances minute-by-minute
    up to 8 years (~4 M iterations); if no match is found in that window
    the function raises CronError so callers see a clear failure rather
    than an infinite loop.
    """
    parsed = parse_expression(expression)
    minutes, hours, doms, months, dows = parsed

    # POSIX cron: when both day-of-month and day-of-week are restricted
    # (i.e. non-``*``), the AND interpretation applies.  When one of them
    # is ``*``, the other field alone decides.  We follow the "broader
    # field is the gate" convention so that ``0 0 1 * *`` matches only
    # the 1st of the month, not (unrestricted dow) every day too.
    full_dom = set(range(_FIELD_RANGES[2][0], _FIELD_RANGES[2][1] + 1))
    full_dow = set(range(_FIELD_RANGES[4][0], _FIELD_RANGES[4][1] + 1))
    dom_is_restricted = doms != full_dom
    dow_is_restricted = dows != full_dow

    if dom_is_restricted and dow_is_restricted:

        def _day_matches(day: int, weekday: int) -> bool:
            return day in doms and weekday in dows
    elif dom_is_restricted:

        def _day_matches(day: int, weekday: int) -> bool:
            return day in doms
    elif dow_is_restricted:

        def _day_matches(day: int, weekday: int) -> bool:
            return weekday in dows
    else:

        def _day_matches(day: int, weekday: int) -> bool:
            return True

    def _aware(dt: datetime.datetime) -> datetime.datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.UTC)
        return dt.astimezone(datetime.UTC)

    base = _aware(base)
    horizon_exclusive = base + datetime.timedelta(days=8 * 366)
    cursor = _aware(now) if now is not None else base

    last_minute: tuple[int, int, int, int, int] | None = None

    safety = 0
    while True:
        safety += 1
        msg = _NO_NEXT_RUN_TPL.format(expression=expression)
        if safety > 4_500_000:  # 8 years of minutes + slack
            raise CronError(msg)
        # Walk to the next minute
        cursor = cursor.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        if cursor >= horizon_exclusive:
            raise CronError(msg)
        # Avoid repeating work for the same minute key
        key = (cursor.year, cursor.month, cursor.day, cursor.hour, cursor.minute)
        if key == last_minute:
            continue
        last_minute = key
        # Quick prune
        if cursor.month not in months:
            continue
        if not _day_matches(cursor.day, cursor.weekday()):
            continue
        if cursor.hour not in hours:
            continue
        if cursor.minute not in minutes:
            continue
        return cursor


def is_valid(expression: str) -> bool:
    """True if ``expression`` parses; False otherwise."""
    try:
        validate(expression)
        return True
    except (CronError, TypeError, ValueError):
        return False


def matches(dt: datetime.datetime, expression: str) -> bool:
    """Return True if ``dt`` exactly matches the cron expression (to the minute)."""
    parsed = parse_expression(expression)
    minutes, hours, doms, months, dows = parsed

    if dt.tzinfo is None:  # noqa: SIM108
        dt = dt.replace(tzinfo=datetime.UTC)
    else:
        dt = dt.astimezone(datetime.UTC)
    if dt.month not in months:
        return False
    full_dom = set(range(_FIELD_RANGES[2][0], _FIELD_RANGES[2][1] + 1))
    full_dow = set(range(_FIELD_RANGES[4][0], _FIELD_RANGES[4][1] + 1))
    dom_restricted = doms != full_dom
    dow_restricted = dows != full_dow
    if dom_restricted and dt.day not in doms:
        return False
    if dow_restricted and dt.weekday() not in dows:
        return False
    return dt.hour in hours and dt.minute in minutes


__all__ = [
    "CronError",
    "is_valid",
    "matches",
    "next_after",
    "parse_expression",
    "validate",
]


# ── Lightweight runtime checks for development ───────────────────────
if __name__ == "__main__":  # pragma: no cover
    import sys

    samples: Sequence[tuple[str, datetime.datetime, datetime.datetime]] = [
        (
            "*/5 * * * *",
            datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC),
            datetime.datetime(2026, 1, 1, 0, 5, tzinfo=datetime.UTC),
        ),
        (
            "0 9 * * 1-5",
            datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC),
            datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC),
        ),
        (
            "@hourly",
            datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC),
            datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.UTC),
        ),
        (
            "0 0 1 * *",
            datetime.datetime(2026, 1, 15, 12, 0, tzinfo=datetime.UTC),
            datetime.datetime(2026, 2, 1, 0, 0, tzinfo=datetime.UTC),
        ),
    ]
    for expr, base, expected in samples:
        got = next_after(base, expr)
        sys.stdout.write(f"{expr!r:24} base={base.isoformat()} -> {got.isoformat()} (expected {expected.isoformat()})\n")
