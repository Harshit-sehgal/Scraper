"""Tests for Failure Classification — Ontology-driven extraction failure analysis.

Tests cover:
  - Direct error message classification (DNS, timeout, browser crash)
  - HTTP status code classification (429, 403, 502, 404)
  - HTML/ DOM signal analysis (challenge patterns, CAPTCHA, malformed DOM, empty page)
  - Extraction result analysis (no records, partial extraction, selector decay)
  - Telemetry-based classification
  - Domain intelligence integration
  - Recovery strategy mapping
"""

from __future__ import annotations

import pytest
from app.failure_classification import (
    RECOVERY_STRATEGIES,
    FailureCategory,
    FailureClassification,
    _has_captcha_patterns,
    _has_challenge_patterns,
    _is_malformed_dom,
    classify_failure,
    update_domain_with_failure,
)

# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_domain_intel():
    """Create a minimal mock domain intelligence object."""

    class MockIntel:
        def __init__(self) -> None:
            self.domain = "test.example.com"
            self.failure_history = {}
            self.preferred_strategy = "none"
            self.hydration_delay_ms = 1000
            self.anti_bot_risk = 0.0
            self.success_count = 0
            self.total_fetches = 0
            self.last_updated = 0.0
            self.selector_decay_rate = 0.0

    class MockRegistry:
        def __init__(self) -> None:
            self._cache = {}

        def get_intelligence(self, url):
            if url not in self._cache:
                self._cache[url] = MockIntel()
            return self._cache[url]

    return MockRegistry()


# ═══════════════════════════════════════════════════════════════════════
# Error Message Classification
# ═══════════════════════════════════════════════════════════════════════


class TestErrorClassification:
    def test_classify_dns_failure(self) -> None:
        result = classify_failure(error_message="Temporary failure in name resolution")
        assert result.category == FailureCategory.DNS_RESOLUTION_FAILURE
        assert result.confidence >= 0.9
        assert any(s["signal"] == "dns_error" for s in result.signals)
        assert result.recovery_strategy == "retry_with_dns_flush"

    def test_classify_connection_refused(self) -> None:
        result = classify_failure(error_message="Connection refused by the server")
        assert result.category == FailureCategory.CONNECTION_TIMEOUT
        assert result.confidence >= 0.9
        assert result.recovery_strategy == "increase_timeout"

    def test_classify_timeout_with_low_dom_nodes(self) -> None:
        result = classify_failure(
            error_message="Timed out waiting for page",
            telemetry={"fetch_method": "playwright", "dom_nodes": 30},
        )
        assert result.category == FailureCategory.HYDRATION_FAILURE
        assert result.confidence >= 0.7

    def test_classify_generic_timeout(self) -> None:
        result = classify_failure(
            error_message="Timed out waiting for response",
            telemetry={"fetch_method": "httpx", "dom_nodes": 500},
        )
        assert result.category == FailureCategory.TIMEOUT
        assert result.confidence >= 0.7

    def test_classify_browser_crash(self) -> None:
        result = classify_failure(error_message="Browser target closed unexpectedly")
        assert result.category == FailureCategory.BROWSER_CRASH
        assert result.confidence >= 0.9
        assert result.recovery_strategy == "restart_browser"

    def test_classify_empty_error_message(self) -> None:
        result = classify_failure()
        assert result.category == FailureCategory.UNKNOWN
        assert result.confidence < 0.5

    def test_classify_error_with_similar_keywords(self) -> None:
        """'connection' in a non-network context should not misclassify."""
        result = classify_failure(error_message="Could not find connection element in DOM")
        assert result.category != FailureCategory.CONNECTION_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════
# HTTP Status Code Classification
# ═══════════════════════════════════════════════════════════════════════


