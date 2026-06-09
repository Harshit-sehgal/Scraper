"""Regression tests for route RBAC.

Verifies that the route access policy enforced by the running app matches
the documented least-privilege model:
- User keys are denied operator/admin endpoints.
- Operator keys can access operator+user endpoints.
- Admin keys can access everything.
- The CSP violations endpoint is intentionally unauthenticated.

These tests are belt-and-braces: if a future refactor loosens a route
guard, this test will fail.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authed_client(monkeypatch):
    """Build a TestClient with three distinct API keys configured."""
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "op")
    monkeypatch.setattr(settings, "API_KEY", "user")
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)
    from app.main import app

    return TestClient(app)


def _hdr(role: str) -> dict[str, str]:
    return {"X-API-Key": role}


# ─── User must be DENIED operator/admin-only routes ───────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/scraper/config",
        "/api/scraper/telemetry",
        "/api/scraper/browser",
        "/api/scraper/health/legacy",
        "/api/scraper/memory/stats",
        "/api/scraper/selectors/stats",
        "/api/scraper/selectors/low-confidence",
        "/api/scraper/regressions",
        "/api/system/status",
        "/api/system/storage/status",
    ],
)
def test_user_key_denied_operator_routes(authed_client, path: str) -> None:
    """Plain user key must NOT be able to read operator/admin endpoints."""
    r = authed_client.get(path, headers=_hdr("user"))
    assert r.status_code == 403, f"User key should be denied access to {path}, got {r.status_code}: {r.text[:200]}"


# ─── Operator must SUCCEED on operator routes ────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/scraper/config",
        "/api/scraper/telemetry",
        "/api/scraper/browser",
        "/api/system/status",
        "/api/system/storage/status",
    ],
)
def test_operator_key_can_read_operator_routes(authed_client, path: str) -> None:
    """Operator key must be able to read operator-tier endpoints."""
    r = authed_client.get(path, headers=_hdr("op"))
    assert r.status_code in (200, 204), f"Operator key should access {path}, got {r.status_code}: {r.text[:200]}"


# ─── Admin must SUCCEED on operator routes ───────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/scraper/config",
        "/api/scraper/telemetry",
        "/api/system/status",
        "/api/system/storage/status",
    ],
)
def test_admin_key_can_read_operator_routes(authed_client, path: str) -> None:
    """Admin key must be able to read operator-tier endpoints."""
    r = authed_client.get(path, headers=_hdr("admin"))
    assert r.status_code in (200, 204), f"Admin key should access {path}, got {r.status_code}: {r.text[:200]}"


# ─── User-only routes (jobs) ────────────────────────────────────────


def test_user_key_can_read_user_routes(authed_client) -> None:
    """User key must be able to read user-tier endpoints."""
    r = authed_client.get("/api/jobs", headers=_hdr("user"))
    assert r.status_code in (200, 204), f"User key should access /api/jobs, got {r.status_code}: {r.text[:200]}"


# ─── CSP violations endpoint is intentionally unauthenticated ────────


def test_csp_violations_endpoint_is_unauthenticated(authed_client) -> None:
    """Browsers cannot carry API keys, so the CSP violation endpoint
    must be reachable without authentication. The middleware should
    exempt ``/api/system/csp-violations`` from API-key enforcement.
    """
    r = authed_client.post(
        "/api/system/csp-violations",
        json={"csp-report": {"violated-directive": "script-src 'self'"}},
    )
    assert r.status_code in (200, 204), f"CSP violation endpoint should be unauthenticated, got {r.status_code}: {r.text[:200]}"


def test_csp_violations_endpoint_works_with_user_key(authed_client) -> None:
    """The CSP endpoint should still work even with a user key sent —
    the middleware should ignore the key, not reject it.
    """
    r = authed_client.post(
        "/api/system/csp-violations",
        headers=_hdr("user"),
        json={"csp-report": {"violated-directive": "script-src 'self'"}},
    )
    assert r.status_code in (200, 204), f"CSP violation endpoint with user key got {r.status_code}: {r.text[:200]}"


# ─── Admin-only mutation routes ─────────────────────────────────────


def test_user_cannot_trigger_admin_only_mutations(authed_client) -> None:
    """User key must NOT be able to trigger admin-only mutations."""
    r = authed_client.delete("/api/scraper/telemetry", headers=_hdr("user"))
    assert r.status_code == 403, f"User key should be denied admin DELETE, got {r.status_code}"


def test_operator_cannot_trigger_admin_only_mutations(authed_client) -> None:
    """Operator key must NOT be able to trigger admin-only mutations."""
    r = authed_client.delete("/api/scraper/telemetry", headers=_hdr("op"))
    assert r.status_code == 403, f"Operator key should be denied admin DELETE, got {r.status_code}"


def test_admin_can_trigger_admin_only_mutations(authed_client) -> None:
    """Admin key must be able to trigger admin-only mutations."""
    r = authed_client.delete("/api/scraper/telemetry", headers=_hdr("admin"))
    assert r.status_code in (200, 204), f"Admin key should succeed for admin DELETE, got {r.status_code}: {r.text[:200]}"
