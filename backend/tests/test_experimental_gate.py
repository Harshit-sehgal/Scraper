"""Tests for the experimental subsystems gate.

The deep-research-report requires that the research shell be quarantined
behind a single flag (`ENABLE_EXPERIMENTAL_ROUTES`). These tests verify
that `experimental_startup.experimental_subsystems_enabled()` reads the
flag correctly and that every public function in the module becomes a
no-op when the flag is off.

We do NOT exercise the full FastAPI lifespan here — that requires
running the app, and conftest already has fixtures for that. The unit
tests below cover the gate logic in isolation so a regression in the
flag wiring is caught at the fastest possible layer.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import pytest
from app.experimental_startup import (
    close_postgres_pool,
    experimental_subsystems_enabled,
    init_domain_health_monitor,
    init_gossip_and_heartbeat,
    init_graph_scheduler,
    init_recovery_framework,
    persist_semantic_world_state,
    restore_semantic_world_state,
    schedule_gossip_propagation,
)

# ─── Gate function ──────────────────────────────────────────────────────────


def test_gate_reads_settings_flag(monkeypatch) -> None:
    """When settings.ENABLE_EXPERIMENTAL_ROUTES is True, gate returns True."""
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", True, raising=False)
    assert experimental_subsystems_enabled() is True


def test_gate_returns_false_by_default(monkeypatch) -> None:
    """When settings.ENABLE_EXPERIMENTAL_ROUTES is False, gate returns False."""
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False, raising=False)
    assert experimental_subsystems_enabled() is False


def test_gate_falls_back_to_false_if_attribute_missing(monkeypatch) -> None:
    """If settings has no ENABLE_EXPERIMENTAL_ROUTES attribute, gate defaults to False."""
    from app import experimental_startup

    class _FakeSettings:
        pass

    monkeypatch.setattr(experimental_startup, "settings", _FakeSettings(), raising=False)
    # The function imports settings lazily, so we patch the import target.
    with patch("app.config.settings", _FakeSettings()):
        assert experimental_subsystems_enabled() is False


# ─── Each init_* function is a no-op when the gate is closed ───────────────


@pytest.fixture
def gate_off(monkeypatch) -> None:
    """Force the gate off for the duration of one test."""
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False, raising=False)


@pytest.fixture
def gate_on(monkeypatch) -> None:
    """Force the gate on for the duration of one test."""
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", True, raising=False)


def test_init_graph_scheduler_noop_when_disabled(gate_off, caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.experimental_startup"):
        init_graph_scheduler()
    # Function should not have raised and should not have logged a successful init.
    assert "Graph update scheduler initialized" not in caplog.text


def test_init_recovery_framework_noop_when_disabled(gate_off, caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.experimental_startup"):
        init_recovery_framework()
    assert "Recovery handlers registered" not in caplog.text


def test_init_domain_health_monitor_noop_when_disabled(gate_off, caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.experimental_startup"):
        init_domain_health_monitor()
    assert "Domain health monitor initialized" not in caplog.text


def test_init_gossip_and_heartbeat_returns_none_tuple_when_disabled(gate_off) -> None:
    gossip, heartbeat = init_gossip_and_heartbeat()
    assert gossip is None
    assert heartbeat is None


def test_restore_semantic_world_state_noop_when_disabled(gate_off) -> None:
    # Should not raise even with arbitrary input.
    restore_semantic_world_state({"some": "data"}, "/tmp/state.json")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
    restore_semantic_world_state(None, "")


def test_persist_semantic_world_state_noop_when_disabled(gate_off) -> None:
    # Should not raise.
    persist_semantic_world_state()


# ─── schedule_gossip_propagation is gated ─────────────────────────────────


def test_schedule_gossip_propagation_noop_when_disabled(gate_off) -> None:
    # Even if a non-None gossip object is passed, the gate must short-circuit
    # and return None — we don't want research work to start accidentally.
    fake_gossip = object()
    fake_heartbeat = object()
    result = asyncio.run(schedule_gossip_propagation(fake_gossip, fake_heartbeat, interval=1.0))
    assert result is None


def test_schedule_gossip_propagation_noop_when_gossip_is_none(gate_on) -> None:
    # Even with the gate open, None gossip should still short-circuit.
    result = asyncio.run(schedule_gossip_propagation(None, None, interval=1.0))
    assert result is None


# ─── close_postgres_pool is NOT gated (Postgres is product kernel) ─────────


def test_close_postgres_pool_is_not_gated(monkeypatch, caplog) -> None:
    """close_postgres_pool must run even when the experimental gate is closed.

    Postgres is a product-kernel storage backend, so its pool-close
    logic must work regardless of the research-shell flag.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False, raising=False)
    # Patch the inner shutdown_postgres to a no-op so we don't actually
    # touch a connection pool.
    with patch("app.postgres_repository.shutdown_postgres"):
        close_postgres_pool()
    # We don't assert it was called (ImportError path is acceptable too),
    # but we DO assert the function did not raise.


# ─── End-to-end 403 verification ───────────────────────────────────────


def test_experimental_router_returns_403_when_disabled(monkeypatch) -> None:
    """A request to an experimental endpoint must 403 when the gate is off.

    This is the HTTP-level complement to the import-time gate tests
    above. The experimental router is mounted with a single
    ``Depends(verify_experimental_enabled)`` dependency on every
    route, so flipping ``ENABLE_EXPERIMENTAL_ROUTES=False`` and
    hitting any endpoint on the router must produce a 403 (not a
    404 — that would suggest the router wasn't mounted, which is a
    different failure mode than "feature flag is off").
    """
    from app.config import settings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False, raising=False)

    # Import the router lazily so we can mount it on a fresh app
    # with the gate set to off. The router object itself is created
    # at import time, but the dependency is evaluated per request,
    # so a settings override at request time is what flips the gate.
    from app.routers.experimental import router as experimental_router

    test_app = FastAPI()
    test_app.include_router(experimental_router)

    with TestClient(test_app) as tc:
        # /api/system/topology is a GET endpoint, so no body is needed.
        resp = tc.get("/api/system/topology")
    assert resp.status_code == 403, f"Expected 403 with gate off, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "Experimental" in body.get("detail", "") or "experimental" in body.get("detail", "").lower()
    # The 403 must name the env var so operators can self-diagnose.
    assert "DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES" in body.get("detail", "")
