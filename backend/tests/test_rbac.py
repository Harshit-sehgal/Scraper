"""
Unit Tests for Role-Based Access Control (RBAC) — DataForge Scraper.
Verifies that route guards correctly allow/reject requests based on configured keys and roles.
"""

import pytest

from app.utils.rbac import UserRole, get_current_role
from app.config import settings


def test_role_resolution_with_keys(monkeypatch):
    """Verify that get_current_role resolves correct roles from API keys."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret-key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret-key")
    monkeypatch.setattr(settings, "API_KEY", "user-secret-key")
    monkeypatch.setattr(settings, "ENV", "production")

    class MockRequest:
        def __init__(self, headers):
            self.headers = headers

    # 1. Admin resolution
    req = MockRequest({"X-API-Key": "admin-secret-key"})
    assert get_current_role(req) == UserRole.ADMIN

    req = MockRequest({"Authorization": "Bearer admin-secret-key"})
    assert get_current_role(req) == UserRole.ADMIN

    req = MockRequest({"X-Admin-Key": "admin-secret-key"})
    assert get_current_role(req) == UserRole.ADMIN

    # 2. Operator resolution
    req = MockRequest({"X-API-Key": "operator-secret-key"})
    assert get_current_role(req) == UserRole.OPERATOR

    req = MockRequest({"Authorization": "Bearer operator-secret-key"})
    assert get_current_role(req) == UserRole.OPERATOR

    # 3. User resolution
    req = MockRequest({"X-API-Key": "user-secret-key"})
    assert get_current_role(req) == UserRole.USER

    # 4. Unauthenticated
    req = MockRequest({"X-API-Key": "invalid-key"})
    with pytest.raises(Exception):
        get_current_role(req)


def test_rbac_endpoint_guards(client, monkeypatch):
    """Verify that actual FastAPI endpoints enforce RBAC rules under production mode."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setattr(settings, "API_KEY", "user-secret")
    monkeypatch.setattr(settings, "ENV", "production")

    # --- 1. Test create job route (Requires Admin or Operator) ---
    # Try as User (Should fail with 403)
    resp = client.post(
        "/api/jobs",
        json={"name": "rbac-test", "urls": ["https://example.com"]},
        headers={"X-API-Key": "user-secret"}
    )
    assert resp.status_code == 403
    assert "Permission denied" in resp.json()["detail"]

    # Try as Operator (Should pass validation and reach the next level)
    # Note: it might fail with other validation errors like missing schema fields, but it shouldn't fail with RBAC 403
    resp = client.post(
        "/api/jobs",
        json={"name": "rbac-test", "urls": ["https://example.com"]},
        headers={"X-API-Key": "operator-secret"}
    )
    assert resp.status_code != 403

    # Try as Admin (Should pass RBAC check)
    resp = client.post(
        "/api/jobs",
        json={"name": "rbac-test", "urls": ["https://example.com"]},
        headers={"X-API-Key": "admin-secret"}
    )
    assert resp.status_code != 403


    # --- 2. Test operator mode switcher (Requires Admin only) ---
    # Try as Operator (Should fail with 403)
    resp = client.post(
        "/api/operator/mode",
        json={"mode": "production"},
        headers={"X-API-Key": "operator-secret"}
    )
    assert resp.status_code == 403

    # Try as Admin (Should pass RBAC check, returns 200/400 instead of 403)
    resp = client.post(
        "/api/operator/mode",
        json={"mode": "production"},
        headers={"X-API-Key": "admin-secret"}
    )
    assert resp.status_code in (200, 400)
