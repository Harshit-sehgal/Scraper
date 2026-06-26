"""Unit tests for the system router endpoints.

Tests the non-destructive, locally-executable endpoints in
``backend/app/routers/system.py``. Access-controlled endpoints are
tested by calling the handler directly with a mock ``_role`` to bypass
FastAPI's ``Depends(require_role(...))`` guard.

Endpoints not covered here:
- ``GET /metrics`` — requires running Prometheus metrics collector
- ``POST /api/url/analyze`` — requires network access + LLM
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.utils.rbac import UserRole


# ─── rate_limit_stats ────────────────────────────────────────────────


class TestRateLimitStats:
    """``GET /api/system/rate-limit-stats`` returns limiter state."""

    @pytest.mark.asyncio
    async def test_rate_limit_stats_returns_dict(self) -> None:
        from app.routers.system import rate_limit_stats

        # The rate limiter may or may not be initialised, but the
        # endpoint should return a dict (or a 503 JSONResponse).
        result = await rate_limit_stats(_role=UserRole.ADMIN)
        # A plain dict response or a JSONResponse — both are acceptable.
        if hasattr(result, "status_code"):
            assert result.status_code in (200, 503)
        else:
            assert isinstance(result, dict)
            assert "enabled" in result

    def test_rate_limit_stats_structure(self) -> None:
        from app.routers.system import _rate_limiter

        # Stats should have known keys when limiter is available.
        stats = _rate_limiter.get_stats()
        assert "enabled" in stats
        assert "active_keys" in stats


# ─── _compute_job_counts ─────────────────────────────────────────────


class TestComputeJobCounts:
    """``_compute_job_counts`` helper returns structured bucket counts."""

    def test_returns_dict_with_status_keys(self) -> None:
        from app.routers.system import _compute_job_counts

        with patch("app.routers.system.jobs_store", {}):
            result = _compute_job_counts()
        assert isinstance(result, dict)
        # Should have at least a "completed" key (one of the JobStatus values)
        from app.models import JobStatus

        assert JobStatus.COMPLETED.value in result

    def test_empty_store_returns_zero_counts(self) -> None:
        from app.models import JobStatus
        from app.routers.system import _compute_job_counts

        with patch("app.routers.system.jobs_store", {}):
            result = _compute_job_counts()
        assert result[JobStatus.COMPLETED.value] == 0


# ─── CSP violations ──────────────────────────────────────────────────


class TestCSPViolations:
    """``POST /api/system/csp-violations`` logs CSP reports."""

    @pytest.mark.asyncio
    async def test_csp_violation_returns_204(self) -> None:
        from app.routers.system import csp_violations

        request = MagicMock()
        request.json = MagicMock(
            return_value={
                "csp-report": {
                    "violated-directive": "script-src-elem",
                    "blocked-uri": "https://evil.com/script.js",
                    "document-uri": "https://app.example.com/page",
                }
            }
        )
        result = await csp_violations(request)
        assert result.status_code == 204

    @pytest.mark.asyncio
    async def test_csp_violation_missing_report_key(self) -> None:
        from app.routers.system import csp_violations

        request = MagicMock()
        request.json = MagicMock(return_value={"something": "else"})
        result = await csp_violations(request)
        assert result.status_code == 204


# ─── _basic_metric_line helpers ──────────────────────────────────────


class TestMetricHelpers:
    """Prometheus exposition format helpers produce valid output."""

    def test_basic_metric_line_no_labels(self) -> None:
        from app.routers.system import _basic_metric_line

        line = _basic_metric_line("http_requests_total", 42.0)
        assert line == "http_requests_total 42.0"

    def test_basic_metric_line_with_labels(self) -> None:
        from app.routers.system import _basic_metric_line

        line = _basic_metric_line("http_requests_total", 7.0, {"method": "GET", "path": "/api/jobs"})
        assert 'method="GET"' in line
        assert 'path="/api/jobs"' in line
        assert line.endswith(" 7.0")

    def test_prometheus_label_text_escapes_quotes(self) -> None:
        from app.routers.system import _prometheus_label_text

        result = _prometheus_label_text({"path": '/api/jobs?q="hello"'})
        # Prometheus format requires escaped quotes in label values
        assert '\\"' in result or '\\"' in result


# ─── AcquisitionMode enum ────────────────────────────────────────────


class TestAcquisitionMode:
    """``AcquisitionMode`` enum has expected values."""

    def test_standard_mode(self) -> None:
        from app.routers.system import AcquisitionMode

        assert AcquisitionMode.STANDARD == "standard"

    def test_aggressive_mode(self) -> None:
        from app.routers.system import AcquisitionMode

        assert AcquisitionMode.AGGRESSIVE == "aggressive"

    def test_deep_scan_mode(self) -> None:
        from app.routers.system import AcquisitionMode

        assert AcquisitionMode.DEEP_SCAN == "deep_scan"
