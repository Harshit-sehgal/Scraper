"""Tests for email verification, password reset, and team invitation features.

Covers two layers:
1. Identity store methods (``SQLiteIdentityStore``) — unit-level.
2. SaaS router endpoints (``POST /api/saas/email-verification/...``,
   ``POST /api/saas/password-reset/...``, ``POST /api/saas/orgs/.../invitations``,
   ``POST /api/saas/invitations/.../respond``) — API-level.
"""

from __future__ import annotations

import pytest
from app.saas.identity_store import SQLiteIdentityStore, reset_identity_store
from app.saas.models import User
from app.saas.service import hash_password

# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def identity_store(tmp_path):
    """Per-test SQLite identity store. Resets the singleton."""
    store = SQLiteIdentityStore(storage_path=tmp_path / "identity_test.db")
    reset_identity_store(store)
    yield store
    reset_identity_store(None)


@pytest.fixture
def sample_user(identity_store) -> User:
    """Create and return a basic user."""
    user = User(
        email="test@example.com",
        display_name="Test User",
        password_hash=hash_password("hunter2"),
    )
    identity_store.create_user(user)
    return user


# ═══════════════════════════════════════════════════════════════════════
# Identity Store — Email Verification
# ═══════════════════════════════════════════════════════════════════════


class TestEmailVerificationStore:
    """Tests for ``SQLiteIdentityStore`` email verification methods."""

    def test_create_verification_token_returns_token(self, identity_store, sample_user):
        token = identity_store.create_email_verification_token(sample_user.id)
        assert token
        assert len(token) > 16

    def test_verify_email_token_with_valid_token(self, identity_store, sample_user):
        token = identity_store.create_email_verification_token(sample_user.id)
        user = identity_store.verify_email_token(token)
        assert user is not None
        assert user.id == sample_user.id
        assert user.email_verified_at is not None

        # Token should be consumed (second attempt returns None)
        assert identity_store.verify_email_token(token) is None

    def test_verify_email_token_rejects_invalid_token(self, identity_store):
        assert identity_store.verify_email_token("bad-token") is None
        assert identity_store.verify_email_token("") is None

    def test_verify_email_token_rejects_empty(self, identity_store):
        assert identity_store.verify_email_token("") is None
        assert identity_store.verify_email_token(None) is None  # type: ignore[arg-type]

    def test_get_email_verification_by_token(self, identity_store, sample_user):
        token = identity_store.create_email_verification_token(sample_user.id)
        record = identity_store.get_email_verification_by_token(token)
        assert record is not None
        assert record["user_id"] == sample_user.id
        assert record["consumed_at"] is None

    def test_get_email_verification_by_token_unknown(self, identity_store):
        assert identity_store.get_email_verification_by_token("nope") is None
        assert identity_store.get_email_verification_by_token("") is None

    def test_double_verification_is_idempotent(self, identity_store, sample_user):
        token = identity_store.create_email_verification_token(sample_user.id)
        first = identity_store.verify_email_token(token)
        assert first is not None
        assert first.email_verified_at is not None

        # A second token should still verify, but the email_verified_at
        # remains the first timestamp (idempotent via IS NULL guard)
        token2 = identity_store.create_email_verification_token(sample_user.id)
        second = identity_store.verify_email_token(token2)
        assert second is not None
        assert second.email_verified_at == first.email_verified_at


# ═══════════════════════════════════════════════════════════════════════
# Identity Store — Password Reset
# ═══════════════════════════════════════════════════════════════════════


class TestPasswordResetStore:
    """Tests for ``SQLiteIdentityStore`` password reset methods."""

    def test_create_reset_token_returns_token(self, identity_store, sample_user):
        token = identity_store.create_password_reset_token(sample_user.id)
        assert token
        assert len(token) > 16

    def test_consume_reset_token_updates_password(self, identity_store, sample_user):
        token = identity_store.create_password_reset_token(sample_user.id)
        new_hash = hash_password("new-password-123")
        success = identity_store.consume_password_reset_token(token, new_hash)
        assert success is True

        # Verify the password hash was updated
        user = identity_store.get_user(sample_user.id)
        assert user is not None
        assert user.password_hash == new_hash

    def test_consume_reset_token_rejects_used_token(self, identity_store, sample_user):
        token = identity_store.create_password_reset_token(sample_user.id)
        identity_store.consume_password_reset_token(token, hash_password("new-1"))
        # Second attempt should fail
        assert identity_store.consume_password_reset_token(token, hash_password("new-2")) is False

    def test_consume_reset_token_rejects_bad_token(self, identity_store):
        assert identity_store.consume_password_reset_token("bad-token", "hash") is False
        assert identity_store.consume_password_reset_token("", "hash") is False

    def test_get_password_reset_by_token(self, identity_store, sample_user):
        token = identity_store.create_password_reset_token(sample_user.id)
        record = identity_store.get_password_reset_by_token(token)
        assert record is not None
        assert record["user_id"] == sample_user.id
        assert record["consumed_at"] is None

    def test_get_password_reset_by_token_unknown(self, identity_store):
        assert identity_store.get_password_reset_by_token("nope") is None
        assert identity_store.get_password_reset_by_token("") is None


