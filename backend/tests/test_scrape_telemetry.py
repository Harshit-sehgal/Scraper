"""Tests for scrape telemetry normalization and aggregation."""

from __future__ import annotations

import math

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
