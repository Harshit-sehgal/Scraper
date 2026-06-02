"""Unit Tests for Telemetry State Adapter.

Tests TelemetryStateAdapter methods and the module-level singleton.
"""

from __future__ import annotations

from unittest.mock import patch

from app.telemetry_state import TelemetryStateAdapter, get_telemetry_state


class TestTelemetryStateAdapter:
    """Tests for TelemetryStateAdapter methods."""

    def setup_method(self):
        """Reset module-level singletons before each test to avoid cross-test pollution."""
        import app.scrape_telemetry as st
        import app.telemetry_state as ts
        ts._telemetry_state = None
        st._collector = None

    def test_initial_stats_empty(self):
        adapter = TelemetryStateAdapter()
        stats = adapter.get_stats()
        assert stats["total_scrapes"] == 0
        assert stats["avg_fetch_ms"] == 0.0
        assert stats["fallback_rate"] == 0.0
        assert stats["avg_confidence"] == 0.0

    def test_record_scrape_delegates_to_telemetry(self):
        adapter = TelemetryStateAdapter()
        with patch.object(adapter._telemetry, "record") as mock_record:
            adapter.record_scrape("http://example.com", fetch_ms=100)
            mock_record.assert_called_once_with("http://example.com", fetch_ms=100)

    def test_record_stabilization(self):
        adapter = TelemetryStateAdapter()
        adapter.record_stabilization("example.com", 1200.0)
        assert adapter.get_avg_stabilization("example.com") == 1200.0

    def test_avg_stabilization_bounded(self):
        adapter = TelemetryStateAdapter()
        adapter.record_stabilization("slow.com", 9999.0)
        assert adapter.get_avg_stabilization("slow.com") == 5000.0  # Clamped to max

    def test_avg_stabilization_minimum(self):
        adapter = TelemetryStateAdapter()
        adapter.record_stabilization("fast.com", 10.0)
        assert adapter.get_avg_stabilization("fast.com") == 500.0  # Clamped to min

    def test_default_stabilization_is_1500(self):
        adapter = TelemetryStateAdapter()
        assert adapter.get_avg_stabilization("unknown.com") == 1500.0

    def test_stabilization_rolling_window(self):
        adapter = TelemetryStateAdapter()
        for _ in range(15):
            adapter.record_stabilization("test.com", 1000.0)
        # Only last 10 are kept
        assert len(adapter._domain_stabilization_times["test.com"]) == 10
        assert adapter.get_avg_stabilization("test.com") == 1000.0

    def test_clear_wipes_telemetry(self):
        adapter = TelemetryStateAdapter()
        adapter.record_scrape("http://example.com")
        with patch.object(adapter._telemetry, "clear") as mock_clear:
            adapter.clear()
            mock_clear.assert_called_once()

    def test_get_recent_snapshots(self):
        adapter = TelemetryStateAdapter()
        expected = [{"url": "http://x.com"}]
        with patch.object(adapter._telemetry, "get_recent", return_value=expected) as mock_get:
            result = adapter.get_recent_snapshots(count=5)
            assert result == expected
            mock_get.assert_called_once_with(5)

    def test_get_confidence_histogram(self):
        adapter = TelemetryStateAdapter()
        expected = {"high": 10, "low": 2}
        with patch.object(adapter._telemetry, "get_confidence_histogram", return_value=expected) as mock_get:
            result = adapter.get_confidence_histogram(count=50)
            assert result == expected
            mock_get.assert_called_once_with(50)

    def test_get_stats_with_data(self):
        """get_stats() with non-empty recent data (covers confidence_scores logic)."""
        adapter = TelemetryStateAdapter()
        mock_recent = [
            {"fetch_ms": 200.0, "fallback_triggered": False, "confidence_map": {"overall_avg": 0.85}},
            {"fetch_ms": 300.0, "fallback_triggered": True, "confidence_map": {"overall_avg": 0.75}},
            {"fetch_ms": 100.0, "fallback_triggered": False, "confidence_map": {"overall_avg": 0.95}},
        ]
        with patch.object(adapter._telemetry, "get_recent", return_value=mock_recent):
            stats = adapter.get_stats()
            assert stats["total_scrapes"] == 3
            assert stats["avg_fetch_ms"] == 200.0  # (200+300+100)/3 = 200
            assert stats["fallback_rate"] == 0.333  # 1/3
            assert stats["avg_confidence"] == 0.85  # (0.85+0.75+0.95)/3 = 0.85


class TestGetTelemetryState:
    """Tests for the module-level singleton."""

    def setup_method(self):
        import app.scrape_telemetry as st
        import app.telemetry_state as ts
        ts._telemetry_state = None
        st._collector = None

    def test_returns_singleton(self):
        import app.telemetry_state as ts
        ts._telemetry_state = None

        first = get_telemetry_state()
        second = get_telemetry_state()
        assert first is second  # Same instance

    def test_type(self):
        import app.telemetry_state as ts
        ts._telemetry_state = None
        instance = get_telemetry_state()
        assert isinstance(instance, TelemetryStateAdapter)
