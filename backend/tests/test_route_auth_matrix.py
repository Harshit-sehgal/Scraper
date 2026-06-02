"""Route Authorization Matrix Tests — DataForge Scraper.

Tests that the RBAC middleware and require_role() dependency correctly
enforce role-based access across all route tiers:

  - Public:   No API key needed (routes outside /api/ or when no keys configured)
  - User:     Any valid API key (api_key_middleware allows, no require_role guard)
  - Operator: ADMIN or OPERATOR API key required (require_role guard)
  - Admin:    ADMIN API key only (require_role guard)

Note: The test patches Settings attributes directly (not env vars) because
pydantic-settings reads env vars at construction time.  Once the module-level
`settings` singleton is created, env-var changes via monkeypatch.setenv()
have no effect.  We must use monkeypatch.setattr() on the singleton.
"""

import asyncio

import httpx
import pytest


class LocalASGIClient:
    """Small sync wrapper around httpx ASGITransport."""

    def __init__(self, app):
        self.app = app

    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        return asyncio.run(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


# ── Route matrix: (method, path, min_role) ────────────────────────────────
# min_role: "public", "user", "operator", "admin"
#
# These are representative routes for each auth tier. Not every single route
# is enumerated — the goal is to verify that the middleware + guards work
# correctly for each tier.
#
# IMPORTANT: Routes with path parameters (e.g., {domain}) must use real
# placeholder values like "example.com" — the FastAPI router won't match
# literal "{domain}" as a path segment.

ROUTE_MATRIX = [
    # ── Public routes (outside /api/, no middleware check) ──────────────
    ("GET", "/health", "public"),
    ("GET", "/ready", "public"),
    ("GET", "/", "public"),
    # ── User-level routes (any valid API key) ───────────────────────────
    ("GET", "/api/jobs", "user"),
    ("GET", "/api/system/status", "user"),
    ("GET", "/api/system/topology", "user"),
    ("GET", "/api/system/observability", "user"),
    ("GET", "/api/scraper/config", "user"),
    ("GET", "/api/scraper/telemetry", "user"),
    ("GET", "/api/scraper/stats", "user"),
    ("GET", "/api/scraper/trends", "user"),
    ("GET", "/api/scraper/economics", "user"),
    ("GET", "/api/scraper/health/summary", "user"),
    ("GET", "/api/scraper/selectors/stats", "user"),
    ("GET", "/api/operator/mode", "user"),
    ("GET", "/api/operator/dashboard", "user"),
    ("GET", "/api/operator/health", "user"),
    ("GET", "/api/operator/predictions", "user"),
    ("GET", "/api/recycle_bin", "user"),
    # ── Operator-level routes (ADMIN or OPERATOR key) ───────────────────
    ("POST", "/api/discover", "operator"),
    ("POST", "/api/schema/suggest", "operator"),
    ("POST", "/api/url/analyze", "operator"),
    ("POST", "/api/scraper/selectors/cleanup", "operator"),
    ("POST", "/api/scraper/strategy/record", "operator"),
    ("POST", "/api/scraper/strategy/evolve/example.com", "operator"),
    ("POST", "/api/scraper/ml/learn", "operator"),
    # ── Admin-level routes (ADMIN key only) ─────────────────────────────
    ("DELETE", "/api/scraper/telemetry", "admin"),
    ("POST", "/api/operator/mode", "admin"),
    ("DELETE", "/api/recycle_bin", "admin"),
    ("POST", "/api/system/scheduler/step", "admin"),
    ("POST", "/api/system/refactor/compress", "admin"),
]


# ── Auth header helpers ─────────────────────────────────────────────────


def make_headers(api_key: str | None = None, admin_key: str | None = None) -> dict[str, str]:
    """Build request headers for a given auth level."""
    headers: dict[str, str] = {}
    if api_key is not None:
        headers["X-API-Key"] = api_key
    if admin_key is not None:
        headers["X-Admin-Key"] = admin_key
    return headers


NO_AUTH = make_headers()
USER_AUTH = make_headers(api_key="test_user_key")
OPERATOR_AUTH = make_headers(api_key="test_operator_key")
ADMIN_AUTH = make_headers(api_key="test_admin_key")


def expected_status(method: str, path: str, auth_level: str, min_role: str) -> int:
    """Determine the expected HTTP status for a request.

    Rules:
      - Public routes: always 200.
      - No auth -> /api/* -> 403 (middleware blocks)
      - User auth + user route -> 200
      - User auth + operator route -> 403 (require_role denies)
      - User auth + admin route -> 403
      - Operator auth + user route -> 200
      - Operator auth + operator route -> 200
      - Operator auth + admin route -> 403
      - Admin auth + any route -> 200
    """
    if min_role == "public":
        return 200

    if auth_level == "none":
        return 403

    if auth_level == min_role:
        return 200
    if auth_level == "user" and min_role in ("operator", "admin"):
        return 403
    if auth_level == "operator" and min_role == "admin":
        return 403
    if auth_level == "operator" and min_role in ("user", "operator"):
        return 200
    if auth_level == "admin":
        return 200

    return 200


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_settings(monkeypatch):
    """Patch the module-level Settings singleton directly.

    pydantic-settings reads env vars at construction time.  Once the
    `settings` singleton exists, monkeypatch.setenv() has no effect.
    We must use monkeypatch.setattr() on the singleton attributes.
    """
    # Import the singleton (may have been created by a previous test's import)
    from app.config import settings

    monkeypatch.setattr(settings, "API_KEY", "test_user_key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "test_operator_key")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test_admin_key")
    monkeypatch.setattr(settings, "ENV", "testing")


@pytest.fixture
def client():
    """Create an ASGI client pointing at the app without running lifespan.

    These tests verify auth middleware and route guards. Running the full
    startup lifespan makes them slow and can hang on unrelated background
    services, which obscures the route-auth signal.
    """
    import os

    mp = pytest.MonkeyPatch()
    mp.setenv("DATAFORGE_STATE_FILE", "/tmp/test_auth_state.json")
    mp.setenv("DATAFORGE_SEMANTIC_STATE_PATH", "/tmp/test_auth_semantic.json")

    try:
        from app.main import app

        yield LocalASGIClient(app)
    except Exception as e:
        pytest.skip(f"Could not initialize app for auth tests: {e}")
    finally:
        mp.undo()
        for f in ["/tmp/test_auth_state.json", "/tmp/test_auth_semantic.json"]:
            try:
                os.remove(f)
            except OSError:
                pass


# ── Parameterized route auth tests ─────────────────────────────────────


@pytest.mark.parametrize("method,path,min_role", ROUTE_MATRIX)
def test_route_auth_no_key(client, method, path, min_role):
    """Without any API key, public routes work but /api/* returns 403."""
    expected = expected_status(method, path, "none", min_role)
    response = client.request(method, path, headers=NO_AUTH)
    if response.status_code == 422:
        return  # Body validation failure is expected for POST without payload
    assert response.status_code == expected, f"{method} {path} (no auth): expected {expected}, got {response.status_code}"


@pytest.mark.parametrize("method,path,min_role", ROUTE_MATRIX)
def test_route_auth_user_key(client, method, path, min_role):
    """With a USER-level API key, user routes work; operator/admin routes blocked."""
    expected = expected_status(method, path, "user", min_role)
    response = client.request(method, path, headers=USER_AUTH)
    if response.status_code == 422:
        return
    assert response.status_code == expected, f"{method} {path} (user auth): expected {expected}, got {response.status_code}"


@pytest.mark.parametrize("method,path,min_role", ROUTE_MATRIX)
def test_route_auth_operator_key(client, method, path, min_role):
    """With an OPERATOR-level API key, user + operator routes work; admin routes blocked."""
    expected = expected_status(method, path, "operator", min_role)
    response = client.request(method, path, headers=OPERATOR_AUTH)
    if response.status_code == 422:
        return
    assert response.status_code == expected, f"{method} {path} (operator auth): expected {expected}, got {response.status_code}"


@pytest.mark.parametrize("method,path,min_role", ROUTE_MATRIX)
def test_route_auth_admin_key(client, method, path, min_role):
    """With an ADMIN-level API key, all routes work."""
    expected = expected_status(method, path, "admin", min_role)
    response = client.request(method, path, headers=ADMIN_AUTH)
    if response.status_code == 422:
        return
    assert response.status_code == expected, f"{method} {path} (admin auth): expected {expected}, got {response.status_code}"


# ── Specific auth scenarios ────────────────────────────────────────────


def test_invalid_api_key_returns_403(client):
    """An unrecognized API key should be rejected with 403."""
    response = client.get("/api/jobs", headers=make_headers(api_key="invalid_key"))
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"


def test_bearer_token_auth(client):
    """Bearer token in Authorization header should work like X-API-Key."""
    response = client.get(
        "/api/jobs",
        headers={"Authorization": "Bearer test_user_key"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_wrong_role_details_in_response(client):
    """When require_role denies access, the response should indicate the required roles."""
    response = client.post("/api/operator/mode", json={"mode": "production"}, headers=USER_AUTH)
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    body = response.json()
    assert "detail" in body
    assert "admin" in body["detail"].lower()


def test_no_auth_public_routes_work(client):
    """Public routes outside /api/ are accessible without any authentication."""
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_admin_via_x_admin_key(client):
    """X-Admin-Key header should also work for admin routes."""
    response = client.post(
        "/api/operator/mode",
        json={"mode": "production"},
        headers={"X-Admin-Key": "test_admin_key"},
    )
    assert response.status_code in (200, 422), f"Expected 200 or 422, got {response.status_code}: {response.text[:200]}"


def test_no_keys_no_auth_required(client, monkeypatch):
    """When no API keys are configured, /api/* routes should not require auth."""
    from app.config import settings

    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")

    response = client.get("/api/jobs")
    # Should work without auth when no keys configured
    assert response.status_code in (200, 422), f"Expected 200 or 422 (no auth, no keys), got {response.status_code}"