# ═══════════════════════════════════════════════════════════════════════
# Identity Store — Team Invitations
# ═══════════════════════════════════════════════════════════════════════


class TestTeamInvitationStore:
    """Tests for ``SQLiteIdentityStore`` team invitation methods."""

    def _make_org(self, identity_store, sample_user, name: str, org_id: str):
        from app.saas.models import Organization

        org = Organization(
            id=org_id,
            name=name,
            created_by_user_id=sample_user.id,
        )
        return identity_store.create_organization(org)

    def test_create_invitation(self, identity_store, sample_user):
        org = self._make_org(identity_store, sample_user, "Test Org", "org-1")
        invitation = identity_store.create_team_invitation(
            org_id=org.id,
            invited_email="invited@example.com",
            invited_by_user_id=sample_user.id,
            role="member",
        )
        assert invitation["status"] == "pending"
        assert invitation["invited_email"] == "invited@example.com"
        assert invitation["org_id"] == org.id

    def test_list_org_invitations(self, identity_store, sample_user):
        org = self._make_org(identity_store, sample_user, "List Org", "org-2")
        identity_store.create_team_invitation(org.id, "a@example.com", sample_user.id, "member")
        identity_store.create_team_invitation(org.id, "b@example.com", sample_user.id, "admin")

        invites = identity_store.list_org_invitations(org.id)
        assert len(invites) == 2

        invites_pending = identity_store.list_org_invitations(org.id, status="pending")
        assert len(invites_pending) == 2

    def test_respond_to_invitation_accept(self, identity_store, sample_user):
        org = self._make_org(identity_store, sample_user, "Accept Org", "org-3")
        invitation = identity_store.create_team_invitation(
            org.id,
            sample_user.email,
            sample_user.id,
            "member",
        )

        result = identity_store.respond_to_invitation(invitation["id"], accept=True)
        assert result is not None
        assert result["status"] == "accepted"

        # User should now be a member of the org
        assert identity_store.is_org_member(sample_user.id, org.id) is True

    def test_respond_to_invitation_decline(self, identity_store, sample_user):
        org = self._make_org(identity_store, sample_user, "Decline Org", "org-4")
        invitation = identity_store.create_team_invitation(
            org.id,
            sample_user.email,
            sample_user.id,
            "member",
        )

        result = identity_store.respond_to_invitation(invitation["id"], accept=False)
        assert result is not None
        assert result["status"] == "declined"

        # User should NOT be a member
        assert identity_store.is_org_member(sample_user.id, org.id) is False

    def test_respond_to_invitation_twice_fails(self, identity_store, sample_user):
        org = self._make_org(identity_store, sample_user, "Double Org", "org-5")
        invitation = identity_store.create_team_invitation(
            org.id,
            sample_user.email,
            sample_user.id,
            "member",
        )

        # First accept
        first = identity_store.respond_to_invitation(invitation["id"], accept=True)
        assert first is not None

        # Second response should return None
        assert identity_store.respond_to_invitation(invitation["id"], accept=True) is None

    def test_get_pending_invitation_by_email(self, identity_store, sample_user):
        org = self._make_org(identity_store, sample_user, "Pending Org", "org-6")
        identity_store.create_team_invitation(org.id, sample_user.email, sample_user.id, "member")

        pending = identity_store.get_pending_invitation_by_email(sample_user.email)
        assert pending is not None
        assert pending["org_id"] == org.id
        assert pending["status"] == "pending"

    def test_get_pending_invitation_by_email_none(self, identity_store):
        assert identity_store.get_pending_invitation_by_email("unknown@example.com") is None
        assert identity_store.get_pending_invitation_by_email("") is None

    def test_respond_to_invitation_unknown(self, identity_store):
        assert identity_store.respond_to_invitation("bad-id", accept=True) is None
        assert identity_store.respond_to_invitation("", accept=True) is None

    def test_list_org_invitations_empty(self, identity_store):
        invites = identity_store.list_org_invitations("nonexistent")
        assert invites == []

    def test_list_org_invitations_empty_id(self, identity_store):
        invites = identity_store.list_org_invitations("")
        assert invites == []


