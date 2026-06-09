"""Unit Tests for Role-Based Access Control (RBAC) — DataForge Scraper.
Verifies that route guards correctly allow/reject requests based on configured keys and roles.
"""

import pytest
from app.config import settings
from app.utils.rbac import UserRole, get_current_role
from fastapi import HTTPException


def test_role_resolution_with_keys(monkeypatch) -> None:
    """Verify that get_current_role resolves correct roles from API keys."""
    from typing import Any

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret-key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret-key")
    monkeypatch.setattr(settings, "API_KEY", "user-secret-key")
    monkeypatch.setattr(settings, "ENV", "production")

    class MockRequest:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers

    req: Any
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
    with pytest.raises((HTTPException, Exception)):
        get_current_role(req)


def test_rbac_endpoint_guards(client, monkeypatch) -> None:
    """Verify that actual FastAPI endpoints enforce RBAC rules under production mode."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setattr(settings, "API_KEY", "user-secret")
    monkeypatch.setattr(settings, "ENV", "production")
    # /api/operator/mode is mounted in the experimental router, which is
    # gated behind ``ENABLE_EXPERIMENTAL_ROUTES``. Enable it so the
    # endpoint is reachable and RBAC can be tested.
    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", True)

    # --- 1. Test create job route (Requires Admin or Operator) ---
    # Try as User (Should fail with 403)
    resp = client.post(
        "/api/jobs",
        json={"name": "rbac-test", "urls": ["https://example.com"]},
        headers={"X-API-Key": "user-secret"},
    )
    assert resp.status_code == 403
    assert "Permission denied" in resp.json()["detail"]

    # Try as Operator (Should pass validation and reach the next level)
    # Note: it might fail with other validation errors like missing schema fields, but it shouldn't fail with RBAC 403
    resp = client.post(
        "/api/jobs",
        json={"name": "rbac-test", "urls": ["https://example.com"]},
        headers={"X-API-Key": "operator-secret"},
    )
    assert resp.status_code != 403

    # Try as Admin (Should pass RBAC check)
    resp = client.post(
        "/api/jobs",
        json={"name": "rbac-test", "urls": ["https://example.com"]},
        headers={"X-API-Key": "admin-secret"},
    )
    assert resp.status_code != 403

    # --- 2. Test operator mode switcher (Requires Admin only) ---
    # Try as Operator (Should fail with 403)
    resp = client.post("/api/operator/mode", json={"mode": "production"}, headers={"X-API-Key": "operator-secret"})
    assert resp.status_code == 403

    # Try as Admin (Should pass RBAC check, returns 200/400 instead of 403)
    resp = client.post("/api/operator/mode", json={"mode": "production"}, headers={"X-API-Key": "admin-secret"})
    assert resp.status_code in (200, 400)


def test_api_middleware_accepts_bearer_tokens_before_rbac(client, monkeypatch) -> None:
    """Global API auth must not reject Bearer tokens before route RBAC runs."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setattr(settings, "API_KEY", "user-secret")
    monkeypatch.setattr(settings, "ENV", "production")

    payload = {
        "name": "bearer-rbac-test",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string", "required": True}],
    }

    operator_resp = client.post(
        "/api/jobs",
        json=payload,
        headers={"Authorization": "Bearer operator-secret"},
    )
    assert operator_resp.status_code != 403

    admin_resp = client.post(
        "/api/operator/mode",
        json={"mode": "production"},
        headers={"Authorization": "Bearer admin-secret"},
    )
    assert admin_resp.status_code in (200, 400)


def test_api_middleware_admin_key_wins_over_user_key(client, monkeypatch) -> None:
    """Admin-first auth priority: a request that carries BOTH an admin
    Bearer and a user X-API-Key header must be attributed to the admin
    role, not the user role. This is the contract that the auth
    middleware enforces by checking ``ADMIN_API_KEY`` before
    ``API_KEY``.
    """
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "admin-secret")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setattr(settings, "API_KEY", "user-secret")
    monkeypatch.setattr(settings, "ENV", "production")

    # /api/operator/mode is admin-only; user-secret would 403.
    resp = client.post(
        "/api/operator/mode",
        json={"mode": "production"},
        headers={
            "X-API-Key": "user-secret",
            "Authorization": "Bearer admin-secret",
        },
    )
    assert resp.status_code in (200, 400), (
        f"admin role was not detected when both keys were present. got {resp.status_code}: {resp.text}"
    )


def test_rbac_development_fallback(monkeypatch) -> None:
    """Verify that development fallback behavior requires ALLOW_INSECURE_DEV_AUTH."""
    from typing import Any

    class MockRequest:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers

    # 1. Dev mode but ALLOW_INSECURE_DEV_AUTH is False -> Should raise 403
    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")

    req: Any = MockRequest({})
    with pytest.raises(HTTPException) as exc_info:
        get_current_role(req)
    assert exc_info.value.status_code == 403

    # 2. Dev mode and ALLOW_INSECURE_DEV_AUTH is True -> Should grant ADMIN
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", True)
    assert get_current_role(req) == UserRole.ADMIN
