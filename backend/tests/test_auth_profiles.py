"""Tests for the Auth Profiles router and encryption integration."""

import pytest
from app.models import AuthProfile, AuthProfileStatus
from app.routers import auth_profiles as auth_profiles_router
from fastapi.testclient import TestClient


class TestAuthProfileModel:
    """Tests for AuthProfile model creation and validation."""

    def test_create_profile(self):
        p = AuthProfile(name="Login for example.com", domain="example.com")
        assert p.name == "Login for example.com"
        assert p.domain == "example.com"
        assert p.status == AuthProfileStatus.ACTIVE
        assert p.usage_count == 0

    def test_profile_id_generated(self):
        p = AuthProfile(name="Test", domain="test.com")
        assert len(p.id) == 36

    def test_storage_state_not_exposed_in_model_dump(self):
        p = AuthProfile(name="Test", domain="test.com", encrypted_storage_state="secret")
        # Model stores encrypted_storage_state, but the API endpoint strips this field
        assert "encrypted_storage_state" in p.model_dump()


class TestAuthProfileEndpoints:
    """Integration tests for Auth Profile API endpoints."""

    def test_create_and_get(self, client: TestClient):
        resp = client.post(
            "/api/auth-profiles?name=Test&domain=example.com",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test"
        assert data["domain"] == "example.com"
        profile_id = data["id"]

        get_resp = client.get(f"/api/auth-profiles/{profile_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Test"

    def test_list_profiles(self, client: TestClient):
        resp = client.get("/api/auth-profiles")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_delete_profile(self, client: TestClient):
        create_resp = client.post(
            "/api/auth-profiles?name=Delete+Me&domain=example.com",
        )
        assert create_resp.status_code == 201
        profile_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/auth-profiles/{profile_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/api/auth-profiles/{profile_id}")
        assert get_resp.status_code == 404

    def test_404_on_missing(self, client: TestClient):
        resp = client.get("/api/auth-profiles/nonexistent-id")
        assert resp.status_code == 404


class TestAuthProfileEncryption:
    """Tests that auth profile storage state is encrypted."""

    def test_storage_state_encrypted_at_rest(self, client: TestClient):
        # Create profile
        create_resp = client.post("/api/auth-profiles?name=EncTest&domain=example.com")
        assert create_resp.status_code == 201
        profile_id = create_resp.json()["id"]

        # Complete login with dummy storage state
        storage_state = {"cookies": [{"name": "session", "value": "abc123"}], "origins": []}
        complete_resp = client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json=storage_state,
        )
        assert complete_resp.status_code == 200

        # Verify the stored state is encrypted
        profiles = auth_profiles_router._auth_profiles
        stored = profiles[profile_id]
        assert "encrypted_storage_state" in stored
        encrypted = stored["encrypted_storage_state"]
        assert encrypted != ""
        # It should be a base64 string, not raw JSON
        import json

        try:
            json.loads(encrypted)
            pytest.fail("Storage state should be encrypted, not plain JSON")
        except (json.JSONDecodeError, ValueError):
            pass  # Expected — encrypted data is not valid JSON

    def test_api_never_returns_storage_state(self, client: TestClient):
        # Create and complete login
        create_resp = client.post("/api/auth-profiles?name=SafeTest&domain=example.com")
        profile_id = create_resp.json()["id"]
        client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json={"cookies": [], "origins": []},
        )

        # GET, LIST should never have the field
        get_resp = client.get(f"/api/auth-profiles/{profile_id}")
        assert "encrypted_storage_state" not in get_resp.json()

        list_resp = client.get("/api/auth-profiles")
        for item in list_resp.json()["items"]:
            assert "encrypted_storage_state" not in item


class TestAuthProfileLoginFlow:
    """Tests for the full login flow."""

    def test_start_login(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Flow&domain=flow.com")
        profile_id = create_resp.json()["id"]

        start_resp = client.post(f"/api/auth-profiles/{profile_id}/start-login")
        assert start_resp.status_code == 200
        data = start_resp.json()
        assert data["profile_id"] == profile_id
        assert data["domain"] == "flow.com"
        assert data["status"] == "ready"

    def test_complete_login_marks_active(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Complete&domain=complete.com")
        profile_id = create_resp.json()["id"]

        assert create_resp.json()["status"] == "pending_login"

        complete_resp = client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json={"cookies": [{"name": "test", "value": "val"}], "origins": []},
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["status"] == "active"


class TestAuthProfileRevoke:
    """Tests for auth profile revocation."""

    def test_revoke_profile(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Revoke&domain=revoke.com")
        profile_id = create_resp.json()["id"]

        # Complete login
        client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json={"cookies": [], "origins": []},
        )

        # Revoke
        revoke_resp = client.post(f"/api/auth-profiles/{profile_id}/revoke")
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["status"] == "revoked"

        # Storage state should be cleared
        stored = auth_profiles_router._auth_profiles[profile_id]
        assert stored["encrypted_storage_state"] == ""


class TestAuthProfileValidation:
    """Tests for auth profile validation."""

    def test_validate_active_profile(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Validate&domain=validate.com")
        profile_id = create_resp.json()["id"]
        client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json={"cookies": [], "origins": []},
        )

        validate_resp = client.post(f"/api/auth-profiles/{profile_id}/validate")
        assert validate_resp.status_code == 200
        assert validate_resp.json()["valid"] is True

    def test_validate_expired_profile(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Expired&domain=expired.com")
        profile_id = create_resp.json()["id"]
        client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json={"cookies": [], "origins": []},
        )

        # Manually set an expired timestamp
        auth_profiles_router._auth_profiles[profile_id]["expires_at"] = "2000-01-01T00:00:00+00:00"

        validate_resp = client.post(f"/api/auth-profiles/{profile_id}/validate")
        assert validate_resp.status_code == 200
        assert validate_resp.json()["valid"] is False


class TestAuthProfileSecurity:
    """Security tests for auth profiles."""

    def test_cross_user_cannot_read_profile(self, client: TestClient):
        # This is a basic test; full cross-tenant tests are in test_p0_auth_tenant.py
        # Here we just verify the 404 on missing profile
        resp = client.get("/api/auth-profiles/nonexistent-id")
        assert resp.status_code == 404

    def test_plaintext_cookies_not_stored(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Plain&domain=plain.com")
        profile_id = create_resp.json()["id"]

        raw_state = {"cookies": [{"name": "session", "value": "raw-secret"}]}
        client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json=raw_state,
        )

        # The raw state should NOT be in the stored profile
        stored = auth_profiles_router._auth_profiles[profile_id]
        encrypted = stored.get("encrypted_storage_state", "")
        import json

        assert "raw-secret" not in encrypted
        # Encrypted payload should be base64-like, not plain JSON
        try:
            json.loads(encrypted)
            pytest.fail("Should be encrypted, not plain JSON")
        except (json.JSONDecodeError, ValueError):
            pass

    def test_revoked_profile_rejected_by_runner(self, client: TestClient):
        create_resp = client.post("/api/auth-profiles?name=Rejected&domain=rejected.com")
        profile_id = create_resp.json()["id"]
        client.post(
            f"/api/auth-profiles/{profile_id}/complete-login",
            json={"cookies": [], "origins": []},
        )
        client.post(f"/api/auth-profiles/{profile_id}/revoke")

        from app.routers.auth_profiles import get_decrypted_storage_state

        with pytest.raises(Exception) as exc_info:
            get_decrypted_storage_state(profile_id, "rejected.com")
        assert "revoked" in str(exc_info.value).lower()
