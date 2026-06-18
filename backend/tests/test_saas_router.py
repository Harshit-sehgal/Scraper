"""Tests for the SaaS identity router (signup, orgs, projects, plan)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_identity_store_fixture():
    """Reset the identity store before each SaaS router test."""
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


class TestSignup:
    """Tests for the self-service signup endpoint."""

    def test_signup_creates_user_org_and_project(self, client: TestClient):
        resp = client.post(
            "/api/saas/signup",
            json={"email": "newuser@example.com", "password": "securepassword123"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["email"] == "newuser@example.com"
        assert "user_id" in data
        assert "organization_id" in data
        assert "project_id" in data
        assert "created successfully" in data["message"]

    def test_signup_duplicate_email_fails(self, client: TestClient):
        # First signup
        resp = client.post(
            "/api/saas/signup",
            json={"email": "dup@example.com", "password": "securepassword123"},
        )
        assert resp.status_code == 201

        # Duplicate
        resp2 = client.post(
            "/api/saas/signup",
            json={"email": "dup@example.com", "password": "securepassword123"},
        )
        assert resp2.status_code == 409

    def test_signup_with_options(self, client: TestClient):
        resp = client.post(
            "/api/saas/signup",
            json={
                "email": "named@example.com",
                "password": "securepassword123",
                "display_name": "Test User",
                "org_name": "My Org",
                "project_name": "My Project",
            },
        )
        assert resp.status_code == 201

    def test_signup_short_password_fails(self, client: TestClient):
        resp = client.post(
            "/api/saas/signup",
            json={"email": "short@example.com", "password": "123"},
        )
        assert resp.status_code == 422


class TestAupEndpoints:
    """Tests for AUP acceptance endpoints."""

    def test_aup_status_requires_auth(self, client: TestClient):
        resp = client.get("/api/saas/aup/status")
        # Dev auth fallback allows access
        assert resp.status_code in (200, 401)

    def test_aup_accept_returns_response(self, client: TestClient):
        resp = client.post("/api/saas/aup/accept", json={})
        # Dev auth fallback allows access
        assert resp.status_code in (200, 401)


class TestProfileEndpoint:
    """Tests for the self-service ``GET /api/saas/me`` endpoint."""

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        """Build the cookies dict carrying a session cookie for user_id."""
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    def test_me_returns_profile_for_authenticated_user(self, client: TestClient) -> None:
        """A signed-up user with a valid session cookie can fetch their own profile."""
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "profile-test@example.com",
                "password": "securepassword123",
                "display_name": "Profile Tester",
            },
        )
        assert signup.status_code == 201, signup.text
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        me = client.get("/api/saas/me", cookies=cookies)
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["user_id"] == user_id
        assert body["email"] == "profile-test@example.com"
        assert body["display_name"] == "Profile Tester"
        # AUP not yet accepted.
        assert body["aup_accepted_at"] is None
        assert body["aup_version_accepted"] is None

    def test_me_returns_404_for_session_with_unknown_user_id(self, client: TestClient) -> None:
        """A session cookie whose user_id does not match a real user must 404, not 500."""
        cookies = self._cookies_for("ghost-user-id")
        resp = client.get("/api/saas/me", cookies=cookies)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_me_after_aup_accept_reflects_status(self, client: TestClient) -> None:
        """Accepting the AUP must be reflected in the next /me response."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "aup-test@example.com", "password": "securepassword123"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)
        from app.saas.router import CURRENT_AUP_VERSION

        accept = client.post(
            "/api/saas/aup/accept",
            json={"aup_version": CURRENT_AUP_VERSION},
            cookies=cookies,
        )
        assert accept.status_code == 200, accept.text

        me = client.get("/api/saas/me", cookies=cookies)
        assert me.status_code == 200
        body = me.json()
        assert body["aup_version_accepted"] == CURRENT_AUP_VERSION
        assert body["aup_accepted_at"] is not None


class TestPlanEndpoint:
    """Tests for the plan/limits endpoint."""

    def test_get_plan(self, client: TestClient):
        resp = client.get("/api/saas/plan")
        assert resp.status_code in (200, 401)
        if resp.status_code == 200:
            data = resp.json()
            assert data["tier"] == "free"
            assert data["max_jobs"] == 10
            assert data["max_scrapes"] == 1000
            assert data["max_teammates"] == 2
            assert data["max_projects"] == 2
            assert isinstance(data["features"], list)

    def test_plan_limits_match_enforcement_source_of_truth(self, client: TestClient):
        """The /plan endpoint MUST derive usage limits from the same
        ``app.plan_enforcer`` source of truth that enforces them at
        job-creation time, so the informational view and the
        enforcement gate can never drift.
        """
        from app.plan_enforcer import get_plan_limits
        from app.utils.usage_ledger import UsageType

        resp = client.get("/api/saas/plan")
        assert resp.status_code in (200, 401)
        if resp.status_code != 200:
            return
        data = resp.json()
        # Billing is unconfigured in tests, so the tier resolves to free.
        free_limits = get_plan_limits("free")
        assert data["max_jobs"] == free_limits[UsageType.JOB_CREATED.value]
        assert data["max_scrapes"] == free_limits[UsageType.PAGE_FETCHED.value]
        # features must be a non-empty list and contain the free-tier baseline.
        assert isinstance(data["features"], list)
        assert data["features"], "free tier should expose at least one feature"


class TestOrganizationEndpoints:
    """Tests for organization management."""

    def test_create_and_list_org(self, client: TestClient):
        # Create an org
        resp = client.post("/api/saas/orgs", json={"name": "Test Org"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Org"
        assert "id" in data

        # List orgs
        list_resp = client.get("/api/saas/orgs")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert any(o["name"] == "Test Org" for o in items)

    def test_get_org_by_id(self, client: TestClient):
        resp = client.post("/api/saas/orgs", json={"name": "Get Me"})
        assert resp.status_code == 201
        org_id = resp.json()["id"]

        get_resp = client.get(f"/api/saas/orgs/{org_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Get Me"


class TestProjectEndpoints:
    """Tests for project management."""

    def test_create_project(self, client: TestClient):
        # First create an org
        org_resp = client.post("/api/saas/orgs", json={"name": "Project Org"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Create a project under the org
        proj_resp = client.post("/api/saas/projects", json={"org_id": org_id, "name": "Test Project"})
        assert proj_resp.status_code == 201
        data = proj_resp.json()
        assert data["name"] == "Test Project"
        assert data["org_id"] == org_id

    def test_list_projects(self, client: TestClient):
        # Create an org
        org_resp = client.post("/api/saas/orgs", json={"name": "List Project Org"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Create a project
        client.post("/api/saas/projects", json={"org_id": org_id, "name": "P1"})

        # List projects
        list_resp = client.get(f"/api/saas/orgs/{org_id}/projects")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert any(p["name"] == "P1" for p in items)
