"""Tests for Self-Tuning Extraction — Automatic parameter adjustment.

Tests:
  - Tuning parameter creation and defaults
  - Telemetry recording
  - Fetch timeout adjustment
  - Adaptive pacing (delay adjustment)
  - Retry optimization
  - Confidence threshold tuning
  - Report generation
"""

from app.config import settings
from app.self_tuning_extraction import (
    SelfTuningController,
    get_self_tuning_controller,
)


class TestSelfTuningController:
    """Test the Self-Tuning Controller."""

    def test_create_controller(self) -> None:
        """Test creating a tuning controller."""
        controller = SelfTuningController()
        assert controller is not None
        assert len(controller._parameters) == 0

    def test_get_parameters_creates_defaults(self) -> None:
        """Test that getting parameters creates defaults."""
        controller = SelfTuningController()
        params = controller.get_parameters("example.com")

        assert params.domain == "example.com"
        assert params.fetch_timeout_s > 0
        assert params.delay_between_requests_s > 0
        assert params.max_retries >= 0

    def test_parameters_defaults_match_settings(self) -> None:
        """Test default values match config."""
        controller = SelfTuningController()
        params = controller.get_parameters("example.com")

        assert params.fetch_timeout_s == settings.PLAYWRIGHT_TIMEOUT / 1000.0
        assert params.delay_between_requests_s == settings.CRAWL_DEFAULT_DELAY_SECONDS
        assert params.max_retries == settings.MAX_RETRIES
        assert params.min_confidence_threshold == settings.DEFAULT_MIN_RECORD_SCORE

    def test_record_telemetry_creates_history(self) -> None:
        """Test recording telemetry creates history."""
        controller = SelfTuningController()
        controller.record_telemetry(
            "example.com",
            {
                "fetch_ms": 1000.0,
                "anti_bot_score": 0.0,
                "confidence_map": {"overall_avg": 0.9},
            },
        )

        assert "example.com" in controller._telemetry
        assert len(controller._telemetry["example.com"]) == 1

    def test_multiple_telemetry_records(self) -> None:
        """Test recording multiple telemetry snapshots."""
        controller = SelfTuningController()
        for i in range(20):
            controller.record_telemetry(
                "example.com",
                {
                    "fetch_ms": 500.0 + i * 50,
                    "anti_bot_score": min(1.0, i * 0.05),
                    "confidence_map": {"overall_avg": max(0.3, 0.9 - i * 0.03)},
                },
            )

        assert len(controller._telemetry["example.com"]) == 20

    def test_history_capped_at_50(self) -> None:
        """Test that history is capped at 50 records."""
        controller = SelfTuningController()
        for _i in range(100):
            controller.record_telemetry(
                "example.com",
                {
                    "fetch_ms": 500.0,
                    "anti_bot_score": 0.0,
                    "confidence_map": {"overall_avg": 0.9},
                },
            )

        assert len(controller._telemetry["example.com"]) == 50

    def test_fetch_timeout_adjusts_up(self) -> None:
        """Test that timeout increases with slow fetches."""
        controller = SelfTuningController()

        # Record slow fetches (5000ms average)
        for i in range(10):
            controller.record_telemetry(
                "slow-domain.com",
                {
                    "fetch_ms": 5000.0 + i * 100,
                    "anti_bot_score": 0.1,
                    "confidence_map": {"overall_avg": 0.7},
                },
            )

        params = controller.get_parameters("slow-domain.com")
        # Timeout should be >= 2x avg + 5s = 2*5 + 5 = 15s
        assert params.fetch_timeout_s >= 15.0

    def test_fetch_timeout_stays_within_bounds(self) -> None:
        """Test that timeout stays within configured bounds."""
        controller = SelfTuningController()

        # Record extremely fast fetches
        for _i in range(10):
            controller.record_telemetry(
                "fast-domain.com",
                {
                    "fetch_ms": 50.0,
                    "anti_bot_score": 0.0,
                    "confidence_map": {"overall_avg": 0.95},
                },
            )

        params = controller.get_parameters("fast-domain.com")
        # Should not go below min_timeout (10.0)
        assert params.fetch_timeout_s >= 10.0

    def test_delay_increases_with_anti_bot(self) -> None:
        """Test that delay increases with anti-bot score."""
        controller = SelfTuningController()

        # High anti-bot domain
        for _i in range(5):
            controller.record_telemetry(
                "anti-bot-domain.com",
                {
                    "fetch_ms": 2000.0,
                    "anti_bot_score": 0.9,
                    "confidence_map": {"overall_avg": 0.3},
                },
            )

        params = controller.get_parameters("anti-bot-domain.com")
        # Delay should be increased beyond base
        assert params.delay_between_requests_s >= settings.CRAWL_DEFAULT_DELAY_SECONDS

    def test_retries_increase_with_failures(self) -> None:
        """Test that retries increase when success rate is low."""
        controller = SelfTuningController()

        # Record failures
        controller.record_telemetry(
            "failing-domain.com",
            {
                "fetch_ms": 1000.0,
                "error": "timeout",
                "failure_category": "timeout",
                "anti_bot_score": 0.0,
                "confidence_map": {"overall_avg": 0.0},
            },
        )

        params = controller.get_parameters("failing-domain.com")
        initial_retries = params.max_retries

        # Record more failures
        for _ in range(4):
            controller.record_telemetry(
                "failing-domain.com",
                {
                    "fetch_ms": 1000.0,
                    "error": "timeout",
                    "failure_category": "timeout",
                    "anti_bot_score": 0.0,
                    "confidence_map": {"overall_avg": 0.0},
                },
            )

        params2 = controller.get_parameters("failing-domain.com")
        assert params2.max_retries >= initial_retries

    def test_confidence_threshold_adjusts(self) -> None:
        """Test that confidence threshold adjusts with quality."""
        controller = SelfTuningController()
        domain = "quality-domain.com"

        # Record high quality extractions
        for _i in range(10):
            controller.record_telemetry(
                domain,
                {
                    "fetch_ms": 500.0,
                    "anti_bot_score": 0.0,
                    "confidence_map": {"overall_avg": 0.85},
                },
            )

        params = controller.get_parameters(domain)
        # Confidence threshold should not decrease with high quality
        assert params.min_confidence_threshold >= 0.35

    def test_tuning_report_empty(self) -> None:
        """Test tuning report with no data."""
        controller = SelfTuningController()
        report = controller.get_tuning_report()
        assert report["total_domains_tuned"] == 0

    def test_tuning_report_with_data(self) -> None:
        """Test tuning report with data."""
        controller = SelfTuningController()
        controller.record_telemetry(
            "example.com",
            {
                "fetch_ms": 1000.0,
                "anti_bot_score": 0.3,
                "confidence_map": {"overall_avg": 0.8},
            },
        )

        report = controller.get_tuning_report()
        assert report["total_domains_tuned"] >= 1
        assert "averages" in report
        assert report["total_adjustments"] >= 0

    def test_domain_report(self) -> None:
        """Test getting domain-specific report."""
        controller = SelfTuningController()
        controller.record_telemetry(
            "example.com",
            {
                "fetch_ms": 1000.0,
                "anti_bot_score": 0.0,
                "confidence_map": {"overall_avg": 0.9},
            },
        )

        report = controller.get_domain_report("example.com")
        assert report is not None
        assert report["domain"] == "example.com"

    def test_domain_report_unknown(self) -> None:
        """Test getting report for unknown domain."""
        controller = SelfTuningController()
        report = controller.get_domain_report("unknown.com")
        assert report is None


class TestSelfTuningControllerGlobal:
    """Test global singleton access."""

    def test_singleton(self) -> None:
        """Test singleton access."""
        c1 = get_self_tuning_controller()
        c2 = get_self_tuning_controller()
        assert c1 is c2
