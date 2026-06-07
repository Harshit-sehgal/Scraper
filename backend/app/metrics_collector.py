"""Shared Metrics Collector — holds runtime metric state that is read by the
/metrics endpoint and written by middleware, workers, and other subsystems.

This module is deliberately separate from main.py to avoid circular imports
when worker_queue.py or other modules need to record metrics.
"""

import threading

_MAX_METRIC_SAMPLES = 1000

# Ring buffer for API request durations (seconds)
_request_latencies: list[float] = []
_request_latencies_lock = threading.Lock()

# Worker failure counters: task_type -> count
_worker_failures: dict[str, int] = {}
_worker_failures_lock = threading.Lock()

# Backend health check durations (seconds) — ring buffer
_health_check_latencies: list[float] = []
_health_check_latencies_lock = threading.Lock()

# Generic error counters: type -> count (e.g. database, network, scraper)
_errors_total: dict[str, int] = {}
_errors_total_lock = threading.Lock()

# LLM call counters
_llm_calls_total: int = 0
_llm_calls_total_lock = threading.Lock()

# Total request counter
_requests_total: int = 0
_requests_total_lock = threading.Lock()

# Extraction-method distribution: method -> count
# Populated by the scraper engine when a record's extraction succeeds.
_extraction_method_counts: dict[str, int] = {}
_extraction_method_counts_lock = threading.Lock()

# Anti-bot classification counts: classification -> count
# e.g. "captcha", "cloudflare_challenge", "rate_limited", "ok"
_anti_bot_classifications: dict[str, int] = {}
_anti_bot_classifications_lock = threading.Lock()

# Export generation outcomes: format -> outcome -> count
# e.g. {"csv": {"success": 12, "failure": 1}, "excel": {...}}
_export_outcomes: dict[str, dict[str, int]] = {}
_export_outcomes_lock = threading.Lock()

# Browser launch outcomes: outcome -> count
_browser_launch_outcomes: dict[str, int] = {}
_browser_launch_outcomes_lock = threading.Lock()

# SSRF validation rejects: reason -> count
_ssrf_rejects: dict[str, int] = {}
_ssrf_rejects_lock = threading.Lock()

# Repository query latencies (seconds) — ring buffer
_repo_query_latencies: list[float] = []
_repo_query_latencies_lock = threading.Lock()

# CSP violation counts: directive -> count. Populated by the
# ``/api/system/csp-violations`` endpoint when a browser reports a
# Content-Security-Policy violation. The directive is the policy clause that
# was violated (e.g. ``script-src``, ``img-src``); "unspecified" when the
# browser does not report one.
_csp_violations: dict[str, int] = {}
_csp_violations_lock = threading.Lock()

# Rate limit hit counters: incremented by the rate limiter middleware when
# a request is blocked by the aggregate global tier or the per-IP tier.
# Exposed as Prometheus gauges via /metrics.
_rate_limit_global_hits: int = 0
_rate_limit_global_hits_lock = threading.Lock()
_rate_limit_per_ip_hits: int = 0
_rate_limit_per_ip_hits_lock = threading.Lock()


def record_request_latency(duration_seconds: float) -> None:
    """Record an API request duration for metrics export."""
    global _request_latencies, _requests_total
    with _request_latencies_lock:
        _request_latencies.append(duration_seconds)
        if len(_request_latencies) > _MAX_METRIC_SAMPLES:
            _request_latencies = _request_latencies[-_MAX_METRIC_SAMPLES:]
    with _requests_total_lock:
        _requests_total += 1


def record_worker_failure(task_type: str) -> None:
    """Increment the worker failure counter for a task type.

    Called by worker_queue.py when a task enters dead_letter state.
    """
    with _worker_failures_lock:
        _worker_failures[task_type] = _worker_failures.get(task_type, 0) + 1


def record_health_check_latency(duration_seconds: float) -> None:
    """Record a backend health check duration."""
    global _health_check_latencies
    with _health_check_latencies_lock:
        _health_check_latencies.append(duration_seconds)
        if len(_health_check_latencies) > _MAX_METRIC_SAMPLES:
            _health_check_latencies = _health_check_latencies[-_MAX_METRIC_SAMPLES:]


