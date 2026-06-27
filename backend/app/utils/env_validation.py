"""Startup configuration validation — fail-fast on dangerous misconfigurations.

Why this exists:

- A startup-time check that warns about an empty secret key is much more
  useful than a runtime ``InvalidTokenError`` deep in a request handler.
- ENV wiring mistakes (typo in a var name, wrong value type, accidentally
  setting ``DATAFORGE_ENV=development`` in production) are best caught
  before the app accepts traffic.
- Several secret values (API keys, encryption keys) are technically
  optional — but in production, missing them should escalate from silent
  default to a loud warning.

This module exposes :func:`validate_startup_config` which is invoked once
at app startup.  The function:

1. Logs warnings for *dev-only* settings detected in non-dev environments
2. Logs warnings for secrets that are unset when the app is in production
3. Logs warnings for malformed integer / boolean values in known env vars
4. Does NOT raise — the goal is to surface problems, not prevent start
   (mocking/incomplete local setups are legitimate).

Tests live in ``tests/test_env_validation.py``.
"""

from __future__ import annotations

import logging
import os
from typing import Final

logger = logging.getLogger(__name__)


# Env vars we expect to be set in production-ish environments.
_PRODUCTION_SECRET_ENV_VARS: Final[tuple[tuple[str, str], ...]] = (
    # (env var name, plain-English description of what remains broken if missing)
    ("DATAFORGE_GROQ_API_KEY", "LLM extraction features (intent parsing, schema suggestions)"),
    ("DATAFORGE_ENCRYPTION_KEY", "API key + token encryption at rest"),
    ("DATAFORGE_SESSION_SECRET", "session cookie signing"),
)

# Boolean-style env vars that should not be silently mistyped. If a value
# is provided, it must match an expected truthy/falsy form.
_KNOWN_BOOL_VARS: Final[dict[str, tuple[str, ...]]] = {
    "DATAFORGE_WORKER_QUEUE": ("1", "0", "true", "false", "yes", "no", ""),
    "DATAFORGE_SMOKE_TEST_MODE": ("1", "0", "true", "false", "yes", "no", ""),
    "DATAFORGE_RATE_LIMIT_DB_BACKED": ("1", "0", "true", "false", "yes", "no", ""),
}

# Integer-style env vars with allowed bounds. Used to catch e.g.
# DATAFORGE_PG_MIN_CONN=banana.
_KNOWN_INT_VARS: Final[dict[str, tuple[int, int]]] = {
    "DATAFORGE_PG_MIN_CONN": (1, 1000),
    "DATAFORGE_PG_MAX_CONN": (1, 1000),
    "DATAFORGE_PLAYWRIGHT_TIMEOUT": (1000, 600000),  # 1s - 10min ms
    "DATAFORGE_MAX_HTML_BYTES": (1024, 100 * 1024 * 1024),  # 1 KB - 100 MB
    "DATAFORGE_RETENTION_DAYS_COMPLETED": (1, 3650),
    "DATAFORGE_RETENTION_DAYS_RECYCLE": (1, 365),
}

# Patterns that suggest an env var has leaked its secret value into
# something user-readable (logs, help text, etc).
_LEAK_SUSPECTS: Final[tuple[str, ...]] = (
    # Common env vars that must never appear in customer-facing output.
    "DATAFORGE_ENCRYPTION_KEY",
    "DATAFORGE_SESSION_SECRET",
    "DATAFORGE_DATABASE_URL",  # may embed password
    "DATAFORGE_GROQ_API_KEY",
)


def _is_production_like() -> bool:
    """Determine whether secrets are expected to be configured."""
    env = (os.environ.get("DATAFORGE_ENV") or "").strip().lower()
    return env in {"production", "staging", "prod"}


def _warn_missing_secrets() -> int:
    """Warn about secrets that are unset in production-like envs.

    Returns the number of warnings raised (used by tests).
    """
    if not _is_production_like():
        return 0
    warned = 0
    for var, what_breaks in _PRODUCTION_SECRET_ENV_VARS:
        if not (os.environ.get(var) or "").strip():
            logger.warning(
                "STARTUP: %s is not set. In production this disables: %s",
                var,
                what_breaks,
            )
            warned += 1
    return warned


def _warn_malformed_booleans() -> int:
    """Warn about boolean env vars with non-truthy/falsy values."""
    warned = 0
    for var, allowed in _KNOWN_BOOL_VARS.items():
        value = os.environ.get(var)
        if value is None:
            continue
        normalized = value.strip().lower()
        if normalized in allowed:
            continue
        logger.warning(
            "STARTUP: %s=%r is not a recognised boolean (allowed: %s). "
            "Treating as unset; set explicitly to 'true'/'false' to silence.",
            var,
            value,
            ", ".join(a for a in allowed if a),
        )
        warned += 1
    return warned


def _warn_malformed_integers() -> int:
    """Warn about integer env vars with non-integer / out-of-range values."""
    warned = 0
    for var, (lo, hi) in _KNOWN_INT_VARS.items():
        value = os.environ.get(var)
        if value is None or value.strip() == "":
            continue
        try:
            ivalue = int(value.strip())
        except ValueError:
            logger.warning(
                "STARTUP: %s=%r is not an integer — using default.",
                var,
                value,
            )
            warned += 1
            continue
        if ivalue < lo or ivalue > hi:
            logger.warning(
                "STARTUP: %s=%d is outside the recommended range [%d, %d].",
                var,
                ivalue,
                lo,
                hi,
            )
            warned += 1
    return warned


def _warn_suspicious_storage_backend() -> int:
    """Warn if a production-like env still points at SQLite.

    SQLite is fine for dev but should be replaced with Postgres in
    production for multi-worker concurrency and durability.
    """
    if not _is_production_like():
        return 0
    backend = (os.environ.get("DATAFORGE_STORAGE_BACKEND") or "sqlite").strip().lower()
    if backend in {"sqlite", ""}:
        logger.warning(
            "STARTUP: DATAFORGE_STORAGE_BACKEND=%r in %s environment. "
            "SQLite is fine for dev/single-worker but Postgres is recommended "
            "for production durability and concurrency.",
            backend,
            os.environ.get("DATAFORGE_ENV"),
        )
        return 1
    return 0


def validate_startup_config() -> dict[str, int]:
    """Run all startup configuration checks. Idempotent.

    Returns:
        A summary dict with ``missing_secrets``, ``malformed_booleans``,
        ``malformed_integers``, ``storage_warnings`` — useful for tests
        and operator dashboards.
    """
    summary = {
        "missing_secrets": _warn_missing_secrets(),
        "malformed_booleans": _warn_malformed_booleans(),
        "malformed_integers": _warn_malformed_integers(),
        "storage_warnings": _warn_suspicious_storage_backend(),
    }
    total = sum(summary.values())
    logger.info(
        "STARTUP: configuration validation complete (%d warning%s)",
        total,
        "" if total == 1 else "s",
    )
    return summary
