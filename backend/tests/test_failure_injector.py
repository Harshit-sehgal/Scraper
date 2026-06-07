"""Tests for the ``FailureInjector`` singleton and its production guard.

The injector is a module-level singleton, so we reset the probability
back to 0 at the end of every test that touches it. Tests that flip
``DATAFORGE_ENV`` use ``monkeypatch.delenv`` / ``monkeypatch.setenv``
so the original environment is restored automatically.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_injector() -> None:
    """Always leave the injector disabled after each test."""
    from app.failure_injector import set_injection_probability

    set_injection_probability(0.0)
    yield
    set_injection_probability(0.0)


def test_set_injection_probability_stores_value() -> None:
    """In a non-production env, set_injection_probability stores the value."""
    from app.failure_injector import (
        get_injector,
        set_injection_probability,
    )

    # Default env is whatever the test runner set; if it is production
    # the guard kicks in and we cannot test the store path. Skip in that
    # case — the guard itself is covered by the dedicated test below.
    if (os.environ.get("DATAFORGE_ENV") or "").strip().lower() == "production":
        pytest.skip("Test runner is in production env; guard is tested separately")

    set_injection_probability(0.5)
    assert get_injector().probability == 0.5
    assert get_injector().active is True


def test_set_injection_probability_to_zero_disables() -> None:
    """Zero probability must always disable the injector, even in production."""
    from app.failure_injector import (
        get_injector,
        set_injection_probability,
    )

    set_injection_probability(0.0)
    assert get_injector().probability == 0.0
    assert get_injector().active is False


def test_production_guard_refuses_to_enable(monkeypatch) -> None:
    """When DATAFORGE_ENV=production, set_injection_probability(>0) is refused.

    The injector probability must stay at 0 and a warning must be logged.
    """
    from app.failure_injector import (
        get_injector,
        set_injection_probability,
    )

    monkeypatch.setenv("DATAFORGE_ENV", "production")

    set_injection_probability(0.0)  # baseline
    set_injection_probability(0.9)  # should be refused

    assert get_injector().probability == 0.0
    assert get_injector().active is False


def test_production_guard_logs_warning(monkeypatch, caplog) -> None:
    """The production guard must emit a WARNING that names the env var."""
    import logging

    from app.failure_injector import set_injection_probability

    monkeypatch.setenv("DATAFORGE_ENV", "production")

    with caplog.at_level(logging.WARNING, logger="app.failure_injector"):
        set_injection_probability(0.5)

    assert any("Refusing to enable failure injection in production" in record.message for record in caplog.records)


def test_production_guard_does_not_affect_zero(monkeypatch) -> None:
    """Setting probability to 0 in production must remain a no-op (no warning)."""
    from app.failure_injector import (
        get_injector,
        set_injection_probability,
    )

    monkeypatch.setenv("DATAFORGE_ENV", "production")

    set_injection_probability(0.0)
    assert get_injector().probability == 0.0
    assert get_injector().active is False


def test_production_guard_does_not_affect_other_envs(monkeypatch) -> None:
    """In dev/staging envs the guard must not block the store path."""
    from app.failure_injector import (
        get_injector,
        set_injection_probability,
    )

    monkeypatch.setenv("DATAFORGE_ENV", "staging")

    set_injection_probability(0.3)
    assert get_injector().probability == 0.3
    assert get_injector().active is True