def record_error(error_type: str) -> None:
    """Increment cumulative error counts by type."""
    with _errors_total_lock:
        _errors_total[error_type] = _errors_total.get(error_type, 0) + 1


def record_llm_call() -> None:
    """Increment cumulative LLM call count."""
    global _llm_calls_total
    with _llm_calls_total_lock:
        _llm_calls_total += 1


def record_extraction_method(method: str) -> None:
    """Record one record-extraction event with its chosen method.

    The deep-research report's monitoring target calls for an
    *extraction method distribution* metric so operators can spot
    regressions to the regex fallback before they turn into data
    quality incidents.
    """
    if not method:
        return
    with _extraction_method_counts_lock:
        _extraction_method_counts[method] = _extraction_method_counts.get(method, 0) + 1


def record_anti_bot_classification(classification: str) -> None:
    """Record a single anti-bot classification event.

    Examples: ``"captcha"``, ``"cloudflare_challenge"``,
    ``"rate_limited"``, ``"ok"``. Operators can alert when the
    ratio of non-OK classifications to total requests crosses a
    threshold.
    """
    if not classification:
        return
    with _anti_bot_classifications_lock:
        _anti_bot_classifications[classification] = (
            _anti_bot_classifications.get(
                classification,
                0,
            )
            + 1
        )


