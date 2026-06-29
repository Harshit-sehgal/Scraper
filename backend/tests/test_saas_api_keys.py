"""Tests for SaaS API key management endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_identity_store_fixture():
    """Reset the identity store before each SaaS API key test."""
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


def _accept_aup_for(user_id: str) -> None:
    """Mark the user as accepted-the-current-AUP so mutate routes pass AUP gating."""
    from app.saas import CURRENT_AUP_VERSION
    from app.saas.identity_store import get_identity_store

    get_identity_store().mark_aup_accepted(user_id, aup_version=CURRENT_AUP_VERSION)


class TestApiKeyManagement:
    """Tests for project-scoped API key CRUD."""

    def test_create_api_key(self, client: TestClient):
        # Sign up to get user + org + project
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-apikeys@example.com",
                "password": "Hunter2!@#",
                "display_name": "API Key Test",
            },
        )
        assert signup.status_code == 201
        data_signup = signup.json()
        project_id = data_signup["project_id"]
        user_id = data_signup["user_id"]
        # Accept the AUP so cookie-authenticated admin users can mutate routes
        _accept_aup_for(user_id)
        # Authenticate as the newly signed-up user
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: create_session_cookie(role="admin", user_id=user_id)}

        create = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Test Key", "scope": "read"},
            cookies=cookies,
        )
        assert create.status_code == 201
        data = create.json()
        assert data["name"] == "Test Key"
        assert data["scope"] == "read"
        assert "raw_key" in data
        assert data["raw_key"].startswith("dfk_")
        assert "key_prefix" in data

    def test_list_api_keys(self, client: TestClient):
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-list@example.com",
                "password": "Hunter2!@#",
            },
        )
        assert signup.status_code == 201
        data_signup = signup.json()
        project_id = data_signup["project_id"]
        user_id = data_signup["user_id"]
        # Accept the AUP so cookie-authenticated admin users can mutate routes
        _accept_aup_for(user_id)

        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: create_session_cookie(role="admin", user_id=user_id)}

        # Create a key
        client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "List Test", "scope": "write"},
            cookies=cookies,
        )

        list_resp = client.get(f"/api/saas/projects/{project_id}/keys", cookies=cookies)
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] >= 1
        assert "raw_key" not in data["items"][0]

    def test_revoke_api_key(self, client: TestClient):
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-revoke@example.com",
                "password": "Hunter2!@#",
            },
        )
        assert signup.status_code == 201
        data_signup = signup.json()
        project_id = data_signup["project_id"]
        user_id = data_signup["user_id"]
        # Accept the AUP so cookie-authenticated admin users can mutate routes
        _accept_aup_for(user_id)

        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: create_session_cookie(role="admin", user_id=user_id)}

        create = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Revoke Test", "scope": "read"},
            cookies=cookies,
        )
        key_id = create.json()["id"]

        revoke = client.delete(f"/api/saas/projects/{project_id}/keys/{key_id}", cookies=cookies)
        assert revoke.status_code == 204

        # List should show revoked status
        list_resp = client.get(f"/api/saas/projects/{project_id}/keys", cookies=cookies)
        for key in list_resp.json()["items"]:
            if key["id"] == key_id:
                assert key["revoked_at"] is not None

    def test_cross_project_access_denied(self, client: TestClient):
        # Create two users with separate projects
        signup1 = client.post(
            "/api/saas/signup",
            json={
                "email": "user1@example.com",
                "password": "Hunter2!@#",
            },
        )
        user1_id = signup1.json()["user_id"]

        signup2 = client.post(
            "/api/saas/signup",
            json={
                "email": "user2@example.com",
                "password": "Hunter2!@#",
            },
        )
        project2 = signup2.json()["project_id"]

        # Authenticate as user1
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: create_session_cookie(role="admin", user_id=user1_id)}

        # User1 tries to list keys for user2's project
        list_resp = client.get(f"/api/saas/projects/{project2}/keys", cookies=cookies)
        assert list_resp.status_code == 403

    def test_org_endpoints_enforce_key_scoping(self, client: TestClient):
        # 1. Sign up user 1 (gets org1, project1)
        signup1 = client.post(
            "/api/saas/signup",
            json={
                "email": "keyowner1@example.com",
                "password": "Hunter2!@#",
            },
        )
        assert signup1.status_code == 201
        data1 = signup1.json()
        project1_id = data1["project_id"]
        user1_id = data1["user_id"]

        from app.saas.identity_store import get_identity_store

        project1 = get_identity_store().get_project(project1_id)
        assert project1 is not None
        org1_id = project1.org_id
        _accept_aup_for(user1_id)

        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies1 = {SESSION_COOKIE: create_session_cookie(role="admin", user_id=user1_id)}

        # Create API key for user 1 scoped to project1_id
        create_key = client.post(
            f"/api/saas/projects/{project1_id}/keys",
            json={"name": "scoped-key-1", "scope": "write"},
            cookies=cookies1,
        )
        assert create_key.status_code == 201
        raw_key_1 = create_key.json()["raw_key"]

        # 2. Sign up user 2 (gets org2, project2)
        signup2 = client.post(
            "/api/saas/signup",
            json={
                "email": "keyowner2@example.com",
                "password": "Hunter2!@#",
            },
        )
        assert signup2.status_code == 201
        project2_id = signup2.json()["project_id"]
        project2 = get_identity_store().get_project(project2_id)
        assert project2 is not None
        org2_id = project2.org_id

        # 3. Request Org 1 details using Key 1 -> should succeed (200)
        get_org1 = client.get(f"/api/saas/orgs/{org1_id}", headers={"X-API-Key": raw_key_1})
        assert get_org1.status_code == 200

        # 4. Request Org 2 details using Key 1 -> should fail with 403 (Cross-tenant access forbidden)
        get_org2 = client.get(f"/api/saas/orgs/{org2_id}", headers={"X-API-Key": raw_key_1})
        assert get_org2.status_code == 403
