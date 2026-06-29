"""Tests for project-scoped API key management (Feat 20)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_identity_store():
    import os
    import tempfile

    from app.saas.identity_store import SQLiteIdentityStore, reset_identity_store

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store = SQLiteIdentityStore(storage_path=f.name)
        reset_identity_store(store)
        yield
        reset_identity_store(None)
        try:
            os.remove(f.name)
        except OSError:
            pass


def _signup_and_auth(client: TestClient, email: str = "keys-test@example.com") -> tuple[str, str, dict]:
    """Sign up, accept AUP, return (user_id, project_id, cookies dict)."""
    resp = client.post(
        "/api/saas/signup",
        json={"email": email, "password": "Hunter2!@#", "display_name": "Keys Test"},
    )
    assert resp.status_code == 201
    data = resp.json()
    user_id = data["user_id"]
    project_id = data["project_id"]

    from app.saas import CURRENT_AUP_VERSION
    from app.saas.identity_store import get_identity_store

    get_identity_store().mark_aup_accepted(user_id, aup_version=CURRENT_AUP_VERSION)

    from app.auth.session import SESSION_COOKIE, create_session_cookie

    cookies = {SESSION_COOKIE: create_session_cookie(role="admin", user_id=user_id)}
    return user_id, project_id, cookies


class TestProjectApiKeys:
    def test_create_api_key(self, client: TestClient):
        _, project_id, cookies = _signup_and_auth(client)
        resp = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "My Key", "scope": "read"},
            cookies=cookies,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "My Key"
        assert body["scope"] == "read"
        assert body["raw_key"].startswith("dfk_")

    def test_list_api_keys(self, client: TestClient):
        _, project_id, cookies = _signup_and_auth(client, "keys-list@example.com")
        client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Key 1", "scope": "read"},
            cookies=cookies,
        )
        client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Key 2", "scope": "write"},
            cookies=cookies,
        )
        resp = client.get(f"/api/saas/projects/{project_id}/keys", cookies=cookies)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 2

    def test_revoke_api_key(self, client: TestClient):
        _, project_id, cookies = _signup_and_auth(client, "keys-revoke@example.com")
        create = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Revokable", "scope": "read"},
            cookies=cookies,
        )
        assert create.status_code == 201
        key_id = create.json()["id"]

        revoke = client.delete(f"/api/saas/projects/{project_id}/keys/{key_id}", cookies=cookies)
        assert revoke.status_code == 204

        # Revoked keys are excluded from the default list
        keys = client.get(f"/api/saas/projects/{project_id}/keys", cookies=cookies).json()
        assert all(k["id"] != key_id for k in keys["items"])

    def test_create_api_key_requires_auth(self, client: TestClient):
        resp = client.post("/api/saas/projects/fake/keys", json={"name": "x", "scope": "read"})
        assert resp.status_code in (401, 403, 404)

    def test_create_api_key_wrong_project(self, client: TestClient):
        _, _, cookies = _signup_and_auth(client, "keys-wrong@example.com")
        resp = client.post(
            "/api/saas/projects/non-existent/keys",
            json={"name": "Bad", "scope": "read"},
            cookies=cookies,
        )
        assert resp.status_code == 404

    def test_api_key_prefix_format(self, client: TestClient):
        _, project_id, cookies = _signup_and_auth(client, "keys-prefix@example.com")
        resp = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Prefixed", "scope": "admin"},
            cookies=cookies,
        )
        assert resp.status_code == 201
        assert resp.json()["key_prefix"] == resp.json()["raw_key"][:8]

    def test_create_multiple_keys_same_project(self, client: TestClient):
        _, project_id, cookies = _signup_and_auth(client, "keys-multi@example.com")
        for i in range(3):
            resp = client.post(
                f"/api/saas/projects/{project_id}/keys",
                json={"name": f"Key {i}", "scope": "read"},
                cookies=cookies,
            )
            assert resp.status_code == 201
        keys = client.get(f"/api/saas/projects/{project_id}/keys", cookies=cookies).json()
        assert keys["total"] >= 3

    def test_revoke_nonexistent_key_returns_404(self, client: TestClient):
        _, project_id, cookies = _signup_and_auth(client, "keys-404@example.com")
        resp = client.delete(f"/api/saas/projects/{project_id}/keys/non-existent", cookies=cookies)
        assert resp.status_code == 404
