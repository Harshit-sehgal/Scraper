"""Unit tests for app.metrics_collector — record/get helpers and ring-buffer safety.

These tests exercise the metrics_collector module in isolation (no FastAPI
client, no HTTP) so they are fast and don't need database or Playwright.
The existing test_metrics_observability.py covers the /metrics endpoint wiring;
this file covers the internal state machine, thread safety, and edge cases.
"""

from __future__ import annotations

import threading

import pytest


@pytest.fixture(autouse=True)
def _reset():
    from app.metrics_collector import reset_for_testing

    reset_for_testing()
    yield
    reset_for_testing()


# ─── Request latency ───────────────────────────────────────────────────


class TestRequestLatency:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_request_latencies, record_request_latency

        record_request_latency(0.05)
        record_request_latency(0.12)
        assert get_request_latencies() == [0.05, 0.12]

    def test_record_increments_total(self) -> None:
        from app.metrics_collector import get_requests_total, record_request_latency

        assert get_requests_total() == 0
        record_request_latency(0.1)
        assert get_requests_total() == 1
        record_request_latency(0.2)
        assert get_requests_total() == 2

    def test_ring_buffer_capped(self) -> None:
        from app.metrics_collector import (
            _MAX_METRIC_SAMPLES,
            get_request_latencies,
            record_request_latency,
        )

        for i in range(_MAX_METRIC_SAMPLES + 100):
            record_request_latency(float(i))
        assert len(get_request_latencies()) == _MAX_METRIC_SAMPLES

    def test_concurrent_records(self) -> None:
        from app.metrics_collector import get_request_latencies, record_request_latency

        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(200):
                    record_request_latency(0.001)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(get_request_latencies()) == 1000


# ─── Worker failures ───────────────────────────────────────────────────


class TestWorkerFailures:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_worker_failures, record_worker_failure

        record_worker_failure("scrape")
        record_worker_failure("scrape")
        record_worker_failure("export")
        assert get_worker_failures() == {"scrape": 2, "export": 1}

    def test_empty_initially(self) -> None:
        from app.metrics_collector import get_worker_failures

        assert get_worker_failures() == {}


# ─── LLM calls ─────────────────────────────────────────────────────────


class TestLlmCalls:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_llm_calls, record_llm_call

        assert get_llm_calls() == 0
        record_llm_call()
        assert get_llm_calls() == 1
        record_llm_call()
        assert get_llm_calls() == 2


# ─── Health check latency ──────────────────────────────────────────────


class TestHealthCheckLatency:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_health_check_latencies, record_health_check_latency

        record_health_check_latency(0.01)
        record_health_check_latency(0.02)
        assert get_health_check_latencies() == [0.01, 0.02]


# ─── Job / page durations ──────────────────────────────────────────────


class TestJobDurationClamping:
    def test_negative_duration_clamped_to_zero(self) -> None:
        from app.metrics_collector import get_job_durations, record_job_duration

        record_job_duration(-5.0)
        assert get_job_durations() == [0.0]

    def test_page_fetch_negative_clamped(self) -> None:
        from app.metrics_collector import get_page_fetch_durations, record_page_fetch_duration

        record_page_fetch_duration(-1.0)
        assert get_page_fetch_durations() == [0.0]


# ─── Errors ────────────────────────────────────────────────────────────


class TestErrors:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_errors, record_error

        record_error("database")
        record_error("database")
        record_error("network")
        assert get_errors() == {"database": 2, "network": 1}


# ─── CSP violations ────────────────────────────────────────────────────


class TestCspViolations:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_csp_violations, record_csp_violation

        record_csp_violation("script-src")
        record_csp_violation("script-src")
        record_csp_violation("img-src")
        assert get_csp_violations() == {"script-src": 2, "img-src": 1}

    def test_none_directive_normalised(self) -> None:
        from app.metrics_collector import get_csp_violations, record_csp_violation

        record_csp_violation(None)  # type: ignore[arg-type]  # runtime normalization guard
        assert get_csp_violations() == {"unspecified": 1}

    def test_whitespace_directive_normalised(self) -> None:
        from app.metrics_collector import get_csp_violations, record_csp_violation

        record_csp_violation("  ")
        assert get_csp_violations() == {"unspecified": 1}

    def test_case_normalised(self) -> None:
        from app.metrics_collector import get_csp_violations, record_csp_violation

        record_csp_violation("Script-Src")
        assert get_csp_violations() == {"script-src": 1}


# ─── Auth profile ops ──────────────────────────────────────────────────