class TestHttpStatusCodeClassification:
    def test_rate_limited_429(self) -> None:
        result = classify_failure(status_code=429)
        assert result.category == FailureCategory.RATE_LIMITED
        assert result.confidence >= 0.9
        assert result.recovery_strategy == "backoff_and_slow"

    def test_forbidden_with_challenge(self) -> None:
        html = "<html>Checking your browser before accessing. cf-browser-verification</html>"
        result = classify_failure(status_code=403, html=html)
        assert result.category == FailureCategory.ANTI_BOT_BLOCK
        assert result.confidence >= 0.8

    def test_forbidden_without_challenge(self) -> None:
        html = "<html><body>Your IP is not permitted</body></html>"
        result = classify_failure(status_code=403, html=html)
        assert result.category == FailureCategory.IP_BANNED
        assert result.confidence >= 0.7

    def test_unauthorized_401(self) -> None:
        result = classify_failure(status_code=401)
        assert result.category == FailureCategory.IP_BANNED

    def test_server_error_502(self) -> None:
        result = classify_failure(status_code=502)
        assert result.category == FailureCategory.HTTP_ERROR
        assert result.confidence >= 0.8

    def test_server_error_503(self) -> None:
        result = classify_failure(status_code=503)
        assert result.category == FailureCategory.HTTP_ERROR

    def test_not_found_404(self) -> None:
        result = classify_failure(status_code=404)
        assert result.category == FailureCategory.HTTP_ERROR
        assert result.confidence >= 0.7

    def test_status_code_200_should_not_classify(self) -> None:
        """200 is not an error status, should fall through to other signals."""
        result = classify_failure(status_code=200)
        assert result.category == FailureCategory.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════
# HTML / DOM Signal Classification
# ═══════════════════════════════════════════════════════════════════════


class TestHtmlClassification:
    def test_empty_page(self) -> None:
        result = classify_failure(html="<html></html>")
        assert result.category == FailureCategory.EMPTY_PAGE
        assert result.confidence >= 0.8

    def test_challenge_detected(self) -> None:
        html = "<html>Please verify you are human. cf-challenge widget</html>"
        result = classify_failure(html=html, telemetry={"anti_bot_score": 0.9})
        assert result.category == FailureCategory.ANTI_BOT_BLOCK
        assert result.confidence >= 0.9

    def test_challenge_with_low_anti_bot_score(self) -> None:
        html = "<html>Checking your browser before accessing. security check</html>"
        result = classify_failure(html=html, telemetry={"anti_bot_score": 0.5})
        assert result.category == FailureCategory.ANTI_BOT_BLOCK
        assert result.confidence >= 0.7

    def test_captcha_detected(self) -> None:
        html = "<html><div class='g-recaptcha'>captcha</div></html>"
        result = classify_failure(html=html)
        assert result.category == FailureCategory.CAPTCHA
        assert result.confidence >= 0.8

    def test_hcaptcha_detected(self) -> None:
        html = "<html><div h-captcha></div></html>"
        result = classify_failure(html=html)
        assert result.category == FailureCategory.CAPTCHA

    def test_malformed_dom(self) -> None:
        """Severely malformed DOM with too few closing tags vs openings."""
        html = "<div><span><a>lots of open<div>tags<a>no close<span>"
        result = classify_failure(html=html)
        assert result.category == FailureCategory.MALFORMED_DOM
        assert result.confidence >= 0.7

    def test_well_formed_html_should_not_classify_as_malformed(self) -> None:
        # Large enough to not trigger empty page check
        html = "<html><body>" + "<p>OK content here</p>" * 30 + "</body></html>"
        result = classify_failure(html=html)
        # Should fall through to UNKNOWN since no error signals
        assert result.category == FailureCategory.UNKNOWN

    def test_lazy_load_with_low_dom(self) -> None:
        html = "<html><body>" + "<p>Content block here for testing purposes</p>" * 20 + "</body></html>"
        result = classify_failure(
            html=html,
            telemetry={"dom_nodes": 50},
            extraction_result={"method": "regex", "records": [], "selector_success": False},
            fetch_method="playwright",
        )
        # Should be NO_RECORDS_EXTRACTED since extraction returned empty and method was regex
        # (low DOM + regex method gives lazy_load, but check priority)
        assert result.category in (
            FailureCategory.NO_RECORDS_EXTRACTED,
            FailureCategory.LAZY_LOAD_TIMEOUT,
        )


# ═══════════════════════════════════════════════════════════════════════
# Extraction Result Classification
# ═══════════════════════════════════════════════════════════════════════


