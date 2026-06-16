"""Regression test for auth_profiles._warn_if_production_inmemory_store.

The auth-profile router stores profiles in a per-process ``dict`` and
carries a ``replace with DB in production`` comment. In a multi-worker
production deployment this drops writes between workers and loses all
profiles on every worker restart. The module now logs a CRITICAL
warning at import time when the configured ENV is production-like so
the limitation cannot be silently ignored.

These tests pin the new behavior by reloading the auth_profiles module
after monkey-patching ``app.config.settings.ENV`` and inspecting the
captured log records.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

import pytest
from app.config import settings


def _reload_auth_profiles_module() -> Any:
    """Re-import the auth_profiles module to force module-level work."""
    # Drop the cached module so the import-time check runs again with
    # whatever monkey-patched settings are in effect.
    return importlib.reload(importlib.import_module("app.routers.auth_profiles"))


def _captured_log_records(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> list[logging.LogRecord]:
    """Run the module-init check inside a captured-log context."""
    with caplog.at_level(logging.CRITICAL):
        _reload_auth_profiles_module()
    return list(caplog.records)


def test_production_env_triggers_critical_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ENV == 'production', the module logs at CRITICAL on load."""
    monkeypatch.setattr(settings, "ENV", "production")
    records = _captured_log_records(caplog, monkeypatch)
    assert any(
        record.levelno == logging.CRITICAL
        and "Auth profile store is in-memory" in record.getMessage()
        for record in records
    ), "Expected CRITICAL warning about in-memory auth profile store under production ENV"


def test_staging_env_triggers_critical_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ENV == 'staging', the module also logs at CRITICAL on load."""
    monkeypatch.setattr(settings, "ENV", "staging")
    records = _captured_log_records(caplog, monkeypatch)
    assert any(
        record.levelno == logging.CRITICAL
        and "Auth profile store is in-memory" in record.getMessage()
        for record in records
    )


def test_test_env_does_not_warn(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under ``test`` env (used by ``validate_local.py``), no warning fires."""
    monkeypatch.setattr(settings, "ENV", "test")
    records = _captured_log_records(caplog, monkeypatch)
    assert not any(
        "Auth profile store is in-memory" in record.getMessage()
        for record in records
    ), "Test env must not raise the production warning"


def test_development_env_does_not_warn(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under ``development`` env, no warning fires."""
    monkeypatch.setattr(settings, "ENV", "development")
    records = _captured_log_records(caplog, monkeypatch)
    assert not any(
        "Auth profile store is in-memory" in record.getMessage()
        for record in records
    )


def test_empty_env_does_not_warn(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under ``ENV=""`` (unset), no warning fires (unsafe-ENV check skipped)."""
    monkeypatch.setattr(settings, "ENV", "")
    records = _captured_log_records(caplog, monkeypatch)
    assert not any(
        "Auth profile store is in-memory" in record.getMessage()
        for record in records
    )
