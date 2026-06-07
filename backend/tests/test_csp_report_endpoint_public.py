"""Tests for the CSP violation report endpoint.

Browsers POST violation reports to ``/api/system/csp-violations`` and
cannot carry API keys. The endpoint must:
- Be reachable without any authentication header.
- Still work when API keys are configured.
- Return 204 on success (no content).
- Be rate-limited but not body-size-capped beyond 5 MB.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_keys(monkeypatch):
    """Configure three distinct API keys — the endpoint must still be public."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setattr(settings, "API_KEY", "user-secret")
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)
    from app.main import app

    return TestClient(app)


def test_csp_violation_no_auth(client_with_keys) -> None:
    """No auth header — endpoint must still accept the report (204)."""
    r = client_with_keys.post(
        "/api/system/csp-violations",
        json={"csp-report": {"violated-directive": "script-src 'self'"}},
    )
    assert r.status_code in (200, 204), f"Expected 200/204 for unauthenticated CSP report, got {r.status_code}: {r.text[:200]}"


def test_csp_violation_with_user_key(client_with_keys) -> None:
    """A user key must NOT be rejected by the CSP endpoint middleware."""
    r = client_with_keys.post(
        "/api/system/csp-violations",
        headers={"X-API-Key": "user-secret"},
        json={"csp-report": {"violated-directive": "script-src 'self'"}},
    )
    assert r.status_code in (200, 204), f"Expected 200/204 for user-key CSP report, got {r.status_code}: {r.text[:200]}"


def test_csp_violation_with_admin_key(client_with_keys) -> None:
    """Admin key must also work (the endpoint is unauthenticated by design)."""
    r = client_with_keys.post(
        "/api/system/csp-violations",
        headers={"X-API-Key": "admin-secret"},
        json={"csp-report": {"violated-directive": "style-src 'self'"}},
    )
    assert r.status_code in (200, 204), f"Expected 200/204 for admin-key CSP report, got {r.status_code}: {r.text[:200]}"


def test_csp_violation_top_level_directive(client_with_keys) -> None:
    """Some browsers omit the ``csp-report`` wrapper — top-level fields
    must also be accepted."""
    r = client_with_keys.post(
        "/api/system/csp-violations",
        json={"violated-directive": "img-src 'self'"},
    )
    assert r.status_code in (200, 204), f"Expected 200/204 for top-level CSP report, got {r.status_code}: {r.text[:200]}"


def test_csp_violation_empty_body(client_with_keys) -> None:
    """An empty body must return 204 (not 400) so as not to spam logs."""
    r = client_with_keys.post("/api/system/csp-violations", json={})
    assert r.status_code in (200, 204), f"Expected 200/204 for empty CSP report, got {r.status_code}: {r.text[:200]}"