class TestExtractionResultClassification:
    def test_no_records_from_memory(self) -> None:
        result = classify_failure(
            extraction_result={
                "method": "memory",
                "records": [],
                "selector_success": False,
            },
        )
        assert result.category == FailureCategory.SELECTOR_DECAY
        assert result.confidence >= 0.8
        assert result.recovery_strategy == "force_rediscovery"

    def test_no_records_from_discovery(self) -> None:
        result = classify_failure(
            extraction_result={
                "method": "discovery",
                "records": [],
                "selector_success": False,
            },
        )
        # discovery failure with no selector success should be malformed DOM
        assert result.category in (
            FailureCategory.MALFORMED_DOM,
            FailureCategory.NO_RECORDS_EXTRACTED,
        )

    def test_no_records_generic(self) -> None:
        result = classify_failure(
            extraction_result={
                "method": "regex",
                "records": [],
                "selector_success": True,  # doesn't matter for regex
            },
        )
        assert result.category == FailureCategory.NO_RECORDS_EXTRACTED
        assert result.confidence >= 0.7
        assert result.recovery_strategy == "escalate_to_llm_fallback"

    def test_partial_extraction(self) -> None:
        records = [
            {"company_name": "Acme", "email": "", "phone": ""},
            {"company_name": "Beta", "email": "", "phone": ""},
        ]
        result = classify_failure(
            extraction_result={
                "method": "discovery",
                "records": records,
                "selector_success": True,
                "schema_fields": ["company_name", "email", "phone"],
            },
        )
        # 2 records x 3 fields = 6 slots, only 2 company names filled = 33% < 30%
        assert result.category == FailureCategory.PARTIAL_EXTRACTION
        assert result.confidence >= 0.6


# ═══════════════════════════════════════════════════════════════════════
# Telemetry & Domain Intelligence Classification
# ═══════════════════════════════════════════════════════════════════════


class TestTelemetryAndDomainClassification:
    def test_high_anti_bot_no_html(self) -> None:
        result = classify_failure(
            telemetry={"anti_bot_score": 0.8},
        )
        assert result.category == FailureCategory.ANTI_BOT_BLOCK
        assert result.confidence >= 0.7

    def test_low_anti_bot_no_html(self) -> None:
        result = classify_failure(
            telemetry={"anti_bot_score": 0.3},
        )
        assert result.category == FailureCategory.UNKNOWN

    def test_low_selector_hit_with_fallback(self) -> None:
        result = classify_failure(
            telemetry={
                "fallback_usage": "regex",
                "selector_hit_rate": 0.2,
            },
        )
        assert result.category == FailureCategory.SELECTOR_MISMATCH
        assert result.confidence >= 0.6

    def test_high_selector_decay_rate(self) -> None:
        result = classify_failure(
            domain_intel={"selector_decay_rate": 0.8},
        )
        assert result.category == FailureCategory.SELECTOR_DECAY
        assert result.confidence >= 0.5


# ═══════════════════════════════════════════════════════════════════════
# Recovery Strategy Mapping
# ═══════════════════════════════════════════════════════════════════════


class TestRecoveryStrategies:
    def test_all_categories_have_recovery_strategies(self) -> None:
        for category in FailureCategory:
            assert category in RECOVERY_STRATEGIES, f"Missing recovery strategy for {category.value}"

    def test_all_recovery_strategies_have_required_keys(self) -> None:
        for category, strategy in RECOVERY_STRATEGIES.items():
            assert "strategy" in strategy, f"Missing 'strategy' for {category.value}"
            assert "params" in strategy, f"Missing 'params' for {category.value}"
            assert "description" in strategy, f"Missing 'description' for {category.value}"
            assert isinstance(strategy["params"], dict), f"'params' must be dict for {category.value}"

    def test_unknown_fallback(self) -> None:
        result = classify_failure()
        assert result.recovery_strategy == "retry_with_diagnostics"
        assert result.recovery_params.get("run_diagnostics") is True


# ═══════════════════════════════════════════════════════════════════════
# Domain Intelligence Integration
# ═══════════════════════════════════════════════════════════════════════


