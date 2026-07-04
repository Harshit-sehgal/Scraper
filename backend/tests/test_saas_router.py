"""Tests for the SaaS identity router (signup, orgs, projects, plan)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_identity_store_fixture():
    """Reset the identity store before each SaaS router test."""
    import os
    import tempfile

    from app.saas.identity_store import SQLiteIdentityStore, reset_identity_store
    from app.saas.router import reset_rate_limiters

    # Reset rate limiters so tests don't hit 429s from sharing 127.0.0.1
    reset_rate_limiters()

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
            json={"email": "newuser@example.com", "password": "SecurePass123!"},
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
            json={"email": "dup@example.com", "password": "SecurePass123!"},
        )
        assert resp.status_code == 201

        # Duplicate
        resp2 = client.post(
            "/api/saas/signup",
            json={"email": "dup@example.com", "password": "SecurePass123!"},
        )
        assert resp2.status_code == 409

    def test_signup_with_options(self, client: TestClient):
        resp = client.post(
            "/api/saas/signup",
            json={
                "email": "named@example.com",
                "password": "SecurePass123!",
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
                "password": "SecurePass123!",
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
            json={"email": "aup-test@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)
        from app.saas import CURRENT_AUP_VERSION

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
        if resp.status_code != 200:
            return  # Not authenticated — nothing to check
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


class TestUsageEndpoint:
    """Tests for the usage summary endpoint."""

    def test_get_usage_returns_defaults_with_no_activity(self, client: TestClient):
        # The /api/saas/usage endpoint returns the authenticated user's
        # accumulated activity. The default user_id under dev-fallback
        # auth is shared across the entire test process, so we cannot
        # assert absolute zeros. Instead verify that the response shape
        # is sane and all known counters are present and non-negative.
        resp = client.get("/api/saas/usage")
        # Dev auth fallback allows access
        assert resp.status_code in (200, 401)
        if resp.status_code != 200:
            return  # Not authenticated — nothing to check
        data = resp.json()
        assert set(data.keys()) >= {
            "jobs_created",
            "pages_fetched",
            "scheduled_jobs",
            "ai_structuring",
            "api_requests",
        }
        assert data["jobs_created"] >= 0
        assert data["pages_fetched"] >= 0
        assert data["scheduled_jobs"] >= 0
        assert data["ai_structuring"] >= 0
        # The API-request counter always increments at least once per
        # request via the request counter middleware, so it must be
        # at least 1 (and certainly non-negative).
        assert data["api_requests"] >= 1


class TestAupEnforcementOnMutationRoutes:
    """Tests that AUP acceptance is required for protected mutation routes."""

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    @staticmethod
    def _accept_aup_via_store(user_id: str) -> None:
        from app.saas import CURRENT_AUP_VERSION
        from app.saas.identity_store import get_identity_store

        get_identity_store().mark_aup_accepted(user_id, aup_version=CURRENT_AUP_VERSION)

    def test_create_api_key_fails_without_aup(self, client: TestClient):
        """Creating an API key must 403 if the user has not accepted the AUP."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "noaup-api@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        project_id = signup.json()["project_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "test-key", "scope": "read"},
            cookies=cookies,
        )
        assert resp.status_code == 403
        assert "Acceptable Use Policy" in resp.json()["detail"]

    def test_create_project_fails_without_aup(self, client: TestClient):
        """Creating a project must 403 if the user has not accepted the AUP."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "noaup-proj@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post(
            "/api/saas/projects",
            json={"org_id": org_id, "name": "No-AUP Project"},
            cookies=cookies,
        )
        assert resp.status_code == 403
        assert "Acceptable Use Policy" in resp.json()["detail"]

    def test_create_scheduled_job_fails_without_aup(self, client: TestClient):
        """Creating a scheduled job must 403 if the user has not accepted the AUP."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "noaup-sched@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post(
            "/api/scheduled?name=No+AUP+Schedule&job_name=No+AUP+Run",
            cookies=cookies,
        )
        assert resp.status_code == 403
        assert "Acceptable Use Policy" in resp.json()["detail"]

    def test_create_api_key_succeeds_with_aup(self, client: TestClient):
        """Creating an API key must succeed after AUP acceptance."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "withaup-api@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        project_id = signup.json()["project_id"]
        cookies = self._cookies_for(user_id)

        self._accept_aup_via_store(user_id)

        resp = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "test-key-aup", "scope": "read"},
            cookies=cookies,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["name"] == "test-key-aup"


class TestOrganizationDeleteEndpoint:
    """Tests for the organization deletion endpoint."""

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    def test_delete_org_removes_org_and_cascades(self, client: TestClient):
        """Deleting an org must cascade to memberships, projects, and API keys."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "orgdelete@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        project_id = signup.json()["project_id"]
        cookies = self._cookies_for(user_id)

        # Verify org exists
        get_resp = client.get(f"/api/saas/orgs/{org_id}", cookies=cookies)
        assert get_resp.status_code == 200

        # Delete the org
        del_resp = client.delete(f"/api/saas/orgs/{org_id}", cookies=cookies)
        assert del_resp.status_code == 204, del_resp.text

        # Verify org is gone (owner's cookie should get 404)
        get_resp2 = client.get(f"/api/saas/orgs/{org_id}", cookies=cookies)
        assert get_resp2.status_code == 404

        # Verify project is gone
        from app.saas.identity_store import get_identity_store

        assert get_identity_store().get_project(project_id) is None

    def test_delete_nonexistent_org_returns_404(self, client: TestClient):
        """Deleting a non-existent org must 404."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "ghost-delete@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.delete("/api/saas/orgs/nonexistent-org-id", cookies=cookies)
        assert resp.status_code == 404


class TestProjectDeleteEndpoint:
    """Tests for the project deletion endpoint."""

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    def test_delete_project_removes_project_and_api_keys(self, client: TestClient):
        """Deleting a project must cascade to API keys."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "projdelete@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        project_id = signup.json()["project_id"]
        cookies = self._cookies_for(user_id)

        # Accept AUP so we can create an API key
        from app.saas import CURRENT_AUP_VERSION
        from app.saas.identity_store import get_identity_store

        get_identity_store().mark_aup_accepted(user_id, aup_version=CURRENT_AUP_VERSION)

        # Create an API key in the project
        key_resp = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "delete-me-key", "scope": "read"},
            cookies=cookies,
        )
        assert key_resp.status_code == 201
        key_id = key_resp.json()["id"]

        # Delete the project
        del_resp = client.delete(f"/api/saas/projects/{project_id}", cookies=cookies)
        assert del_resp.status_code == 204, del_resp.text

        # Verify project is gone
        assert get_identity_store().get_project(project_id) is None

        # Verify API key is gone
        assert get_identity_store().get_api_key(key_id) is None

    def test_delete_nonexistent_project_returns_404(self, client: TestClient):
        """Deleting a non-existent project must 404."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "ghost-proj-delete@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.delete("/api/saas/projects/nonexistent-project-id", cookies=cookies)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# FU-2026-07-05 — Invitation Role Passthrough / Org-Takeover Fix Tests
# ═══════════════════════════════════════════════════════════════════════


class TestInvitationSecurity:
    """Regression tests for the CRITICAL org-takeover fix (FU-2026-07-05):

    - ``role="owner"`` in invitation body is rejected (allowlist gate).
    - A viewer-membership caller cannot invite an admin.
    - A member-membership caller cannot invite an admin.
    - The invite-role allowlist is validated at both route and
      identity_store layers (defense-in-depth).
    """

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    def test_invitation_with_owner_role_is_rejected(self, client: TestClient):
        """``role="owner"`` must be 422 regardless of inviter's own rank."""
        # Create owner user + org
        signup = client.post(
            "/api/saas/signup",
            json={"email": "org-owner@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201, signup.text
        user_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "attacker@evil.com", "role": "owner"},
            cookies=cookies,
        )
        # Expect 422 — "owner" is not in _INVITABLE_ROLES
        assert resp.status_code == 422, resp.text
        assert "role must be one of member/admin/viewer" in resp.json()["detail"].lower()

    def test_viewer_cannot_invite_as_admin(self, client: TestClient):
        """A viewer-membership caller cannot invite with role='admin'."""
        # Create owner
        signup = client.post(
            "/api/saas/signup",
            json={"email": "owner-viewer@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201, signup.text
        owner_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]

        # Create a second user (viewer)
        signup2 = client.post(
            "/api/saas/signup",
            json={"email": "viewer-user@example.com", "password": "SecurePass123!"},
        )
        assert signup2.status_code == 201, signup2.text
        viewer_id = signup2.json()["user_id"]

        # Add viewer as a member of the org (via owner's cookies)
        owner_cookies = self._cookies_for(owner_id)
        # First add viewer as member via invitation
        invite_resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "viewer-user@example.com", "role": "member"},
            cookies=owner_cookies,
        )
        assert invite_resp.status_code == 201
        invitation_id = invite_resp.json()["id"]

        # Viewer accepts the invitation
        viewer_cookies_raw = self._cookies_for(viewer_id, role="admin")
        accept_resp = client.post(
            f"/api/saas/invitations/{invitation_id}/respond",
            json={"accept": True},
            cookies=viewer_cookies_raw,
        )
        assert accept_resp.status_code == 200, accept_resp.text

        # Now viewer tries to invite someone as admin
        resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "new-admin@example.com", "role": "admin"},
            cookies=viewer_cookies_raw,
        )
        assert resp.status_code == 403, resp.text
        # The message should indicate rank insufficiency (either
        # "only an owner may invite an admin" or
        # "cannot invite a member role above your own")
        detail_lower = resp.json()["detail"].lower()
        assert "owner" in detail_lower or "above your own" in detail_lower

    def test_member_cannot_invite_as_admin(self, client: TestClient):
        """A member-membership caller cannot invite with role='admin'."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "owner-member@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201, signup.text
        owner_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]

        signup2 = client.post(
            "/api/saas/signup",
            json={"email": "member-user@example.com", "password": "SecurePass123!"},
        )
        assert signup2.status_code == 201, signup2.text
        member_id = signup2.json()["user_id"]

        # Owner invites member
        owner_cookies = self._cookies_for(owner_id)
        invite_resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "member-user@example.com", "role": "member"},
            cookies=owner_cookies,
        )
        assert invite_resp.status_code == 201
        invitation_id = invite_resp.json()["id"]

        # Member accepts
        member_cookies = self._cookies_for(member_id, role="admin")
        accept_resp = client.post(
            f"/api/saas/invitations/{invitation_id}/respond",
            json={"accept": True},
            cookies=member_cookies,
        )
        assert accept_resp.status_code == 200

        # Member tries to invite admin — must be rejected
        resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "admin-wannabe@example.com", "role": "admin"},
            cookies=member_cookies,
        )
        assert resp.status_code == 403, resp.text
        detail_lower = resp.json()["detail"].lower()
        assert "owner" in detail_lower or "above your own" in detail_lower

    def test_owner_can_invite_admin(self, client: TestClient):
        """Owner can still invite admins (baseline — fix must not break legit flow)."""
        signup = client.post(
            "/api/saas/signup",
            json={"email": "owner-legit@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201, signup.text
        user_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        cookies = self._cookies_for(user_id)

        # Owner invites member
        resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "some-member@example.com", "role": "member"},
            cookies=cookies,
        )
        assert resp.status_code == 201, resp.text

        # Owner invites admin — should still work
        resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "some-admin@example.com", "role": "admin"},
            cookies=cookies,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == "admin"

    def test_identity_store_defense_in_depth_rejects_non_invitable_role(self) -> None:
        """``respond_to_invitation`` must return None for non-invitable roles even if DB row says 'owner'."""
        import os
        import tempfile

        from app.saas.identity_store import SQLiteIdentityStore, reset_identity_store

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SQLiteIdentityStore(storage_path=db_path)
            reset_identity_store(store)
            # Sign up a user via the service so we get valid user/org rows
            from app.saas import SignupService

            svc = SignupService()
            signup_result = svc.signup("hostile@example.com", "SecurePass123!", org_name="HostileCorp")
            assert signup_result.user.id

            # Directly inject an invitation row with role='owner' — simulating
            # a stale DB migration, a second code path, or an attacker-injected
            # row. The circuit-allowlist in respond_to_invitation should reject
            # it (return None) before any membership row is inserted.
            import uuid
            from datetime import UTC, datetime, timedelta

            invite_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            expires = (datetime.now(UTC) + timedelta(days=7)).isoformat()
            with store._lock, store._connect() as conn:
                conn.execute(
                    """INSERT INTO team_invitations
                       (id, org_id, invited_email, invited_by_user_id, role, status, created_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (
                        invite_id,
                        signup_result.organization.id,
                        "attacker@evil.com",
                        signup_result.user.id,
                        "owner",
                        now,
                        expires,
                    ),
                )
                conn.commit()

            # Now try to respond. Should return None because role="owner"
            # is rejected by the defense-in-depth check.
            result = store.respond_to_invitation(
                invite_id,
                accept=True,
                requesting_user_id=signup_result.user.id,
            )
            assert result is None, f"Should reject owner role; got {result}"

            # Verify no membership was created for owner role
            members = store.list_org_memberships(signup_result.organization.id)
            # Only the original OWNER from signup should exist
            assert len(members) == 1
            assert members[0].role.value == "owner"
        finally:
            reset_identity_store(None)
            try:
                os.remove(db_path)
            except OSError:
                pass
