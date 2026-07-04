"""Tests for origin-validation CSRF middleware.

The middleware adds defense-in-depth origin checking for state-changing
API requests, closing the gap between SameSite=Strict (cookie-level)
and server-side origin validation. It only applies in production/staging
environments, only to state-changing methods (POST/PUT/PATCH/DELETE),
and skips API-key-authenticated requests (form-based CSRF cannot inject
custom headers).

These tests use monkeypatch to toggle the environment setting and
patch ``resolve_auth_context`` to simulate different auth contexts.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.config import settings
from app.middlewares import (
    _SKIPPED_AUTH_CONTEXTS,
    _STATEFUL_METHODS,
    origin_validation_middleware,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def csrf_app() -> FastAPI:
    """Minimal FastAPI app with only the origin-validation middleware attached."""
    app = FastAPI()

    # State-changing endpoint (POST)
    @app.post("/api/test/post")
    async def post_endpoint():
        return {"ok": True}

    @app.put("/api/test/put")
    async def put_endpoint():
        return {"ok": True}

    @app.delete("/api/test/delete")
    async def delete_endpoint():
        return {"ok": True}

    @app.patch("/api/test/patch")
    async def patch_endpoint():
        return {"ok": True}

    # Read-only endpoint (should never be affected)
    @app.get("/api/test/get")
    async def get_endpoint():
        return {"ok": True}

    # Non-API path (should never be affected)
    @app.post("/other/post")
    async def other_post():
        return {"ok": True}

    app.middleware("http")(origin_validation_middleware)
    return app


@pytest.fixture
def client(csrf_app: FastAPI) -> TestClient:
    return TestClient(csrf_app)


def _make_auth_context(*, source: str = "session", role: str = "user", user_id: str = "test") -> object:
    """Build a lightweight auth-context mock for middleware tests."""
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.source = source
    ctx.user_id = user_id
    ctx.role = role
    ctx.org_id = ""
    ctx.project_id = ""
    return ctx


def _mock_auth_source(app: FastAPI, source: str) -> None:
    """Monkeypatch resolve_auth_context at its actual home (app.utils.rbac)."""
    import app.utils.rbac as _rbac_mod

    patcher = patch.object(_rbac_mod, "resolve_auth_context", return_value=_make_auth_context(source=source))
    patcher.start()
    import atexit

    atexit.register(patcher.stop)


class TestOriginValidationMiddleware:
    """Core middleware behaviour: environment gating, method filtering, path filtering."""

    def test_get_request_always_passes(self, client: TestClient, monkeypatch) -> None:
        """Read-only GET requests are never blocked, even in production."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        resp = client.get("/api/test/get")
        assert resp.status_code == 200

    def test_non_api_path_stateful_request_passes(self, client: TestClient, monkeypatch) -> None:
        """Non-/api/ paths are never blocked."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        resp = client.post("/other/post")
        assert resp.status_code == 200

    def test_stateful_post_in_dev_passes_without_origin(self, client: TestClient, monkeypatch) -> None:
        """In development, state-changing requests without Origin pass."""
        monkeypatch.setattr(settings, "ENV", "development")
        _mock_auth_source(client.app, "session")
        resp = client.post("/api/test/post")
        assert resp.status_code == 200

    def test_stateful_post_in_prod_rejected_without_origin(self, client: TestClient, monkeypatch) -> None:
        """In production, state-changing session requests without Origin are rejected."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        resp = client.post("/api/test/post")
        assert resp.status_code == 403
        assert "Origin" in resp.json()["detail"]

    def test_stateful_post_in_staging_rejected_without_origin(self, client: TestClient, monkeypatch) -> None:
        """Staging also enforces the origin check."""
        monkeypatch.setattr(settings, "ENV", "staging")
        _mock_auth_source(client.app, "session")
        resp = client.post("/api/test/post")
        assert resp.status_code == 403

    @pytest.mark.parametrize("method", sorted(_STATEFUL_METHODS))
    def test_all_stateful_methods_checked(self, client: TestClient, monkeypatch, method: str) -> None:
        """Every state-changing method is covered."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        resp = getattr(client, method.lower())("/api/test/" + method.lower())
        assert resp.status_code == 403


class TestOriginValidationWithOrigin:
    """Tests when an Origin or Referer header is present."""

    def test_allowed_origin_passes(self, client: TestClient, monkeypatch) -> None:
        """A request with an Origin matching CORS_ORIGINS passes."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        origins = settings.CORS_ORIGINS
        assert origins, "Test needs at least one CORS origin"
        resp = client.post(
            "/api/test/post",
            headers={"Origin": origins[0]},
        )
        assert resp.status_code == 200

    def test_disallowed_origin_rejected(self, client: TestClient, monkeypatch) -> None:
        """A request with an Origin NOT in CORS_ORIGINS is rejected."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        resp = client.post(
            "/api/test/post",
            headers={"Origin": "https://evil.com"},
        )
        assert resp.status_code == 403
        assert "not allowed" in resp.json()["detail"].lower()

    def test_referer_fallback_works(self, client: TestClient, monkeypatch) -> None:
        """When Origin is absent, the Referer's origin portion is used."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        origins = settings.CORS_ORIGINS
        assert origins, "Test needs at least one CORS origin"
        resp = client.post(
            "/api/test/post",
            headers={"Referer": origins[0] + "/app/jobs"},
        )
        assert resp.status_code == 200

    def test_referer_with_disallowed_origin_rejected(self, client: TestClient, monkeypatch) -> None:
        """Referer from a non-whitelisted origin is rejected."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "session")
        resp = client.post(
            "/api/test/post",
            headers={"Referer": "https://evil.com/app/jobs"},
        )
        assert resp.status_code == 403


class TestOriginValidationSkipsAPIKeyAuth:
    """API-key-authenticated requests must pass without Origin headers."""

    @pytest.mark.parametrize("auth_source", sorted(_SKIPPED_AUTH_CONTEXTS))
    def test_api_key_auth_skips_origin_check(self, client: TestClient, monkeypatch, auth_source: str) -> None:
        """API-key-authenticated requests bypass the origin check entirely."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, auth_source)
        resp = client.post("/api/test/post")  # no Origin header
        assert resp.status_code == 200, f"API-key auth {auth_source!r} should bypass CSRF check"

    def test_api_key_user_bypasses_all_methods(self, client: TestClient, monkeypatch) -> None:
        """api_key_user context bypasses origin check for all stateful methods."""
        monkeypatch.setattr(settings, "ENV", "production")
        _mock_auth_source(client.app, "api_key_user")
        for method in _STATEFUL_METHODS:
            resp = getattr(client, method.lower())("/api/test/" + method.lower())
            assert resp.status_code == 200, f"{method} should pass for api_key_user"
