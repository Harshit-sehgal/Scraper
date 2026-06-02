"""Tests for acquisition telemetry collector."""

from app.acquisition_state import AcquisitionState
from app.acquisition_telemetry import AcquisitionTelemetryCollector


class TestAcquisitionTelemetryCollector:
    """Tests for the AcquisitionTelemetryCollector."""

    def test_record_direct_acquisition(self):
        collector = AcquisitionTelemetryCollector()
        event = collector.record(
            url="https://example.com/data",
            state=AcquisitionState.DIRECT,
            original_url="https://example.com/data",
            final_url="https://example.com/data",
            fetch_method="playwright_full",
        )
        assert event.state == "direct"
        assert event.url == "https://example.com/data"

    def test_record_session_expired(self):
        collector = AcquisitionTelemetryCollector()
        collector.record(
            url="https://example.com/search/abc123",
            state=AcquisitionState.SESSION_EXPIRED,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
            session_bound=True,
            ephemeral_params=["sessionid"],
        )
        summary = collector.get_summary()
        assert summary["session_bound_urls"] == 1
        assert summary["state_distribution"]["session_expired"] == 1

    def test_record_recovery_success(self):
        collector = AcquisitionTelemetryCollector()
        collector.record(
            url="https://example.com/search/abc123",
            state=AcquisitionState.RECOVERED,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/search?from=NYC&to=LHR",
            canonical_url="https://example.com/search?from=NYC&to=LHR",
            fetch_method="search_form_post",
            recovery_method="search_form_post",
            recovered_url="https://example.com/search?from=NYC&to=LHR",
        )
        summary = collector.get_summary()
        assert summary["recovery_attempts"] == 1
        assert summary["recovery_successes"] == 1
        assert summary["recovery_success_rate"] == 1.0

    def test_record_recovery_failure(self):
        collector = AcquisitionTelemetryCollector()
        collector.record(
            url="https://example.com/search/abc123",
            state=AcquisitionState.RECOVERY_FAILED,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
        )
        summary = collector.get_summary()
        assert summary["recovery_attempts"] == 1
        assert summary["recovery_successes"] == 0
        assert summary["recovery_success_rate"] == 0.0

    def test_mixed_acquisitions(self):
        collector = AcquisitionTelemetryCollector()
        collector.record(
            url="https://a.com",
            state=AcquisitionState.DIRECT,
            original_url="https://a.com",
            final_url="https://a.com")
        collector.record(
            url="https://b.com/s/abc",
            state=AcquisitionState.RECOVERED,
            original_url="https://b.com/s/abc",
            final_url="https://b.com/search?q=1",
            recovery_method="search_form_post")
        collector.record(
            url="https://c.com/s/xyz",
            state=AcquisitionState.SESSION_EXPIRED,
            original_url="https://c.com/s/xyz",
            final_url="https://c.com/")
        summary = collector.get_summary()
        assert summary["total_acquisitions"] == 3
        assert summary["state_distribution"]["direct"] == 1
        assert summary["state_distribution"]["recovered"] == 1
        assert summary["state_distribution"]["session_expired"] == 1

    def test_get_recent_events(self):
        collector = AcquisitionTelemetryCollector()
        for i in range(5):
            collector.record(
                url=f"https://example.com/{i}",
                state=AcquisitionState.DIRECT,
                original_url=f"https://example.com/{i}",
                final_url=f"https://example.com/{i}",
            )
        recent = collector.get_recent(3)
        assert len(recent) == 3
        assert recent[-1]["url"] == "https://example.com/4"

    def test_max_history_trimming(self):
        collector = AcquisitionTelemetryCollector(max_history=10)
        for i in range(15):
            collector.record(
                url=f"https://example.com/{i}",
                state=AcquisitionState.DIRECT,
                original_url=f"https://example.com/{i}",
                final_url=f"https://example.com/{i}",
            )
        assert len(collector._history) == 10
        assert collector._history[0].url == "https://example.com/5"

    def test_clear(self):
        collector = AcquisitionTelemetryCollector()
        collector.record(
            url="https://a.com",
            state=AcquisitionState.DIRECT,
            original_url="https://a.com",
            final_url="https://a.com")
        collector.clear()
        assert collector.get_summary()["total_acquisitions"] == 0

    def test_recovery_rate_with_mixed_outcomes(self):
        collector = AcquisitionTelemetryCollector()
        collector.record(
            url="https://a.com",
            state=AcquisitionState.RECOVERED,
            original_url="https://a.com",
            final_url="https://a.com/fresh")
        collector.record(
            url="https://b.com",
            state=AcquisitionState.RECOVERY_FAILED,
            original_url="https://b.com",
            final_url="https://b.com/")
        collector.record(
            url="https://c.com",
            state=AcquisitionState.RECOVERED,
            original_url="https://c.com",
            final_url="https://c.com/fresh")
        summary = collector.get_summary()
        assert summary["recovery_attempts"] == 3
        assert summary["recovery_successes"] == 2
        assert summary["recovery_success_rate"] == round(2 / 3, 3)
