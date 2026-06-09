"""Tests for G2 session-based authentication.

Verifies that the session cookie exchange flow works correctly:
- POST /api/session exchanges a valid API key for an HTTP-only cookie
- GET /api/session/me returns session state from the cookie
- DELETE /api/session clears the session
- The middleware accepts session cookies as an alternative to X-API-Key
"""

from app.config import settings


def _set_api_key(monkeypatch, key="test-key", admin_key=""):
    """Helper to configure API keys for session auth tests."""
    monkeypatch.setattr(settings, "API_KEY", key)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", admin_key)
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)


def test_session_create_and_verify(client, monkeypatch) -> None:
    """POST /api/session with a valid API key returns a session cookie."""
    _set_api_key(monkeypatch, key="test-api-key-123")

    # Create session with valid API key
    r = client.post("/api/session", headers={"X-API-Key": "test-api-key-123"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["role"] == "user"

    # Check the session cookie was set
    cookies = r.cookies
    assert "dataforge_session" in cookies, "Session cookie should be set"

    # Verify session via GET /api/session/me
    r2 = client.get("/api/session/me", cookies={"dataforge_session": cookies["dataforge_session"]})
    assert r2.status_code == 200
    me_data = r2.json()
    assert me_data["authenticated"] is True
    assert me_data["role"] == "user"


def test_session_rejects_invalid_key(client, monkeypatch) -> None:
    """POST /api/session with an invalid API key returns 403."""
    _set_api_key(monkeypatch, key="real-key")

    r = client.post("/api/session", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 403


def test_session_me_unauthenticated(client) -> None:
    """GET /api/session/me without a session returns unauthenticated."""
    r = client.get("/api/session/me")
    assert r.status_code == 200
    data = r.json()
    assert data["authenticated"] is False


def test_session_delete_clears_cookie(client, monkeypatch) -> None:
    """DELETE /api/session clears the session cookie (max-age=0)."""
    _set_api_key(monkeypatch, key="test-key")

    # First create a session
    r = client.post("/api/session", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert "dataforge_session" in str(r.headers.get("set-cookie", ""))

    # Delete the session — response should set cookie with max-age=0
    r2 = client.delete("/api/session")
    assert r2.status_code == 200
    set_cookie = r2.headers.get("set-cookie", "")
    assert "dataforge_session=" in set_cookie, "Session cookie should be in Set-Cookie"
    assert "max-age=0" in set_cookie.lower() or "expires=thu, 01 jan 1970" in set_cookie.lower(), (
        "Cookie should be expired"
    )

    # Without a session cookie, session/me returns unauthenticated
    r3 = client.get("/api/session/me")
    assert r3.status_code == 200
    assert r3.json()["authenticated"] is False


def test_session_cookie_authenticates_api_requests(client, monkeypatch) -> None:
    """A valid session cookie authenticates API requests without X-API-Key header."""
    _set_api_key(monkeypatch, key="test-key")

    # Create a session
    r = client.post("/api/session", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    cookie = r.cookies.get("dataforge_session")

    # Use the session cookie to access a protected API endpoint
    r2 = client.get("/api/jobs", cookies={"dataforge_session": cookie})
    assert r2.status_code == 200


def test_session_expired_cookie_rejected(client, monkeypatch) -> None:
    """An expired session cookie is rejected."""
    from app.auth.session import create_session_cookie, verify_session_cookie

    # Create a session that's already expired
    import app.auth.session as session_mod
    monkeypatch.setattr(session_mod, "SESSION_MAX_AGE", -1)
    cookie = create_session_cookie("admin")
    result = verify_session_cookie(cookie)
    assert result is None, "Expired session should be rejected"


def test_session_admin_role(client, monkeypatch) -> None:
    """POST /api/session with an admin key creates an admin-level session."""
    _set_api_key(monkeypatch, key="user-key", admin_key="admin-key-456")

    r = client.post("/api/session", headers={"X-Admin-Key": "admin-key-456"})
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "admin"

    cookie = r.cookies.get("dataforge_session")
    r2 = client.get("/api/session/me", cookies={"dataforge_session": cookie})
    assert r2.json()["role"] == "admin"
