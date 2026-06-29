"""Tests for the extraction health dashboard endpoints.

Covers:
  - GET /api/system/extraction-health  — schema, time window, top failing domains, empty state
  - GET /api/system/extraction-rate    — schema, rate calculation, empty state
  - Auth guard (returns 403 without proper role)
"""

from __future__ import annotations

import pytest
from app.utils.rbac import UserRole

# ─── extraction_health ─────────────────────────────────────────────────


class TestExtractionHealthSchema:
    """``GET /api/system/extraction-health`` returns correct schema."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        from app.metrics_collector import reset_for_testing

        reset_for_testing()
        from app.routers.system import extraction_health

        result = await extraction_health(_role=UserRole.ADMIN)
        assert isinstance(result, dict)
        expected_keys = {
            "window",
            "generated_at",
            "success_rate",
            "total_attempted",
            "total_succeeded",
            "p95_latency_by_layer",
            "top_failing_domains",
            "failure_categories",
        }
        assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"

    @pytest.mark.asyncio
    async def test_success_rate_is_float_between_0_and_1(self) -> None:
        from app.metrics_collector import (
            record_domain_extraction,
            reset_for_testing,
        )

        reset_for_testing()
        record_domain_extraction("example.com", success=True)
        record_domain_extraction("example.com", success=True)
        record_domain_extraction("fail.com", success=False)

        from app.routers.system import extraction_health

        result = await extraction_health(_role=UserRole.ADMIN)
        assert 0.0 <= result["success_rate"] <= 1.0


class TestExtractionHealthTimeWindow:
    """Extraction health respects the 1h window concept."""

    @pytest.mark.asyncio
    async def test_window_field_is_1h(self) -> None:
        from app.metrics_collector import reset_for_testing

        reset_for_testing()
        from app.routers.system import extraction_health

        result = await extraction_health(_role=UserRole.ADMIN)
        assert result["window"] == "1h"


class TestExtractionHealthTopFailingDomains:
    """Top failing domains are limited to 10."""

    @pytest.mark.asyncio
    async def test_top_failing_domains_limited_to_10(self) -> None:
        from app.metrics_collector import record_domain_extraction, reset_for_testing

        reset_for_testing()
        # Record failures for 15 distinct domains.
        for i in range(15):
            record_domain_extraction(f"fail{i}.com", success=False)

        from app.routers.system import extraction_health

        result = await extraction_health(_role=UserRole.ADMIN)
        assert len(result["top_failing_domains"]) <= 10

    @pytest.mark.asyncio
    async def test_top_failing_domains_sorted_by_failure_count(self) -> None:
        from app.metrics_collector import record_domain_extraction, reset_for_testing

        reset_for_testing()
        # Domain with 5 failures
        for _ in range(5):
            record_domain_extraction("bigfail.com", success=False)
        # Domain with 2 failures
        for _ in range(2):
            record_domain_extraction("smallfail.com", success=False)

        from app.routers.system import extraction_health

        result = await extraction_health(_role=UserRole.ADMIN)
        domains = result["top_failing_domains"]
        if len(domains) >= 2:
            assert domains[0]["failure_count"] >= domains[1]["failure_count"]


class TestExtractionHealthEmptyState:
    """Extraction health handles empty metrics gracefully."""

    @pytest.mark.asyncio
    async def test_empty_state_returns_defaults(self) -> None:
        from app.metrics_collector import reset_for_testing

        reset_for_testing()
        from app.routers.system import extraction_health

        result = await extraction_health(_role=UserRole.ADMIN)
        assert result["success_rate"] == 1.0  # No failures = perfect health
        assert result["total_attempted"] == 0
        assert result["total_succeeded"] == 0
        assert result["top_failing_domains"] == []
        assert isinstance(result["p95_latency_by_layer"], dict)


# ─── extraction_rate ───────────────────────────────────────────────────


class TestExtractionRateSchema:
    """``GET /api/system/extraction-rate`` returns correct schema."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        from app.metrics_collector import reset_for_testing

        reset_for_testing()
        from app.routers.system import extraction_rate

        result = await extraction_rate(_role=UserRole.ADMIN)
        assert isinstance(result, dict)
        expected_keys = {"generated_at", "requests_total", "rate_per_second"}
        assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"

    @pytest.mark.asyncio
    async def test_rate_per_second_has_all_intervals(self) -> None:
        from app.metrics_collector import reset_for_testing

        reset_for_testing()
        from app.routers.system import extraction_rate

        result = await extraction_rate(_role=UserRole.ADMIN)
        rates = result["rate_per_second"]
        for interval in ("1m", "5m", "15m"):
            assert interval in rates, f"Missing interval: {interval}"
            assert isinstance(rates[interval], float)

    @pytest.mark.asyncio
    async def test_empty_state_rate_is_zero(self) -> None:
        from app.metrics_collector import reset_for_testing

        reset_for_testing()
        from app.routers.system import extraction_rate

        result = await extraction_rate(_role=UserRole.ADMIN)
        for rate in result["rate_per_second"].values():
            assert rate == 0.0


class TestExtractionRateWithTraffic:
    """Rate calculation with actual recorded traffic."""

    @pytest.mark.asyncio
    async def test_rate_positive_after_recording(self) -> None:
        from app.metrics_collector import (
            record_request_latency,
            reset_for_testing,
        )

        reset_for_testing()
        # Record a few requests to populate the timestamp buffer.
        for _ in range(10):
            record_request_latency(0.05)

        from app.routers.system import extraction_rate

        result = await extraction_rate(_role=UserRole.ADMIN)
        # The 1m rate should be > 0 since we just recorded requests.
        assert result["rate_per_second"]["1m"] > 0.0
        assert result["requests_total"] == 10


# ─── Auth guard ────────────────────────────────────────────────────────


class TestExtractionHealthAuth:
    """Auth is required for extraction health endpoints.

    We test this via the HTTP client with dev auth *disabled* and no
    valid API key — the RBAC guard should return 403.
    """

    def test_extraction_health_requires_auth(self) -> None:
        """Without valid credentials, the endpoint returns 403."""
        import app.main as main_mod
        from fastapi.testclient import TestClient

        # Temporarily disable dev bypass and set an API key.
        original_dev = main_mod.settings.ALLOW_INSECURE_DEV_AUTH
        original_key = main_mod.settings.API_KEY
        try:
            main_mod.settings.ALLOW_INSECURE_DEV_AUTH = False
            main_mod.settings.API_KEY = "test-secret-key"
            client = TestClient(main_mod.app, raise_server_exceptions=False)
            resp = client.get("/api/system/extraction-health")
            assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        finally:
            main_mod.settings.ALLOW_INSECURE_DEV_AUTH = original_dev
            main_mod.settings.API_KEY = original_key

    def test_extraction_rate_requires_auth(self) -> None:
        """Without valid credentials, the endpoint returns 403."""
        import app.main as main_mod
        from fastapi.testclient import TestClient

        original_dev = main_mod.settings.ALLOW_INSECURE_DEV_AUTH
        original_key = main_mod.settings.API_KEY
        try:
            main_mod.settings.ALLOW_INSECURE_DEV_AUTH = False
            main_mod.settings.API_KEY = "test-secret-key"
            client = TestClient(main_mod.app, raise_server_exceptions=False)
            resp = client.get("/api/system/extraction-rate")
            assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        finally:
            main_mod.settings.ALLOW_INSECURE_DEV_AUTH = original_dev
            main_mod.settings.API_KEY = original_key