# ═══════════════════════════════════════════════════════════════════════
# API Endpoint Tests (via TestClient)
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_saas_identity_for_api_tests():
    """Reset identity store with a temp file before each API test.

    The conftest's ``_reset_identity_store_fixture`` resets the singleton
    to None, which causes API endpoint tests to fall back to the default
    path-based store. That can lead to ``no such table`` errors when the
    default store's schema hasn't been initialized for the test context.

    This fixture creates a fresh temp-file store for each API test,
    matching the pattern in ``test_saas_router.py``.
    """
    import os
    import tempfile

    from app.saas.identity_store import SQLiteIdentityStore, reset_identity_store
    from app.saas.router import reset_rate_limiters

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


class TestEmailVerificationAPI:
    """Tests for ``/api/saas/email-verification/*`` endpoints."""

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    def test_send_verification(self, client):
        # First signup
        signup = client.post(
            "/api/saas/signup",
            json={"email": "verify-send@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post("/api/saas/email-verification/send", cookies=cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert "Verification" in data["message"]

    def test_verify_email_with_token(self, client):
        from app.saas.identity_store import get_identity_store

        signup = client.post(
            "/api/saas/signup",
            json={"email": "verify-token@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        # Create a token directly via the store
        store = get_identity_store()
        token = store.create_email_verification_token(user_id)
        assert token

        resp = client.post(
            "/api/saas/email-verification/verify",
            json={"token": token},
            cookies=cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["verified"] is True

    def test_verify_email_bad_token(self, client):
        signup = client.post(
            "/api/saas/signup",
            json={"email": "verify-bad@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post(
            "/api/saas/email-verification/verify",
            json={"token": "this-is-definitely-not-a-real-token"},
            cookies=cookies,
        )
        assert resp.status_code == 400

    def test_verification_status(self, client):
        from app.saas.identity_store import get_identity_store

        signup = client.post(
            "/api/saas/signup",
            json={"email": "verify-status@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        # Before verification
        resp = client.get("/api/saas/email-verification/status", cookies=cookies)
        assert resp.status_code == 200
        assert resp.json()["email_verified"] is False

        # Verify
        store = get_identity_store()
        token = store.create_email_verification_token(user_id)
        client.post(
            "/api/saas/email-verification/verify",
            json={"token": token},
            cookies=cookies,
        )

        # After verification
        resp = client.get("/api/saas/email-verification/status", cookies=cookies)
        assert resp.status_code == 200
        assert resp.json()["email_verified"] is True


class TestPasswordResetAPI:
    """Tests for ``/api/saas/password-reset/*`` endpoints."""

    def test_request_password_reset(self, client):
        signup = client.post(
            "/api/saas/signup",
            json={"email": "reset-request@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201

        resp = client.post(
            "/api/saas/password-reset/request",
            json={"email": "reset-request@example.com"},
        )
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()

    def test_request_password_reset_unknown_email(self, client):
        """Should return 200 to prevent email enumeration."""
        resp = client.post(
            "/api/saas/password-reset/request",
            json={"email": "doesnotexist@example.com"},
        )
        assert resp.status_code == 200

    def test_confirm_password_reset(self, client):
        from app.saas.identity_store import get_identity_store

        signup = client.post(
            "/api/saas/signup",
            json={"email": "reset-confirm@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]

        # Create a reset token directly via the store
        store = get_identity_store()
        token = store.create_password_reset_token(user_id)
        assert token

        resp = client.post(
            "/api/saas/password-reset/reset",
            json={"token": token, "new_password": "NewSecurePass456!"},
        )
        assert resp.status_code == 200
        assert "reset" in resp.json()["message"].lower()

    def test_confirm_password_reset_bad_token(self, client):
        resp = client.post(
            "/api/saas/password-reset/reset",
            json={"token": "invalid-token", "new_password": "NewSecurePass456!"},
        )
        assert resp.status_code == 400

    def test_confirm_password_reset_short_password(self, client):
        resp = client.post(
            "/api/saas/password-reset/reset",
            json={"token": "some-token", "new_password": "short"},
        )
        assert resp.status_code == 422


class TestInvitationAPI:
    """Tests for invitation endpoints."""

    @staticmethod
    def _cookies_for(user_id: str, role: str = "admin") -> dict:
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        return {SESSION_COOKIE: create_session_cookie(role=role, user_id=user_id)}

    def test_create_invitation(self, client):
        # Create an org
        org_resp = client.post("/api/saas/orgs", json={"name": "Invite Org"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Create invitation
        resp = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "invited@example.com", "role": "member"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["invited_email"] == "invited@example.com"
        assert data["org_id"] == org_id

    def test_list_org_invitations(self, client):
        org_resp = client.post("/api/saas/orgs", json={"name": "List Invites"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "a@example.com", "role": "member"},
        )
        client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "b@example.com", "role": "admin"},
        )

        resp = client.get(f"/api/saas/orgs/{org_id}/invitations")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_accept_invitation(self, client):
        from app.saas.identity_store import get_identity_store

        # Signup as the inviter
        signup = client.post(
            "/api/saas/signup",
            json={"email": "inviter@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        inviter_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        cookies = self._cookies_for(inviter_id)

        # Create invitation
        inv = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "invited-user@example.com", "role": "member"},
            cookies=cookies,
        )
        assert inv.status_code == 201
        invitation_id = inv.json()["id"]

        # Now create the invited user and accept
        # First, create a user with the invited email
        store = get_identity_store()
        from app.saas.models import User
        from app.saas.service import hash_password

        store.create_user(
            User(
                email="invited-user@example.com",
                password_hash=hash_password("hunter2"),
            )
        )
        invited_user = store.get_user_by_email("invited-user@example.com")
        assert invited_user is not None
        invited_cookies = self._cookies_for(invited_user.id)

        resp = client.post(
            f"/api/saas/invitations/{invitation_id}/respond",
            json={"accept": True},
            cookies=invited_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # Verify the user is now a member
        assert store.is_org_member(invited_user.id, org_id) is True

    def test_decline_invitation(self, client):
        from app.saas.identity_store import get_identity_store

        signup = client.post(
            "/api/saas/signup",
            json={"email": "decliner-owner@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        owner_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        cookies = self._cookies_for(owner_id)

        inv = client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "decliner-user@example.com", "role": "member"},
            cookies=cookies,
        )
        assert inv.status_code == 201
        invitation_id = inv.json()["id"]

        store = get_identity_store()
        from app.saas.models import User
        from app.saas.service import hash_password

        store.create_user(
            User(
                email="decliner-user@example.com",
                password_hash=hash_password("hunter2"),
            )
        )
        declined_user = store.get_user_by_email("decliner-user@example.com")
        assert declined_user is not None
        declined_cookies = self._cookies_for(declined_user.id)

        resp = client.post(
            f"/api/saas/invitations/{invitation_id}/respond",
            json={"accept": False},
            cookies=declined_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "declined"

        # Verify the user is NOT a member
        assert store.is_org_member(declined_user.id, org_id) is False

    def test_respond_to_unknown_invitation(self, client):
        signup = client.post(
            "/api/saas/signup",
            json={"email": "unknown-invite@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.post(
            "/api/saas/invitations/nonexistent-id/respond",
            json={"accept": True},
            cookies=cookies,
        )
        assert resp.status_code == 404

    def test_get_pending_invitations(self, client):
        from app.saas.identity_store import get_identity_store

        # Create org and invite
        signup = client.post(
            "/api/saas/signup",
            json={"email": "owner-pending@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        owner_id = signup.json()["user_id"]
        org_id = signup.json()["organization_id"]
        cookies = self._cookies_for(owner_id)

        client.post(
            f"/api/saas/orgs/{org_id}/invitations",
            json={"email": "pending-user@example.com", "role": "member"},
            cookies=cookies,
        )

        # Create invited user and check pending
        store = get_identity_store()
        from app.saas.models import User
        from app.saas.service import hash_password

        store.create_user(
            User(
                email="pending-user@example.com",
                password_hash=hash_password("hunter2"),
            )
        )
        invited_user = store.get_user_by_email("pending-user@example.com")
        assert invited_user is not None
        invited_cookies = self._cookies_for(invited_user.id)

        resp = client.get("/api/saas/invitations/pending", cookies=invited_cookies)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["invited_email"] == "pending-user@example.com"

    def test_get_pending_invitations_empty(self, client):
        signup = client.post(
            "/api/saas/signup",
            json={"email": "no-pending@example.com", "password": "SecurePass123!"},
        )
        assert signup.status_code == 201
        user_id = signup.json()["user_id"]
        cookies = self._cookies_for(user_id)

        resp = client.get("/api/saas/invitations/pending", cookies=cookies)
        assert resp.status_code == 200
        assert resp.json() == []