class TestDomainIntelligenceIntegration:
    def test_update_domain_with_failure(self, mock_domain_intel) -> None:
        result = FailureClassification(
            category=FailureCategory.SELECTOR_DECAY,
            confidence=0.9,
        )
        update_domain_with_failure(mock_domain_intel, "https://test.example.com/page", result)

        intel = mock_domain_intel.get_intelligence("https://test.example.com/page")
        assert intel.failure_history.get("selector_decay") == 1

    def test_repeated_failure_adjusts_strategy(self, mock_domain_intel) -> None:
        """After 3+ selector_decay failures, strategy should switch to 'discovery'."""
        intel = mock_domain_intel.get_intelligence("https://test.example.com/page")
        intel.preferred_strategy = "memory"

        for _ in range(3):
            result = FailureClassification(
                category=FailureCategory.SELECTOR_DECAY,
                confidence=0.9,
            )
            update_domain_with_failure(mock_domain_intel, "https://test.example.com/page", result)

        assert intel.failure_history.get("selector_decay", 0) >= 3
        assert intel.preferred_strategy == "discovery"

    def test_repeated_anti_bot_adjusts_strategy(self, mock_domain_intel) -> None:
        """After 3+ anti_bot_block failures, strategy should switch to 'httpx'."""
        intel = mock_domain_intel.get_intelligence("https://bot.example.com/page")
        intel.preferred_strategy = "playwright"

        for _ in range(3):
            result = FailureClassification(
                category=FailureCategory.ANTI_BOT_BLOCK,
                confidence=0.9,
            )
            update_domain_with_failure(mock_domain_intel, "https://bot.example.com/page", result)

        assert intel.preferred_strategy == "httpx"

    def test_repeated_hydration_failure_delays_increase(self, mock_domain_intel) -> None:
        """After 3+ hydration failures, delay should increase."""
        intel = mock_domain_intel.get_intelligence("https://slow.example.com/page")
        original_delay = intel.hydration_delay_ms

        for _ in range(3):
            result = FailureClassification(
                category=FailureCategory.HYDRATION_FAILURE,
                confidence=0.9,
            )
            update_domain_with_failure(mock_domain_intel, "https://slow.example.com/page", result)

        assert intel.hydration_delay_ms > original_delay


# ═══════════════════════════════════════════════════════════════════════
# Detection Pattern Helpers
# ═══════════════════════════════════════════════════════════════════════


class TestDetectionPatterns:
    def test_has_challenge_patterns_cloudflare(self) -> None:
        assert _has_challenge_patterns("<html>cf-browser-verification widget</html>")
        assert _has_challenge_patterns("<html>Checking your browser before accessing</html>")

    def test_has_challenge_patterns_datadome(self) -> None:
        assert _has_challenge_patterns("<html>datadome security check</html>")

    def test_has_challenge_patterns_negative(self) -> None:
        assert not _has_challenge_patterns("<html>normal content</html>")

    def test_has_captcha_patterns_recaptcha(self) -> None:
        assert _has_captcha_patterns('<html><div class="g-recaptcha"></div></html>')
        assert _has_captcha_patterns("<html>i'm not a robot</html>")

    def test_has_captcha_patterns_negative(self) -> None:
        assert not _has_captcha_patterns("<html>normal content</html>")

    def test_is_malformed_dom_high_ratio(self) -> None:
        """DOM with very few closing tags."""
        assert _is_malformed_dom("<div><span><a>lots<div>of open<a>tags<span>everywhere<div>")

    def test_is_malformed_dom_low_ratio(self) -> None:
        """Well-formed DOM should not be classified as malformed."""
        assert not _is_malformed_dom("<html><body><div><p>normal</p></div></body></html>")

    def test_is_malformed_dom_no_html(self) -> None:
        assert not _is_malformed_dom("")
        assert not _is_malformed_dom("some plain text with no tags")


class TestExceptionTranslation:
    def test_exception_translations(self) -> None:
        from app.failure_classification import translate_exception_to_friendly_message

        # Test crawl timeouts
        msg1 = translate_exception_to_friendly_message("Playwright Navigation Timeout: goto failed after 30000ms")
        assert "Crawl Timeout" in msg1

        # Test wait timeouts
        msg2 = translate_exception_to_friendly_message("Timeout waiting for selector .loader to be hidden")
        assert "Wait Timeout" in msg2

        # Test DNS resolution
        msg3 = translate_exception_to_friendly_message("dns_lookup_failed: Could not resolve address")
        assert "DNS Lookup Failed" in msg3

        # Test connections
        msg4 = translate_exception_to_friendly_message("ConnectionRefusedError: server rejected port 80")
        assert "Connection Refused" in msg4

        # Test anti-bot defenses
        msg5 = translate_exception_to_friendly_message("Cloudflare DDoS challenge active")
        assert "Anti-Bot Defense Block" in msg5

        # Test browser crashes
        msg6 = translate_exception_to_friendly_message("Playwright crash: target context was closed")
        assert "Browser Context Reset" in msg6

        # Test unknown system exceptions
        msg7 = translate_exception_to_friendly_message("ValueError: some strange python error")
        assert "Extraction Impediment" in msg7
