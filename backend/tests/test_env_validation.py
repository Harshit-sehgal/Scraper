"""Tests for startup configuration validation.

Verifies that env_validation surfaces misconfigurations without blocking
startup (the validator is a best-effort advisor, not a hardening gate).
"""
from __future__ import annotations

import logging

import pytest
from app.utils.env_validation import (
    validate_startup_config,
)


@pytest.fixture
def _reset_env(monkeypatch):
    """Strip known DATAFORGE_ vars before each test."""
    for var in [
        "DATAFORGE_ENV",
        "DATAFORGE_GROQ_API_KEY",
        "DATAFORGE_ENCRYPTION_KEY",
        "DATAFORGE_SESSION_SECRET",
        "DATAFORGE_WORKER_QUEUE",
        "DATAFORGE_SMOKE_TEST_MODE",
        "DATAFORGE_RATE_LIMIT_DB_BACKED",
        "DATAFORGE_PG_MIN_CONN",
        "DATAFORGE_PG_MAX_CONN",
        "DATAFORGE_PLAYWRIGHT_TIMEOUT",
        "DATAFORGE_MAX_HTML_BYTES",
        "DATAFORGE_RETENTION_DAYS_COMPLETED",
        "DATAFORGE_RETENTION_DAYS_RECYCLE",
        "DATAFORGE_STORAGE_BACKEND",
    ]:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_dev_mode_does_not_warn_missing_secrets(_reset_env, caplog):
    """Missing secrets only warns in production-like envs."""
    _reset_env.setenv("DATAFORGE_ENV", "development")
    with caplog.at_level(logging.INFO, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["missing_secrets"] == 0
    # dev mode should not warn about missing GROQ_API_KEY
    assert not any(
        "DATAFORGE_GROQ_API_KEY" in record.message for record in caplog.records
    )


def test_production_warns_missing_secrets(_reset_env, caplog):
    """Production-like envs should warn when secrets are missing."""
    _reset_env.setenv("DATAFORGE_ENV", "production")
    with caplog.at_level(logging.WARNING, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["missing_secrets"] >= 1
    assert any(
        "DATAFORGE_GROQ_API_KEY" in record.message for record in caplog.records
    )


def test_production_silent_when_secrets_present(_reset_env, caplog):
    _reset_env.setenv("DATAFORGE_ENV", "production")
    _reset_env.setenv("DATAFORGE_GROQ_API_KEY", "test-key")
    _reset_env.setenv("DATAFORGE_ENCRYPTION_KEY", "test-encryption-key")
    _reset_env.setenv("DATAFORGE_SESSION_SECRET", "test-session-secret")
    with caplog.at_level(logging.WARNING, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["missing_secrets"] == 0


def test_malformed_boolean_detected(_reset_env, caplog):
    _reset_env.setenv("DATAFORGE_WORKER_QUEUE", "perhaps")
    with caplog.at_level(logging.WARNING, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["malformed_booleans"] >= 1


def test_known_boolean_values_accepted(_reset_env):
    for val in ("1", "0", "true", "false", "yes", "no", ""):
        _reset_env.setenv("DATAFORGE_WORKER_QUEUE", val)
        summary = validate_startup_config()
        assert summary["malformed_booleans"] == 0, f"val={val!r} should be accepted"


def test_malformed_integer_detected(_reset_env, caplog):
    _reset_env.setenv("DATAFORGE_PG_MIN_CONN", "banana")
    with caplog.at_level(logging.WARNING, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["malformed_integers"] >= 1


def test_out_of_range_integer_detected(_reset_env, caplog):
    _reset_env.setenv("DATAFORGE_PG_MIN_CONN", "50000")  # above 1000 max
    with caplog.at_level(logging.WARNING, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["malformed_integers"] >= 1


def test_valid_integer_accepted(_reset_env):
    _reset_env.setenv("DATAFORGE_PG_MIN_CONN", "5")
    _reset_env.setenv("DATAFORGE_MAX_HTML_BYTES", "5242880")
    summary = validate_startup_config()
    assert summary["malformed_integers"] == 0


def test_sqlite_in_production_warns(_reset_env, caplog):
    _reset_env.setenv("DATAFORGE_ENV", "production")
    # default backend is sqlite
    with caplog.at_level(logging.WARNING, logger="app.utils.env_validation"):
        summary = validate_startup_config()
    assert summary["storage_warnings"] == 1


def test_postgres_in_production_silent(_reset_env):
    _reset_env.setenv("DATAFORGE_ENV", "production")
    _reset_env.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
    summary = validate_startup_config()
    assert summary["storage_warnings"] == 0


def test_summary_returns_counters(_reset_env):
    """Smoke test that the summary structure is preserved."""
    summary = validate_startup_config()
    assert set(summary.keys()) == {
        "missing_secrets",
        "malformed_booleans",
        "malformed_integers",
        "storage_warnings",
    }
    for v in summary.values():
        assert isinstance(v, int)
