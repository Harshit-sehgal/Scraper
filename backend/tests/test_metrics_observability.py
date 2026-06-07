"""Tests for the new Prometheus-export metrics (observability).

The deep-research report's *Monitoring target* section lists:
- extraction method distribution
- anti-bot classifications
- export generation failures
- browser launch failures
- SSRF validation rejects
- repository query latency

These tests pin the corresponding record_*/get_* helpers in
``app.metrics_collector`` and the wiring into the
``/api/system/storage/status`` / ``/metrics`` endpoints.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def reset_metrics():
    from app.metrics_collector import reset_for_testing

    reset_for_testing()
    yield
    reset_for_testing()


class TestExtractionMethodCounts:
    def test_record_and_get(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_extraction_method_counts,
            record_extraction_method,
        )

        record_extraction_method("network")
        record_extraction_method("network")
        record_extraction_method("regex")
        counts = get_extraction_method_counts()
        assert counts == {"network": 2, "regex": 1}

    def test_empty_string_ignored(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_extraction_method_counts,
            record_extraction_method,
        )

        record_extraction_method("")
        assert get_extraction_method_counts() == {}


class TestAntiBotClassifications:
    def test_record_and_get(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_anti_bot_classifications,
            record_anti_bot_classification,
        )

        record_anti_bot_classification("captcha")
        record_anti_bot_classification("captcha")
        record_anti_bot_classification("ok")
        counts = get_anti_bot_classifications()
        assert counts == {"captcha": 2, "ok": 1}


class TestExportOutcomes:
    def test_record_and_get(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_export_outcomes,
            record_export_outcome,
        )

        record_export_outcome("csv", True)
        record_export_outcome("csv", True)
        record_export_outcome("csv", False)
        record_export_outcome("excel", True)
        outcomes = get_export_outcomes()
        assert outcomes == {"csv": {"success": 2, "failure": 1}, "excel": {"success": 1, "failure": 0}}


class TestBrowserLaunchOutcomes:
    def test_record_and_get(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_browser_launch_outcomes,
            record_browser_launch,
        )

        record_browser_launch(True)
        record_browser_launch(False)
        record_browser_launch(False)
        outcomes = get_browser_launch_outcomes()
        assert outcomes == {"success": 1, "failure": 2}


class TestSsrfRejects:
    def test_record_and_get(self, reset_metrics) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("loopback_name")
        record_ssrf_reject("loopback_name")
        record_ssrf_reject("cloud_metadata")
        counts = get_ssrf_rejects()
        assert counts == {"loopback_name": 2, "cloud_metadata": 1}

    def test_empty_reason_normalised(self, reset_metrics) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("")
        counts = get_ssrf_rejects()
        assert counts == {"unspecified": 1}


class TestRepoQueryLatency:
    def test_record_and_get_ring_buffer(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_repo_query_latencies,
            record_repo_query_latency,
        )

        for i in range(5):
            record_repo_query_latency(float(i) / 1000.0)
        latencies = get_repo_query_latencies()
        assert latencies == [0.0, 0.001, 0.002, 0.003, 0.004]

    def test_ring_buffer_is_capped(self, reset_metrics) -> None:
        from app.metrics_collector import (
            _MAX_METRIC_SAMPLES,
            get_repo_query_latencies,
            record_repo_query_latency,
        )

        for i in range(_MAX_METRIC_SAMPLES + 50):
            record_repo_query_latency(float(i) / 1000.0)
        assert len(get_repo_query_latencies()) == _MAX_METRIC_SAMPLES


class TestMetricsEndpointExposesNewGauges:
    def test_metrics_endpoint_contains_extraction_method(self, client, reset_metrics) -> None:
        from app.metrics_collector import (
            get_extraction_method_counts,
            record_extraction_method,
        )

        record_extraction_method("network")
        record_extraction_method("network")
        record_extraction_method("regex")
        # Sanity: the recorder actually mutated the global state.
        assert get_extraction_method_counts() == {"network": 2, "regex": 1}
        r = client.get("/metrics")
        assert r.status_code in (200, 401, 403)
        if r.status_code == 200:
            text = r.text
            assert "dataforge_extraction_method_total" in text, text

    def test_metrics_endpoint_contains_export_outcomes(self, client, reset_metrics) -> None:
        from app.metrics_collector import (
            get_export_outcomes,
            record_export_outcome,
        )

        record_export_outcome("csv", True)
        record_export_outcome("csv", False)
        assert get_export_outcomes() == {"csv": {"success": 1, "failure": 1}}
        r = client.get("/metrics")
        if r.status_code == 200:
            assert "dataforge_export_outcomes_total" in r.text, r.text


class TestExtractionMethodCallSiteWiring:
    """The scraper engine must invoke record_extraction_method at every
    convergence point. These tests pin the wiring without spinning up a
    full scrape.
    """

    def test_safe_helper_no_op_on_none(self) -> None:
        from app.scraper import _record_extraction_method_safe

        # Should not raise.
        _record_extraction_method_safe(None)
        _record_extraction_method_safe("")

    def test_safe_helper_records_non_empty(self, reset_metrics) -> None:
        from app.metrics_collector import get_extraction_method_counts
        from app.scraper import _record_extraction_method_safe

        _record_extraction_method_safe("regex")
        assert get_extraction_method_counts() == {"regex": 1}


class TestAntiBotClassificationCallSiteWiring:
    """The scraper engine + classifiers must invoke
    record_anti_bot_classification from the per-request and per-classification
    paths. These tests pin the wiring without spinning up a full scrape.
    """

    def test_failure_classification_records_anti_bot_block(self, reset_metrics) -> None:
        from app.failure_classification import (
            FailureCategory,
            _build_classification,
        )
        from app.metrics_collector import get_anti_bot_classifications

        _build_classification(FailureCategory.ANTI_BOT_BLOCK, 0.9, [])
        _build_classification(FailureCategory.CAPTCHA, 0.85, [])
        _build_classification(FailureCategory.RATE_LIMITED, 0.95, [])
        counts = get_anti_bot_classifications()
        assert counts.get("anti_bot_block") == 1
        assert counts.get("captcha") == 1
        assert counts.get("rate_limited") == 1

    def test_failure_classification_skips_non_anti_bot(self, reset_metrics) -> None:
        from app.failure_classification import (
            FailureCategory,
            _build_classification,
        )
        from app.metrics_collector import get_anti_bot_classifications

        _build_classification(FailureCategory.DNS_RESOLUTION_FAILURE, 0.95, [])
        _build_classification(FailureCategory.BROWSER_CRASH, 0.9, [])
        assert get_anti_bot_classifications() == {}

    def test_zero_result_classifier_records_anti_bot_block(self, reset_metrics) -> None:
        from app.metrics_collector import get_anti_bot_classifications
        from app.zero_result_classifier import _build

        _build("anti_bot_block", 0.85)
        _build("empty_response", 0.95)
        _build("genuinely_empty", 0.60)  # NOT an anti-bot class
        counts = get_anti_bot_classifications()
        assert counts.get("anti_bot_block") == 1
        assert counts.get("empty_response") == 1
        assert "genuinely_empty" not in counts


class TestRateLimitHitCounters:
    """Rate limit hit counters exposed as Prometheus metrics."""

    def test_record_global_hit(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_rate_limit_global_hits,
            record_rate_limit_global_hit,
        )

        assert get_rate_limit_global_hits() == 0
        record_rate_limit_global_hit()
        assert get_rate_limit_global_hits() == 1
        record_rate_limit_global_hit()
        assert get_rate_limit_global_hits() == 2

    def test_record_per_ip_hit(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_rate_limit_per_ip_hits,
            record_rate_limit_per_ip_hit,
        )

        assert get_rate_limit_per_ip_hits() == 0
        record_rate_limit_per_ip_hit()
        record_rate_limit_per_ip_hit()
        record_rate_limit_per_ip_hit()
        assert get_rate_limit_per_ip_hits() == 3

    def test_reset_clears_both_counters(self, reset_metrics) -> None:
        from app.metrics_collector import (
            get_rate_limit_global_hits,
            get_rate_limit_per_ip_hits,
            record_rate_limit_global_hit,
            record_rate_limit_per_ip_hit,
            reset_for_testing,
        )

        record_rate_limit_global_hit()
        record_rate_limit_per_ip_hit()
        assert get_rate_limit_global_hits() == 1
        assert get_rate_limit_per_ip_hits() == 1

        reset_for_testing()
        assert get_rate_limit_global_hits() == 0
        assert get_rate_limit_per_ip_hits() == 0

    def test_metrics_endpoint_contains_rate_limit_hits(self, client, reset_metrics) -> None:
        from app.metrics_collector import (
            record_rate_limit_global_hit,
            record_rate_limit_per_ip_hit,
        )

        record_rate_limit_global_hit()
        record_rate_limit_per_ip_hit()
        record_rate_limit_per_ip_hit()

        r = client.get("/metrics")
        assert r.status_code in (200, 401, 403)
        if r.status_code == 200:
            text = r.text
            assert "dataforge_rate_limit_global_hits_total" in text, text
            assert "dataforge_rate_limit_per_ip_hits_total" in text, text


class TestRateLimitStatsEndpoint:
    """The /api/system/rate-limit-stats endpoint returns expected schema."""

    def test_rate_limit_stats_returns_expected_keys(self, client, monkeypatch) -> None:
        """Verify the response contains all expected schema fields.

        Sets up an admin API key so the request can authenticate against
        the operator/admin-protected endpoint.
        """
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key", raising=False)
        monkeypatch.setattr(settings, "API_KEY", "", raising=False)

        r = client.get(
            "/api/system/rate-limit-stats",
            headers={"X-API-Key": "test-admin-key"},
        )
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        expected_keys = {
            "enabled",
            "global_limit_per_window",
            "global_window_seconds",
            "per_ip_enabled",
            "per_ip_limit_per_window",
            "per_ip_window_seconds",
            "active_keys",
            "route_limits",
        }
        assert expected_keys.issubset(data.keys()), f"Missing keys: {expected_keys - data.keys()}"
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["global_limit_per_window"], int)
        assert isinstance(data["global_window_seconds"], (int, float))
        assert isinstance(data["per_ip_enabled"], bool)
        assert isinstance(data["per_ip_limit_per_window"], int)
        assert isinstance(data["per_ip_window_seconds"], (int, float))
        assert isinstance(data["active_keys"], int)
        assert isinstance(data["route_limits"], dict)


class TestAntiBotPlatformDetection:
    """detect_anti_bot_platform must label the matched platform; ok otherwise."""

    def test_clean_html_returns_ok(self) -> None:
        from app.scrape_telemetry import detect_anti_bot_platform

        html = "<html><body><h1>Hello, world</h1><p>Lorem ipsum.</p></body></html>"
        assert detect_anti_bot_platform(html) == "ok"

    def test_cloudflare_challenge_returns_cloudflare(self) -> None:
        from app.scrape_telemetry import detect_anti_bot_platform

        html = "<html><body>cf-browser-verification: please wait</body></html>"
        assert detect_anti_bot_platform(html) == "cloudflare"

    def test_captcha_returns_captcha(self) -> None:
        from app.scrape_telemetry import detect_anti_bot_platform

        html = '<html><body><div class="g-recaptcha" data-sitekey="x"></div></body></html>'
        assert detect_anti_bot_platform(html) == "captcha"

    def test_rate_limit_returns_rate_limit(self) -> None:
        from app.scrape_telemetry import detect_anti_bot_platform

        html = "<html><body>429 too many requests — try again later</body></html>"
        assert detect_anti_bot_platform(html) == "rate_limit"

    def test_empty_html_returns_ok(self) -> None:
        from app.scrape_telemetry import detect_anti_bot_platform

        assert detect_anti_bot_platform("") == "ok"