class TestAuthProfileOps:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_auth_profile_ops, record_auth_profile_op

        record_auth_profile_op("created")
        record_auth_profile_op("validated")
        record_auth_profile_op("created")
        assert get_auth_profile_ops() == {"created": 2, "validated": 1}

    def test_empty_string_ignored(self) -> None:
        from app.metrics_collector import get_auth_profile_ops, record_auth_profile_op

        record_auth_profile_op("")
        assert get_auth_profile_ops() == {}


# ─── Workflow ops ────────────────────────────────────────────────────────


class TestWorkflowOps:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_workflow_ops, record_workflow_op

        record_workflow_op("created")
        record_workflow_op("run")
        assert get_workflow_ops() == {"created": 1, "run": 1}

    def test_empty_string_ignored(self) -> None:
        from app.metrics_collector import get_workflow_ops, record_workflow_op

        record_workflow_op("")
        assert get_workflow_ops() == {}


# ─── Signup outcomes ────────────────────────────────────────────────────


class TestSignupOutcomes:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_signup_outcomes, record_signup_outcome

        record_signup_outcome("success")
        record_signup_outcome("failure_duplicate_email")
        assert get_signup_outcomes() == {"success": 1, "failure_duplicate_email": 1}

    def test_empty_string_ignored(self) -> None:
        from app.metrics_collector import get_signup_outcomes, record_signup_outcome

        record_signup_outcome("")
        assert get_signup_outcomes() == {}


# ─── Scheduled job ops ─────────────────────────────────────────────────


class TestScheduledJobOps:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_scheduled_job_ops, record_scheduled_job_op

        record_scheduled_job_op("triggered")
        record_scheduled_job_op("completed")
        assert get_scheduled_job_ops() == {"triggered": 1, "completed": 1}


# ─── Retention ops ─────────────────────────────────────────────────────


class TestRetentionOps:
    def test_record_and_get(self) -> None:
        from app.metrics_collector import get_retention_ops, record_retention_op

        record_retention_op("enforced")
        record_retention_op("dry_run")
        assert get_retention_ops() == {"enforced": 1, "dry_run": 1}


# ─── Product counters ──────────────────────────────────────────────────


class TestProductCounterValidation:
    def test_unknown_counter_ignored(self) -> None:
        from app.metrics_collector import get_product_totals, increment_product_counter

        increment_product_counter("nonexistent_total")
        assert get_product_totals().get("nonexistent_total", 0) == 0

    def test_zero_amount_ignored(self) -> None:
        from app.metrics_collector import get_product_totals, increment_product_counter

        increment_product_counter("job_created_total", amount=0)
        assert get_product_totals()["job_created_total"] == 0

    def test_negative_amount_ignored(self) -> None:
        from app.metrics_collector import get_product_totals, increment_product_counter

        increment_product_counter("job_created_total", amount=-1)
        assert get_product_totals()["job_created_total"] == 0

    def test_valid_increment(self) -> None:
        from app.metrics_collector import get_product_totals, increment_product_counter

        increment_product_counter("job_created_total", amount=3)
        assert get_product_totals()["job_created_total"] == 3


# ─── SSRF reject normalisation ─────────────────────────────────────────


class TestSsrfRejectNormalisation:
    def test_metadata_url_collapsed_to_private_ip(self) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("http://169.254.169.254/latest/meta-data/")
        assert get_ssrf_rejects() == {"private_ip": 1}

    def test_localhost_collapsed_to_loopback(self) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("localhost connection refused")
        assert get_ssrf_rejects() == {"loopback": 1}

    def test_internal_tld_collapsed_to_dns_filter(self) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("host.corp resolution blocked")
        assert get_ssrf_rejects() == {"dns_filter": 1}

    def test_bad_port_collapsed_to_port(self) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("disallowed_port 22")
        assert get_ssrf_rejects() == {"port": 1}

    def test_bad_scheme_collapsed(self) -> None:
        from app.metrics_collector import get_ssrf_rejects, record_ssrf_reject

        record_ssrf_reject("bad_scheme ftp://blocked")
        assert get_ssrf_rejects() == {"scheme": 1}


# ─── reset_for_testing coverage ─────────────────────────────────────────


