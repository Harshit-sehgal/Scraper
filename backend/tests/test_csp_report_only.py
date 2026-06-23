"""Tests for the CSP (Content-Security-Policy) report-only middleware + endpoint.

The deep-research report calls for a *CSP: report-only CSP, mixed-content
audit*. This file pins the report-only header attached by
``app.middlewares.csp_report_only_middleware`` and the violation report
endpoint at ``POST /api/system/csp-violations``.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def reset_metrics():
    from app.metrics_collector import reset_for_testing

    reset_for_testing()
    yield
    reset_for_testing()


class TestCSPReportOnlyHeader:
    def test_health_response_carries_csp_header(self, client) -> None:
        r = client.get("/health")
        assert r.status_code in (200, 401, 403, 503)
        if r.status_code == 200:
            header = "content-security-policy-report-only"
            assert header in {k.lower() for k in r.headers}, dict(r.headers)
            value = r.headers.get(header) or r.headers.get(header.title())
            assert "default-src 'self'" in value
            assert "report-uri /api/system/csp-violations" in value

    def test_api_response_carries_csp_header(self, client) -> None:
        r = client.get("/api/system/status")
        # 200 (no auth) or 401/403 (with auth); both should carry the header.
        assert r.status_code in (200, 401, 403)
        header = "content-security-policy-report-only"
        assert header in {k.lower() for k in r.headers}, dict(r.headers)

    def test_metrics_response_carries_csp_header(self, client) -> None:
        r = client.get("/metrics")
        # /metrics is unauthenticated by default; should carry the header.
        assert r.status_code in (200, 401, 403)
        header = "content-security-policy-report-only"
        assert header in {k.lower() for k in r.headers}, dict(r.headers)


class TestCSPViolationsEndpoint:
    def test_endpoint_accepts_csp_report_wrapped_payload(self, client, reset_metrics) -> None:
        payload = {"csp-report": {"violated-directive": "script-src 'self'", "blocked-uri": "inline"}}
        r = client.post("/api/system/csp-violations", json=payload)
        assert r.status_code == 204
        from app.metrics_collector import get_csp_violations

        counts = get_csp_violations()
        assert counts.get("script-src") == 1

    def test_endpoint_accepts_bare_payload(self, client, reset_metrics) -> None:
        payload = {"violated-directive": "img-src https://example.com", "blocked-uri": "https://example.com/x.png"}
        r = client.post("/api/system/csp-violations", json=payload)
        assert r.status_code == 204
        from app.metrics_collector import get_csp_violations

        counts = get_csp_violations()
        assert counts.get("img-src") == 1

    def test_endpoint_falls_back_to_unspecified_when_missing_directive(self, client, reset_metrics) -> None:
        payload = {"csp-report": {"blocked-uri": "https://example.com/x.png"}}
        r = client.post("/api/system/csp-violations", json=payload)
        assert r.status_code == 204
        from app.metrics_collector import get_csp_violations

        counts = get_csp_violations()
        assert counts.get("unspecified") == 1

    def test_endpoint_handles_invalid_json_gracefully(self, client) -> None:
        r = client.post(
            "/api/system/csp-violations",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 204

    def test_endpoint_normalises_directive_case(self, client, reset_metrics) -> None:
        payload = {"csp-report": {"violated-directive": "  SCRIPT-SRC 'self'"}}
        r = client.post("/api/system/csp-violations", json=payload)
        assert r.status_code == 204
        from app.metrics_collector import get_csp_violations

        counts = get_csp_violations()
        assert "script-src" in counts
        assert "SCRIPT-SRC" not in counts


class TestCSPViolationsInMetricsEndpoint:
    def test_metrics_endpoint_emits_csp_violations_gauge(self, client, reset_metrics) -> None:
        from app.metrics_collector import record_csp_violation

        record_csp_violation("script-src")
        record_csp_violation("img-src")
        r = client.get("/metrics")
        if r.status_code == 200:
            assert "dataforge_csp_violations_total" in r.text, r.text
            assert 'directive="script-src"' in r.text
            assert 'directive="img-src"' in r.text


class TestCSPReportOnlyToggle:
    @pytest.mark.asyncio
    async def test_middleware_skipped_when_disabled(self, monkeypatch) -> None:
        # Re-create the middleware with the toggle off by patching the
        # settings object it reads.
        from app.config import settings
        from app.middlewares import csp_middleware

        original = settings.CSP_REPORT_ONLY
        monkeypatch.setattr(settings, "CSP_REPORT_ONLY", False)
        try:
            from starlette.requests import Request

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/health",
                "headers": [],
            }

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def call_next(_request):
                return ResponseShim()

            request = Request(scope, receive)
            response = await csp_middleware(request, call_next)
            assert "content-security-policy-report-only" not in {k.lower() for k in response.headers}
        finally:
            monkeypatch.setattr(settings, "CSP_REPORT_ONLY", original)


class ResponseShim:
    """Minimal Response stand-in for the toggle test."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
