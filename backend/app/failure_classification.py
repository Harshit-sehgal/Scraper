"""Failure Classification — Ontology-driven extraction failure analysis.

Provides:
  - A formal failure ontology (FailureCategory enum) covering all known
    extraction failure modes encountered in hostile web environments.
  - A classifier that inspects telemetry, DOM characteristics, and
    extraction results to determine the most likely failure category.
  - Recovery strategy generation: given a failure class, recommend the
    optimal next action (retry, backoff, switch strategy, rotate proxy, etc.).
  - Integration points: domain_intelligence adapts per-domain failure patterns,
    telemetry captures classification outcomes, and the scraper pipeline
    invokes classification on low-quality or empty results.

Every extraction failure should be classified where practical. Generic failures
hide actionable signal. Classification enables automated recovery decisions.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Failure Ontology
# ═══════════════════════════════════════════════════════════════════════


class FailureCategory(StrEnum):
    """Formal ontology of all known extraction failure modes.

    Each category maps to a distinct physical root cause in the
    extraction pipeline, enabling targeted recovery strategies.
    """

    # ── Fetch / Transport Layer ──────────────────────────────────────
    HYDRATION_FAILURE = "hydration_failure"
    """Page JS never finished rendering — DOM was incomplete or empty."""

    LAZY_LOAD_TIMEOUT = "lazy_load_timeout"
    """Content was loaded lazily and never appeared within the timeout."""

    RENDER_STARVATION = "render_starvation"
    """Browser ran out of memory or CPU time to complete rendering."""

    DNS_RESOLUTION_FAILURE = "dns_resolution_failure"
    """Could not resolve the domain."""

    CONNECTION_TIMEOUT = "connection_timeout"
    """TCP / TLS handshake or initial connection timed out."""

    HTTP_ERROR = "http_error"
    """Server returned a non-2xx status code (4xx, 5xx)."""

    # ── Anti-Bot Layer ───────────────────────────────────────────────
    ANTI_BOT_BLOCK = "anti_bot_block"
    """Detected a challenge page (Cloudflare, DataDome, etc.)."""

    CAPTCHA = "captcha"
    """A CAPTCHA or interactive challenge was presented."""

    IP_BANNED = "ip_banned"
    """The source IP has been permanently or temporarily banned."""

    RATE_LIMITED = "rate_limited"
    """Rate-limited by the server (429 Too Many Requests)."""

    # ── Extraction Layer ─────────────────────────────────────────────
    SELECTOR_DECAY = "selector_decay"
    """Previously successful selectors no longer match the DOM."""

    SELECTOR_MISMATCH = "selector_mismatch"
    """Selectors matched DOM elements but extracted semantically wrong data."""

    MALFORMED_DOM = "malformed_dom"
    """The DOM structure was too broken or irregular for extraction."""

    EMPTY_PAGE = "empty_page"
    """The page had no meaningful content (blank, placeholder, or skeleton)."""

    NO_RECORDS_EXTRACTED = "no_records_extracted"
    """All extraction methods returned zero records."""

    LOW_QUALITY_EXTRACTION = "low_quality_extraction"
    """Records were extracted but all scored below the quality threshold."""

    PARTIAL_EXTRACTION = "partial_extraction"
    """Only a subset of expected fields were populated."""

    # ── Semantic / Processing Layer ──────────────────────────────────
    SEMANTIC_MISMATCH = "semantic_mismatch"
    """LLM-structured data does not match the expected schema."""

    FIELD_SWAP = "field_swap"
    """LLM or selector mistakenly swapped two or more fields."""

    HALLUCINATION = "hallucination"
    """LLM invented data that was not present in the source."""

    # ── Infrastructure / System ──────────────────────────────────────
    BROWSER_CRASH = "browser_crash"
    """Playwright browser or context crashed during fetch."""

    TIMEOUT = "timeout"
    """Generic timeout — no more specific category matched."""

    UNKNOWN = "unknown"
    """Catch-all for unclassifiable failures."""


# ═══════════════════════════════════════════════════════════════════════
# Failure Classification Result
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class FailureClassification:
    """Result of classifying an extraction attempt."""

    category: FailureCategory = FailureCategory.UNKNOWN
    confidence: float = 0.0
    """How confident the classifier is in this classification [0, 1]."""

    signals: list[dict] = field(default_factory=list)
    """Specific signals that triggered this classification."""

    recovery_strategy: str = "retry"
    """Recommended recovery strategy name."""

    recovery_params: dict[str, Any] = field(default_factory=dict)
    """Parameters for the recovery strategy (delay_ms, rotate_proxy, etc.)."""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["category"] = self.category.value
        return result


# ═══════════════════════════════════════════════════════════════════════
# Recovery Strategy Definitions
# ═══════════════════════════════════════════════════════════════════════

RECOVERY_STRATEGIES: dict[FailureCategory, dict] = {
    FailureCategory.HYDRATION_FAILURE: {
        "strategy": "increase_hydration_wait",
        "params": {"extra_delay_ms": 3000},
        "description": "Increase JS settle delay and wait for specific selectors.",
    },
    FailureCategory.LAZY_LOAD_TIMEOUT: {
        "strategy": "scroll_and_wait",
        "params": {"scroll_attempts": 5, "scroll_delay_ms": 1000},
        "description": "Trigger additional scroll events to force lazy loading.",
    },
    FailureCategory.RENDER_STARVATION: {
        "strategy": "reduce_concurrency",
        "params": {"max_contexts": 3},
        "description": "Reduce browser concurrency to free resources.",
    },
    FailureCategory.DNS_RESOLUTION_FAILURE: {
        "strategy": "retry_with_dns_flush",
        "params": {"delay_ms": 2000, "max_retries": 2},
        "description": "Retry after a brief delay; DNS may be transient.",
    },
    FailureCategory.CONNECTION_TIMEOUT: {
        "strategy": "increase_timeout",
        "params": {"timeout_ms": 30000},
        "description": "Increase connection timeout and retry.",
    },
    FailureCategory.HTTP_ERROR: {
        "strategy": "examine_status",
        "params": {"delay_ms": 5000, "max_retries": 1},
        "description": "Check status code; retry once after delay for 5xx.",
    },
    FailureCategory.ANTI_BOT_BLOCK: {
        "strategy": "rotate_and_backoff",
        "params": {"delay_ms": 15000, "rotate_proxy": True},
        "description": "Back off significantly, optionally rotate IP / identity.",
    },
    FailureCategory.CAPTCHA: {
        "strategy": "abort",
        "params": {"skip_domain_minutes": 30},
        "description": "Abort — CAPTCHA requires human intervention or solver.",
    },
    FailureCategory.IP_BANNED: {
        "strategy": "rotate_proxy",
        "params": {"rotate_proxy": True, "delay_ms": 60000},
        "description": "Rotate IP proxy and wait before retrying.",
    },
    FailureCategory.RATE_LIMITED: {
        "strategy": "backoff_and_slow",
        "params": {"delay_ms": 30000, "slow_factor": 0.5},
        "description": "Back off and reduce request rate to this domain.",
    },
    FailureCategory.SELECTOR_DECAY: {
        "strategy": "force_rediscovery",
        "params": {"bypass_memory": True},
        "description": "Bypass selector memory and force LLM re-discovery.",
    },
    FailureCategory.SELECTOR_MISMATCH: {
        "strategy": "force_rediscovery_with_swap_detection",
        "params": {"enable_swap_detection": True, "bypass_memory": True},
        "description": "Re-discover selectors with field-swap detection enabled.",
    },
    FailureCategory.MALFORMED_DOM: {
        "strategy": "use_httpx_fallback",
        "params": {"prefer_httpx": True},
        "description": "Fall back to httpx (no JS) which may return cleaner HTML.",
    },
    FailureCategory.EMPTY_PAGE: {
        "strategy": "verify_url",
        "params": {"check_redirect": True},
        "description": "Verify the URL is correct and not a redirect to a blank page.",
    },
    FailureCategory.NO_RECORDS_EXTRACTED: {
        "strategy": "escalate_to_llm_fallback",
        "params": {"force_llm_discovery": True},
        "description": "Escalate directly to LLM-based extraction.",
    },
    FailureCategory.LOW_QUALITY_EXTRACTION: {
        "strategy": "lower_threshold_and_reprocess",
        "params": {"score_multiplier": 0.7},
        "description": "Lower quality threshold and re-process existing records.",
    },
    FailureCategory.PARTIAL_EXTRACTION: {
        "strategy": "retry_with_field_focus",
        "params": {"focus_fields": True},
        "description": "Retry extraction with emphasis on missing fields.",
    },
    FailureCategory.SEMANTIC_MISMATCH: {
        "strategy": "reclean_with_schema_hint",
        "params": {"apply_schema_validation": True},
        "description": "Re-run AI cleaning with stronger schema hints.",
    },
    FailureCategory.FIELD_SWAP: {
        "strategy": "align_swapped_fields",
        "params": {"detect_swaps": True},
        "description": "Detect and correct field swaps in extraction results.",
    },
    FailureCategory.HALLUCINATION: {
        "strategy": "revalidate_with_source",
        "params": {"require_source_evidence": True},
        "description": "Re-validate extracted values against source HTML.",
    },
    FailureCategory.BROWSER_CRASH: {
        "strategy": "restart_browser",
        "params": {"restart_context": True},
        "description": "Restart the browser context and retry.",
    },
    FailureCategory.TIMEOUT: {
        "strategy": "increase_timeout_and_retry",
        "params": {"timeout_multiplier": 2.0},
        "description": "Increase all timeouts by a multiplier and retry.",
    },
    FailureCategory.UNKNOWN: {
        "strategy": "retry_with_diagnostics",
        "params": {"run_diagnostics": True},
        "description": "Retry with full diagnostics enabled for analysis.",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Classifier
# ═══════════════════════════════════════════════════════════════════════


def classify_failure(
    telemetry: dict | None = None,
    html: str | None = None,
    extraction_result: dict | None = None,
    domain_intel: dict | None = None,
    status_code: int | None = None,
    error_message: str | None = None,
    fetch_method: str | None = None,  # noqa: ARG001, RUF100
) -> FailureClassification:
    """Classify an extraction failure based on available signals.

    Args:
        telemetry: ScrapeTelemetry dict (or None if fetch failed entirely).
        html: Raw HTML string (or None if fetch failed).
        extraction_result: ExtractionResult dict (method, records, selectors).
        domain_intel: DomainIntelligence dict of the target domain.
        status_code: HTTP status code (if available).
        error_message: Error message string from the failing component.
        fetch_method: The fetch method used ("playwright" or "httpx").

    Returns:
        A FailureClassification with the best-guess category, confidence,
        and recommended recovery strategy.

    """
    signals: list[dict] = []
    error_text = (error_message or "").lower()
    telemetry = telemetry or {}
    domain_intel = domain_intel or {}

    # ── Stage 1: Fast-path classification from error messages ─────────
    # These are strong signals that often directly indicate the category.

    # DNS / Connection errors
    if any(
        kw in error_text
        for kw in [
            "dns",
            "name resolution",
            "nodename nor servname",
            "temporary failure in name resolution",
        ]
    ):
        signals.append({"signal": "dns_error", "source": "error_message"})
        return _build_classification(FailureCategory.DNS_RESOLUTION_FAILURE, 0.95, signals)

    if any(
        kw in error_text
        for kw in [
            "connection refused",
            "connection reset",
            "connection timed out",
            "connection closed",
            "econnrefused",
            "econnreset",
        ]
    ):
        signals.append({"signal": "connection_error", "source": "error_message"})
        return _build_classification(FailureCategory.CONNECTION_TIMEOUT, 0.90, signals)

    if any(
        kw in error_text
        for kw in [
            "timeout",
            "timed out",
            "deadline exceeded",
        ]
    ):
        signals.append({"signal": "timeout", "source": "error_message"})
        # Could be multiple categories; check for hydration specifics
        if (
            telemetry.get("fetch_method") == "playwright"
            and telemetry.get("dom_nodes", 0) < settings.CLASSIFY_HYDRATION_DOM_THRESHOLD
        ):
            return _build_classification(FailureCategory.HYDRATION_FAILURE, 0.75, signals)
        return _build_classification(FailureCategory.TIMEOUT, 0.70, signals)

    if any(
        kw in error_text
        for kw in [
            "browser",
            "crash",
            "target closed",
            "protocol error",
            "page.navigate",
            "browser context",
        ]
    ):
        signals.append({"signal": "browser_crash", "source": "error_message"})
        return _build_classification(FailureCategory.BROWSER_CRASH, 0.90, signals)

    # Selector decay / empty extraction failure
    if any(
        kw in error_text
        for kw in [
            "zero_records_extracted",
            "no records extracted",
            "selector decay",
            "empty page",
        ]
    ):
        signals.append({"signal": "selector_decay_msg", "source": "error_message"})
        return _build_classification(FailureCategory.SELECTOR_DECAY, 0.85, signals)

    # Anti-bot block / WAF
    if any(
        kw in error_text
        for kw in [
            "403 forbidden",
            "forbidden",
            "waf challenge",
            "anti-bot",
            "cloudflare",
            "captcha",
            "ip banned",
            "access denied",
        ]
    ):
        signals.append({"signal": "anti_bot_msg", "source": "error_message"})
        return _build_classification(FailureCategory.ANTI_BOT_BLOCK, 0.90, signals)

    # ── Stage 2: HTTP Status Code Analysis ────────────────────────────
    if status_code is not None:
        if status_code == 429:
            signals.append({"signal": "http_429", "source": "status_code"})
            return _build_classification(FailureCategory.RATE_LIMITED, 0.95, signals)
        if status_code in (403, 401):
            signals.append({"signal": f"http_{status_code}", "source": "status_code"})
            # Could be anti-bot or IP ban — check for challenge patterns in
            # HTML
            if html and _has_challenge_patterns(html):
                return _build_classification(FailureCategory.ANTI_BOT_BLOCK, 0.85, signals)
            return _build_classification(FailureCategory.IP_BANNED, 0.70, signals)
        if status_code in (502, 503, 504):
            signals.append({"signal": f"http_{status_code}", "source": "status_code"})
            return _build_classification(FailureCategory.HTTP_ERROR, 0.80, signals)
        if status_code == 404:
            signals.append({"signal": "http_404", "source": "status_code"})
            return _build_classification(FailureCategory.HTTP_ERROR, 0.75, signals)

    # ── Stage 3: HTML / DOM Signal Analysis ──────────────────────────
    if html is not None:
        # Anti-bot challenge patterns (check BEFORE empty page, since challenge
        # pages can be short but are clearly not "empty")
        if _has_challenge_patterns(html):
            signals.append({"signal": "challenge_detected", "source": "html_patterns"})
            anti_bot_score = telemetry.get("anti_bot_score", 0.0)
            if anti_bot_score > 0.8:
                return _build_classification(FailureCategory.ANTI_BOT_BLOCK, 0.90, signals)
            return _build_classification(FailureCategory.ANTI_BOT_BLOCK, 0.75, signals)

        # CAPTCHA patterns
        if _has_captcha_patterns(html):
            signals.append({"signal": "captcha_detected", "source": "html_patterns"})
            return _build_classification(FailureCategory.CAPTCHA, 0.85, signals)

        # Malformed DOM — very few closing tags, very irregular
        if _is_malformed_dom(html):
            signals.append({"signal": "malformed_dom", "source": "html_structure"})
            return _build_classification(FailureCategory.MALFORMED_DOM, 0.70, signals)

        # Empty or near-empty page (checked AFTER challenge / malformed patterns
        # since challenge pages can also be short but aren't "empty")
        if len(html.strip()) < settings.CLASSIFY_EMPTY_PAGE_HTML_THRESHOLD:
            signals.append({"signal": "tiny_html", "source": "html_size"})
            return _build_classification(FailureCategory.EMPTY_PAGE, 0.85, signals)

        # Lazy load indicators with few records
        dom_nodes = telemetry.get("dom_nodes", 0)
        extraction_method = (extraction_result or {}).get("method", "")
        if dom_nodes < settings.CLASSIFY_LAZYLOAD_DOM_THRESHOLD and extraction_method == "regex":
            signals.append({"signal": "low_dom_count", "source": "dom_analysis"})
            return _build_classification(FailureCategory.LAZY_LOAD_TIMEOUT, 0.65, signals)

    # ── Stage 4: Extraction Result Analysis ───────────────────────────
    if extraction_result is not None:
        method = extraction_result.get("method", "")
        records = extraction_result.get("records", [])
        selector_success = extraction_result.get("selector_success", False)

        if not records:
            signals.append({"signal": "no_records", "source": "extraction_result"})
            if method == "memory":
                return _build_classification(FailureCategory.SELECTOR_DECAY, 0.80, signals)
            if method == "discovery" and not selector_success:
                return _build_classification(FailureCategory.MALFORMED_DOM, 0.60, signals)
            return _build_classification(FailureCategory.NO_RECORDS_EXTRACTED, 0.70, signals)

        # Check for partial extraction (too many empty fields)
        if _is_partial_extraction(records, extraction_result.get("schema_fields", [])):
            signals.append({"signal": "partial_extraction", "source": "field_analysis"})
            return _build_classification(FailureCategory.PARTIAL_EXTRACTION, 0.65, signals)

    # ── Stage 5: Telemetry-based heuristics ───────────────────────────
    if telemetry:
        anti_bot_score = telemetry.get("anti_bot_score", 0.0)
        if anti_bot_score > settings.CLASSIFY_ANTIBOT_SCORE_THRESHOLD and not html:
            signals.append({"signal": "high_anti_bot_no_html", "source": "telemetry"})
            return _build_classification(FailureCategory.ANTI_BOT_BLOCK, 0.70, signals)

        fallback = telemetry.get("fallback_usage", "none")
        selector_hit = telemetry.get("selector_hit_rate", 1.0)
        if fallback != "none" and selector_hit < settings.CLASSIFY_LOW_SELECTOR_HIT_THRESHOLD:
            signals.append({"signal": "low_selector_hit", "source": "telemetry"})
            return _build_classification(FailureCategory.SELECTOR_MISMATCH, 0.60, signals)

    # ── Stage 6: Fallback to domain intelligence patterns ─────────────
    if domain_intel:
        decay_rate = domain_intel.get("selector_decay_rate", 0.0)
        if decay_rate > settings.CLASSIFY_DECAY_RATE_THRESHOLD:
            signals.append({"signal": "high_decay_rate", "source": "domain_intel"})
            return _build_classification(FailureCategory.SELECTOR_DECAY, 0.55, signals)

    # ── Default ───────────────────────────────────────────────────────
    signals.append({"signal": "no_classification_matched", "source": "fallthrough"})
    return _build_classification(FailureCategory.UNKNOWN, 0.30, signals)


# ═══════════════════════════════════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════════════════════════════════


def _build_classification(
    category: FailureCategory,
    confidence: float,
    signals: list[dict],
) -> FailureClassification:
    """Build a FailureClassification with the appropriate recovery strategy."""
    strategy_def = RECOVERY_STRATEGIES.get(category, RECOVERY_STRATEGIES[FailureCategory.UNKNOWN])

    # Observability: emit anti-bot classification counter for the four
    # categories that map to anti-bot blocks. Categories outside this set
    # (DNS, timeout, browser crash, etc.) are not "anti_bot_classifications"
    # and are tracked separately via dataforge_errors_total.
    try:
        from app.metrics_collector import record_anti_bot_classification

        if category in (
            FailureCategory.ANTI_BOT_BLOCK,
            FailureCategory.CAPTCHA,
            FailureCategory.IP_BANNED,
            FailureCategory.RATE_LIMITED,
        ):
            record_anti_bot_classification(category.value)
    except (ImportError, AttributeError, TypeError, ValueError):
        # Never let observability break classification.
        pass

    return FailureClassification(
        category=category,
        confidence=round(confidence, 3),
        signals=signals,
        recovery_strategy=strategy_def["strategy"],
        recovery_params=strategy_def["params"],
    )


# ─── Detection Patterns ────────────────────────────────────────────────

_CHALLENGE_PATTERNS = [
    "cf-browser-verification",
    "cf-challenge",
    "cf-turnstile",
    "challenge-platform",
    "checking your browser",
    "akamai-ghost",
    "ak_bmsc",
    "bm_sz",
    "dd-captcha",
    "datadome",
    "perimeterx",
    "px-captcha",
    "incapsula",
    "visid_incap",
    "access denied",
    "blocked",
    "sorry, you have been blocked",
    "please verify",
    "security check",
    "suspicious activity",
    "enable javascript",
    "javascript is required",
    "attention required",
    "verify you are human",
]


def _has_challenge_patterns(html: str) -> bool:
    """Check if the HTML contains anti-bot challenge patterns."""
    html_lower = html.lower()
    return any(pattern in html_lower for pattern in _CHALLENGE_PATTERNS)


_CAPTCHA_PATTERNS = [
    "g-recaptcha",
    "h-captcha",
    "recaptcha",
    "captcha",
    "i'm not a robot",
    "image verification",
    "text verification",
    "select all images",
    "enter the characters",
    "captcha-container",
    "captcha_wrapper",
]


def _has_captcha_patterns(html: str) -> bool:
    """Check if the HTML contains CAPTCHA patterns."""
    html_lower = html.lower()
    return any(pattern in html_lower for pattern in _CAPTCHA_PATTERNS)


def _is_malformed_dom(html: str) -> bool:
    """Heuristic: detect severely malformed DOM."""
    import re

    # Count opening vs closing tags
    openings = len(re.findall(r"<[a-zA-Z][^>]*>", html))
    closings = len(re.findall(r"</[a-zA-Z][^>]*>", html))
    if openings == 0:
        return False
    ratio = closings / max(1, openings)
    # If fewer than 30% of tags are closed, likely malformed
    return ratio < settings.CLASSIFY_MALFORMED_DOM_RATIO


def _is_partial_extraction(records: list[dict], schema_fields: list[str]) -> bool:
    """Check if records have too many empty fields (partial extraction)."""
    if not records or not schema_fields:
        return False
    from app.html_utils import _is_empty_value

    total_slots = len(records) * len(schema_fields)
    filled_slots = 0
    for record in records:
        for fname in schema_fields:
            if not _is_empty_value(record.get(fname)):
                filled_slots += 1

    fill_rate = filled_slots / max(1, total_slots)
    return fill_rate < settings.CLASSIFY_PARTIAL_EXTRACTION_FILL_RATE


# ═══════════════════════════════════════════════════════════════════════
# Domain Intelligence Integration
# ═══════════════════════════════════════════════════════════════════════


def update_domain_with_failure(
    domain_intel_registry: Any,
    url: str,
    classification: FailureClassification,
) -> None:
    """Update domain intelligence with failure classification data.

    This gives domains a memory of what types of failures they tend to
    produce, enabling proactive strategy selection on subsequent visits.
    """
    intel = domain_intel_registry.get_intelligence(url)
    category = classification.category.value

    # Track failure count per category
    if not hasattr(intel, "failure_history"):
        intel.failure_history = {}
    intel.failure_history[category] = intel.failure_history.get(category, 0) + 1

    # If a domain consistently produces the same failure, adjust preferred
    # strategy
    threshold = settings.CLASSIFY_FAILURE_PATTERN_THRESHOLD
    for cat, count in intel.failure_history.items():
        if count >= threshold:
            # This domain has a pattern — adjust strategy proactively
            if cat in ("selector_decay", "selector_mismatch"):
                intel.preferred_strategy = "discovery"
            elif cat == "anti_bot_block":
                intel.preferred_strategy = "httpx"
            elif cat in ("hydration_failure", "lazy_load_timeout"):
                intel.hydration_delay_ms = min(
                    intel.hydration_delay_ms + settings.CLASSIFY_HYDRATION_DELAY_INCREMENT,
                    settings.CLASSIFY_HYDRATION_DELAY_MAX,
                )
            break

    intel.last_updated = time.time()
    logger.info(
        "Domain %s: failure classified as %s (confidence=%.2f, strategy=%s)",
        intel.domain,
        category,
        classification.confidence,
        classification.recovery_strategy,
    )


def translate_exception_to_friendly_message(error: Exception | str) -> str:
    """Translate low-level connection, timeout, and rendering exceptions into human-friendly operator descriptions."""
    err_text = str(error).lower()

    if "timeout" in err_text:
        if "goto" in err_text or "navigation" in err_text:
            return (
                "⚠️ [Crawl Timeout] The target web server did not respond within the allocated timeout period. "
                "DataForge has triggered a cool-down period and will automatically retry with backoff."
            )
        return (
            "⏳ [Wait Timeout] The page rendered successfully, but dynamic hydration (network idle or DOM quietness) "
            "took longer than expected. Retrying with a higher waiting delay limit."
        )

    if "dns" in err_text or "resolve" in err_text:
        return (
            "🌐 [DNS Lookup Failed] Could not resolve the server's IP address. This domain may have expired, "
            "be temporarily down, or there is a local internet lookup restriction."
        )

    if "refused" in err_text or "connect" in err_text:
        return (
            "🔌 [Connection Refused] The target server actively rejected the connection or is offline. "
            "We have logged this transient network block and scheduled a delayed retry."
        )

    if "anti-bot" in err_text or "captcha" in err_text or "cloudflare" in err_text or "ddos" in err_text:
        return (
            "🛡️ [Anti-Bot Defense Block] An active challenge or firewall (e.g. Cloudflare, Captcha, Access Denied) "
            "was encountered. To protect our node reputation, we bypassed standard fallbacks and triggered proxy rotation."
        )

    if "crash" in err_text or "closed" in err_text:
        return (
            "🤖 [Browser Context Reset] The underlying headless browser context crashed or closed unexpectedly. "
            "DataForge has recycled the process container and restarted the scrape cycle cleanly."
        )

    return (
        f"❌ [Extraction Impediment] A system error occurred: {error}. Classifying root cause and scheduled for dynamic recovery."
    )