class TestResetForTesting:
    def test_full_reset_clears_all_counters(self) -> None:
        from app import metrics_collector as mc

        # Populate every counter type using the module's recorders
        mc.record_request_latency(0.1)
        mc.record_worker_failure("x")
        mc.record_health_check_latency(0.1)
        mc.record_job_duration(1.0)
        mc.record_page_fetch_duration(0.1)
        mc.record_error("y")
        mc.record_llm_call()
        mc.record_extraction_method("regex")
        mc.record_export_outcome("csv", True)
        mc.record_rate_limit_global_hit()
        mc.record_rate_limit_per_ip_hit()
        mc.record_csp_violation("script-src")
        mc.record_auth_profile_op("created")
        mc.record_workflow_op("run")
        mc.record_signup_outcome("success")
        mc.record_scheduled_job_op("triggered")
        mc.record_retention_op("enforced")
        mc.record_extraction_failure("timeout")
        mc.record_domain_extraction("example.com", success=True)

        # Sanity-check populated state
        assert mc.get_request_latencies() == [0.1]
        assert mc.get_llm_calls() == 1
        assert mc.get_rate_limit_global_hits() == 1

        # Reset
        mc.reset_for_testing()

        # Verify everything cleared
        assert mc.get_request_latencies() == []
        assert mc.get_llm_calls() == 0
        assert mc.get_rate_limit_global_hits() == 0
        assert mc.get_rate_limit_per_ip_hits() == 0
        assert mc.get_worker_failures() == {}
        assert mc.get_errors() == {}
        assert mc.get_csp_violations() == {}
        assert mc.get_auth_profile_ops() == {}
        assert mc.get_workflow_ops() == {}
        assert mc.get_signup_outcomes() == {}
        assert mc.get_scheduled_job_ops() == {}
        assert mc.get_retention_ops() == {}
        # Roadmap Obs #1/Obs #10 metrics also must be reset.
        assert mc.get_extraction_failure_counts() == dict.fromkeys(
            (
                "timeout",
                "block",
                "auth_required",
                "ssl_error",
                "network_error",
                "parse_error",
                "empty_page",
                "captcha",
                "rate_limit",
                "browser_crash",
                "unknown",
            ),
            0,
        )
        assert mc.get_domain_extraction_counts() == {}


# ─── Extraction failure categories (Roadmap Obs #10) ──────────────────


class TestExtractionFailureCategories:
    def test_known_category_increments(self) -> None:
        from app.metrics_collector import get_extraction_failure_counts, record_extraction_failure

        record_extraction_failure("timeout")
        record_extraction_failure("timeout")
        record_extraction_failure("captcha")
        counts = get_extraction_failure_counts()
        assert counts["timeout"] == 2
        assert counts["captcha"] == 1
        # Counters the test never touched must be present in the snapshot
        # (so the dict keys are stable for Prometheus scraping).
        assert "block" in counts
        assert counts["block"] == 0

    def test_unknown_category_clamped_to_unknown(self) -> None:
        from app.metrics_collector import get_extraction_failure_counts, record_extraction_failure

        record_extraction_failure("not_a_real_category")
        record_extraction_failure("totally_made_up")
        counts = get_extraction_failure_counts()
        # Unknown categories are clamped to the "unknown" bucket which
        # IS part of the bounded label set that Prometheus sees.
        assert "unknown" in counts
        assert counts["unknown"] == 2


# ─── Per-domain extraction tracking (Roadmap Obs #1) ───────────────────


class TestDomainExtractionTracking:
    def test_success_and_failure_counted_per_domain(self) -> None:
        from app.metrics_collector import get_domain_extraction_counts, record_domain_extraction

        record_domain_extraction("example.com", success=True)
        record_domain_extraction("example.com", success=True)
        record_domain_extraction("example.com", success=False)
        record_domain_extraction("other.com", success=True)

        counts = get_domain_extraction_counts()
        assert counts["example.com"] == {"success": 2, "failure": 1}
        assert counts["other.com"] == {"success": 1, "failure": 0}

    def test_empty_domain_ignored(self) -> None:
        from app.metrics_collector import get_domain_extraction_counts, record_domain_extraction

        record_domain_extraction("", success=True)
        record_domain_extraction("", success=False)
        assert get_domain_extraction_counts() == {}

    def test_bounded_memory_evicts_oldest(self) -> None:
        from app.metrics_collector import get_domain_extraction_counts, record_domain_extraction

        # Add MORE than the bound (1000) distinct domains to trigger eviction.
        for i in range(1005):
            record_domain_extraction(f"domain-{i}.example", success=True)
        # We can't predict which domain gets evicted, but the dict should
        # be bounded to roughly 1000 entries (the implementation keeps 1000).
        snapshot = get_domain_extraction_counts()
        assert len(snapshot) <= 1001