def record_export_outcome(fmt: str, success: bool) -> None:
    """Record an export generation outcome.

    Tracks both successes and failures so operators can alert on
    export-failure ratios that exceed the report's *export
    generation failures* monitoring target.
    """
    if not fmt:
        return
    outcome = "success" if success else "failure"
    with _export_outcomes_lock:
        bucket = _export_outcomes.setdefault(fmt, {"success": 0, "failure": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1


def record_browser_launch(success: bool) -> None:
    """Record a Playwright browser launch outcome.

    Used to detect environments where Playwright is missing its
    runtime libraries or the bundled browsers are corrupt.
    """
    outcome = "success" if success else "failure"
    with _browser_launch_outcomes_lock:
        _browser_launch_outcomes[outcome] = _browser_launch_outcomes.get(outcome, 0) + 1


def record_ssrf_reject(reason: str) -> None:
    """Record an SSRF validation reject.

    Operators can use this to spot scraping attempts that target
    private address space and to tune the SSRF guard.
    """
    if not reason:
        reason = "unspecified"
    with _ssrf_rejects_lock:
        _ssrf_rejects[reason] = _ssrf_rejects.get(reason, 0) + 1


def record_repo_query_latency(duration_seconds: float) -> None:
    """Record a single repository query latency (seconds).

    The deep-research report's *Repository query latency* target
    wants p50/p95 visibility on storage calls. A ring buffer is
    good enough for our short-lived single-process metrics
    endpoint; long-term storage should use Prometheus's own
    histogram type.
    """
    global _repo_query_latencies
    with _repo_query_latencies_lock:
        _repo_query_latencies.append(duration_seconds)
        if len(_repo_query_latencies) > _MAX_METRIC_SAMPLES:
            _repo_query_latencies = _repo_query_latencies[-_MAX_METRIC_SAMPLES:]


def record_csp_violation(directive: str) -> None:
    """Record a Content-Security-Policy violation report.

    Called by the ``/api/system/csp-violations`` endpoint when a browser
    reports a violation. The directive is the policy clause that was
    violated (``script-src``, ``img-src``, ``connect-src``, …); the value
    is normalised to lowercase and defaults to ``"unspecified"`` if the
    browser does not report a directive.
    """
    label = (directive or "unspecified").strip().lower() or "unspecified"
    with _csp_violations_lock:
        _csp_violations[label] = _csp_violations.get(label, 0) + 1


def record_rate_limit_global_hit() -> None:
    """Increment the global rate limit hit counter.

    Called by the rate limiter middleware when the aggregate global tier
    blocks a request (429 Too Many Requests). Exposed as a Prometheus
    gauge via /metrics so operators can alert on sustained global
    rate-limiting.
    """
    global _rate_limit_global_hits
    with _rate_limit_global_hits_lock:
        _rate_limit_global_hits += 1


def record_rate_limit_per_ip_hit() -> None:
    """Increment the per-IP rate limit hit counter.

    Called by the rate limiter middleware when the per-IP fair-sharing
    tier blocks a request (429 Too Many Requests). Exposed as a
    Prometheus gauge via /metrics so operators can spot a single
    aggressive client being throttled.
    """
    global _rate_limit_per_ip_hits
    with _rate_limit_per_ip_hits_lock:
        _rate_limit_per_ip_hits += 1


def get_request_latencies() -> list[float]:
    with _request_latencies_lock:
        return list(_request_latencies)


def get_worker_failures() -> dict[str, int]:
    with _worker_failures_lock:
        return dict(_worker_failures)


def get_health_check_latencies() -> list[float]:
    with _health_check_latencies_lock:
        return list(_health_check_latencies)


def get_errors() -> dict[str, int]:
    with _errors_total_lock:
        return dict(_errors_total)


def get_llm_calls() -> int:
    with _llm_calls_total_lock:
        return _llm_calls_total


def get_requests_total() -> int:
    with _requests_total_lock:
        return _requests_total


def get_extraction_method_counts() -> dict[str, int]:
    with _extraction_method_counts_lock:
        return dict(_extraction_method_counts)


def get_anti_bot_classifications() -> dict[str, int]:
    with _anti_bot_classifications_lock:
        return dict(_anti_bot_classifications)


def get_export_outcomes() -> dict[str, dict[str, int]]:
    with _export_outcomes_lock:
        return {fmt: dict(outcomes) for fmt, outcomes in _export_outcomes.items()}


def get_browser_launch_outcomes() -> dict[str, int]:
    with _browser_launch_outcomes_lock:
        return dict(_browser_launch_outcomes)


def get_ssrf_rejects() -> dict[str, int]:
    with _ssrf_rejects_lock:
        return dict(_ssrf_rejects)


def get_repo_query_latencies() -> list[float]:
    with _repo_query_latencies_lock:
        return list(_repo_query_latencies)


def get_csp_violations() -> dict[str, int]:
    with _csp_violations_lock:
        return dict(_csp_violations)


def get_rate_limit_global_hits() -> int:
    with _rate_limit_global_hits_lock:
        return _rate_limit_global_hits


def get_rate_limit_per_ip_hits() -> int:
    with _rate_limit_per_ip_hits_lock:
        return _rate_limit_per_ip_hits


def reset_for_testing() -> None:
    """Reset all counters and buffers (for test isolation)."""
    global _llm_calls_total, _requests_total, _rate_limit_global_hits, _rate_limit_per_ip_hits
    with _request_latencies_lock:
        _request_latencies.clear()
    with _worker_failures_lock:
        _worker_failures.clear()
    with _health_check_latencies_lock:
        _health_check_latencies.clear()
    with _errors_total_lock:
        _errors_total.clear()
    with _llm_calls_total_lock:
        _llm_calls_total = 0
    with _requests_total_lock:
        _requests_total = 0
    with _extraction_method_counts_lock:
        _extraction_method_counts.clear()
    with _anti_bot_classifications_lock:
        _anti_bot_classifications.clear()
    with _export_outcomes_lock:
        _export_outcomes.clear()
    with _browser_launch_outcomes_lock:
        _browser_launch_outcomes.clear()
    with _ssrf_rejects_lock:
        _ssrf_rejects.clear()
    with _repo_query_latencies_lock:
        _repo_query_latencies.clear()
    with _csp_violations_lock:
        _csp_violations.clear()
    with _rate_limit_global_hits_lock:
        _rate_limit_global_hits = 0
    with _rate_limit_per_ip_hits_lock:
        _rate_limit_per_ip_hits = 0
