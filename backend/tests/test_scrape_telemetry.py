"""Tests for scrape telemetry normalization and aggregation."""

from __future__ import annotations

import logging
import math

import pytest
from app.scrape_telemetry import ScrapeTelemetryCollector


def test_confidence_histogram_clamps_and_skips_malformed_scores() -> None:
    collector = ScrapeTelemetryCollector()

    collector.record("https://example.com/a", confidence_map={"overall_avg": -0.5})
    collector.record("https://example.com/b", confidence_map={"overall_avg": 0.42})
    collector.record("https://example.com/c", confidence_map={"overall_avg": 1.5})
    collector.record("https://example.com/d", confidence_map={"overall_avg": "bad"})
    collector.record("https://example.com/e", confidence_map={"overall_avg": math.nan})

    histogram = collector.get_confidence_histogram(10)

    assert sum(histogram.values()) == 3
    assert histogram["0.0-0.1"] == 1
    assert histogram["0.4-0.5"] == 1
    assert histogram["0.9-1.0"] == 1


def test_record_emits_telemetry_even_when_observability_sinks_fail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Telemetry must not be lost when the observability sinks raise.

    Regression test for the silent ``except Exception: pass`` blocks that used
    to mask emission failures. The collected ``ScrapeTelemetry`` is the
    source of truth and must always be returned to the caller, while
    failures from optional sinks (domain intelligence, world state) should
    be logged at exception level so operators can see them.
    """
    import app.scrape_telemetry as telemetry_module

    collector = ScrapeTelemetryCollector()

    # Force both optional sinks to raise. ``record`` must still return
    # a valid ``ScrapeTelemetry`` and log the failures.
    world_state_down = RuntimeError("world-state-down")
    domain_intel_down = RuntimeError("domain-intel-down")

    with caplog.at_level(logging.ERROR, logger="app.scrape_telemetry"):
        original_record_degradation = None
        original_update_from_telemetry = None

        try:
            from app.semantic_world_state import get_world_state

            ws = get_world_state()
            original_record_degradation = ws.record_degradation

            def _boom_record(*_args, **_kwargs):
                raise world_state_down

            ws.record_degradation = _boom_record  # type: ignore[method-assign]

            from app.domain_intelligence import get_domain_intelligence

            di = get_domain_intelligence()
            original_update_from_telemetry = di.update_from_telemetry

            def _boom_update(*_args, **_kwargs):
                raise domain_intel_down

            di.update_from_telemetry = _boom_update  # type: ignore[method-assign]

            telemetry = collector.record("https://example.com/sink-fail")

            # Telemetry itself is preserved (source of truth).
            assert telemetry.url == "https://example.com/sink-fail"
            assert telemetry.records_final == 0

            # Both failures are now visible in the log instead of being
            # silently swallowed. Allow the caplog fixture to receive
            # both the domain-intelligence failure and the world-state
            # failure; either order is acceptable because record() calls
            # them sequentially.
            exception_records = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert len(exception_records) >= 1, "Expected at least one ERROR-level log from a failed sink"
        finally:
            if original_record_degradation is not None:
                ws.record_degradation = original_record_degradation  # type: ignore[method-assign]
            if original_update_from_telemetry is not None:
                di.update_from_telemetry = original_update_from_telemetry  # type: ignore[method-assign]

    # Sanity: the module still exposes a working logger and collector.
    assert telemetry_module.logger is not None
    assert collector.get_last_for_url("https://example.com/sink-fail") is not None
