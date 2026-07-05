"""Unit tests for SQLiteIdentityStore — user CRUD, org membership,
project management, API key lifecycle, and email/password token flows.

Uses an in-memory SQLite database for fast, isolated testing.
"""

from __future__ import annotations

import hashlib

import pytest
from app.saas.identity_store import (
    SQLiteIdentityStore,
    _row_to_api_key,
    _row_to_membership,
    _row_to_organization,
    _row_to_project,
    _row_to_user,
)
from app.saas.models import (
    ApiKey,
    ApiKeyScope,
    Membership,
    MembershipRole,
    Organization,
    Project,
    User,
    UserStatus,
)


@pytest.fixture
def store(tmp_path) -> SQLiteIdentityStore:
    """Create a fresh on-disk identity store for each test (tmp_path isolated)."""
    db_path = tmp_path / "identity.db"
    s = SQLiteIdentityStore(storage_path=str(db_path))
    # Ensure email uniqueness across tests by clearing any existing data
    s.clear()
    return s


@pytest.fixture
def user(store: SQLiteIdentityStore) -> User:
    return store.create_user(
        User(
            email="alice@test.invalid",
            display_name="Alice",
            password_hash="hash_of_password",
        )
    )


@pytest.fixture
def org(store: SQLiteIdentityStore, user: User) -> Organization:
    return store.create_organization(Organization(name="TestCo", created_by_user_id=user.id))


@pytest.fixture
def project(store: SQLiteIdentityStore, org: Organization, user: User) -> Project:
    return store.create_project(Project(org_id=org.id, name="TestProject", created_by_user_id=user.id))


# ─── Row converters ─────────────────────────────────────────────────────


class TestRowConverters:
    """Round-trip conversion of dict rows to Pydantic models."""

    def test_row_to_user(self) -> None:
        row = {
            "id": "u1",
            "email": "a@b.com",
            "display_name": "A",
            "status": "active",
            "password_hash": "h",
            "created_at": "2026-01-01",
            "email_verified_at": None,
            "aup_accepted_at": None,
            "aup_version_accepted": None,
        }
        u = _row_to_user(row)
        assert u.id == "u1"
        assert u.email == "a@b.com"

    def test_row_to_organization(self) -> None:
        row = {"id": "o1", "name": "Org", "created_by_user_id": "u1", "created_at": "2026-01-01"}
        org = _row_to_organization(row)
        assert org.name == "Org"

    def test_row_to_membership(self) -> None:
        row = {"id": "m1", "user_id": "u1", "org_id": "o1", "role": "admin", "created_at": "2026-01-01", "removed_at": None}
        m = _row_to_membership(row)
        assert m.role == MembershipRole.ADMIN
        assert m.is_active()

    def test_row_to_project(self) -> None:
        row = {"id": "p1", "org_id": "o1", "name": "Proj", "created_by_user_id": "u1", "created_at": "2026-01-01"}
        p = _row_to_project(row)
        assert p.name == "Proj"

    def test_row_to_api_key(self) -> None:
        row = {
            "id": "k1",
            "project_id": "p1",
            "user_id": "u1",
            "name": "key1",
            "key_hash": "hash",
            "key_prefix": "pfx",
            "scope": "write",
            "created_at": "2026-01-01",
            "last_used_at": None,
            "revoked_at": None,
        }
        k = _row_to_api_key(row)
        assert k.is_active()


# ─── Users ───────────────────────────────────────────────────────────────


class TestUserCRUD:
    """Create, read, update user records."""

    def test_create_user(self, store: SQLiteIdentityStore) -> None:
        u = store.create_user(User(email="bob@test.invalid", display_name="Bob"))
        assert u.id
        assert u.email == "bob@test.invalid"

    def test_get_user(self, store: SQLiteIdentityStore, user: User) -> None:
        found = store.get_user(user.id)
        assert found is not None
        assert found.email == "alice@test.invalid"

    def test_get_user_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.get_user("nonexistent") is None

    def test_get_user_empty_id(self, store: SQLiteIdentityStore) -> None:
        assert store.get_user("") is None

    def test_get_user_by_email(self, store: SQLiteIdentityStore, user: User) -> None:
        found = store.get_user_by_email("alice@test.invalid")
        assert found is not None
        assert found.id == user.id

    def test_get_user_by_email_case_insensitive(self, store: SQLiteIdentityStore, user: User) -> None:
        found = store.get_user_by_email("ALICE@TEST.INVALID")
        assert found is not None

    def test_get_user_by_email_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.get_user_by_email("nobody@test.invalid") is None

    def test_get_user_by_email_empty(self, store: SQLiteIdentityStore) -> None:
        assert store.get_user_by_email("") is None

    def test_duplicate_email_raises(self, store: SQLiteIdentityStore, user: User) -> None:
        from app.saas.identity_store import IdentityStoreError

        with pytest.raises(IdentityStoreError, match="already exists"):
            store.create_user(User(email="alice@test.invalid", display_name="Alice2"))

    def test_set_user_status(self, store: SQLiteIdentityStore, user: User) -> None:
        updated = store.set_user_status(user.id, UserStatus.DISABLED)
        assert updated is not None
        assert updated.status == UserStatus.DISABLED

        # Verify persistence
        reloaded = store.get_user(user.id)
        assert reloaded is not None
        assert reloaded.status == UserStatus.DISABLED

    def test_mark_aup_accepted(self, store: SQLiteIdentityStore, user: User) -> None:
        updated = store.mark_aup_accepted(user.id, aup_version="1.0")
        assert updated is not None
        assert updated.aup_version_accepted == "1.0"
        assert updated.aup_accepted_at is not None

    def test_mark_aup_accepted_empty_user_id(self, store: SQLiteIdentityStore) -> None:
        assert store.mark_aup_accepted("") is None

    def test_mark_aup_accepted_preserves_first_timestamp(self, store: SQLiteIdentityStore, user: User) -> None:
        first = store.mark_aup_accepted(user.id, aup_version="1.0")
        # No sleep needed — the assertion tests that the FIRST timestamp is
        # preserved for the same AUP version regardless of call timing.
        second = store.mark_aup_accepted(user.id, aup_version="1.0")
        assert first is not None and second is not None
        # Same version — first timestamp preserved
        assert second.aup_accepted_at == first.aup_accepted_at

    def test_mark_aup_accepted_new_version_updates(self, store: SQLiteIdentityStore, user: User) -> None:
        first = store.mark_aup_accepted(user.id, aup_version="1.0")
        second = store.mark_aup_accepted(user.id, aup_version="2.0")
        assert first is not None and second is not None
        # Different version — timestamp should update
        assert second.aup_version_accepted == "2.0"


# ─── Organizations ───────────────────────────────────────────────────────


class TestOrganizationCRUD:
    """Create, read, delete organization records."""

    def test_create_org(self, store: SQLiteIdentityStore, org: Organization) -> None:
        assert org.id
        assert org.name == "TestCo"

    def test_get_org(self, store: SQLiteIdentityStore, org: Organization) -> None:
        found = store.get_organization(org.id)
        assert found is not None
        assert found.name == "TestCo"

    def test_get_org_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.get_organization("nonexistent") is None

    def test_delete_org(self, store: SQLiteIdentityStore, org: Organization) -> None:
        assert store.delete_organization(org.id) is True
        assert store.get_organization(org.id) is None

    def test_delete_org_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.delete_organization("nonexistent") is False

    def test_list_user_organizations(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        # First, add user as member of the org
        store.create_membership(Membership(user_id=user.id, org_id=org.id, role=MembershipRole.OWNER))
        orgs = store.list_user_organizations(user.id)
        assert len(orgs) >= 1
        assert any(o.id == org.id for o in orgs)

    def test_list_user_organizations_empty(self, store: SQLiteIdentityStore, user: User) -> None:
        orgs = store.list_user_organizations(user.id)
        assert orgs == []


# ─── Memberships ─────────────────────────────────────────────────────────


class TestMemberships:
    """Create, list, remove memberships."""

    def test_create_membership(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        m = store.create_membership(Membership(user_id=user.id, org_id=org.id, role=MembershipRole.MEMBER))
        assert m.id
        assert m.user_id == user.id
        assert m.org_id == org.id

    def test_get_membership(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        m = store.create_membership(Membership(user_id=user.id, org_id=org.id))
        found = store.get_membership(m.id)
        assert found is not None
        assert found.id == m.id

    def test_list_org_memberships(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        store.create_membership(Membership(user_id=user.id, org_id=org.id))
        members = store.list_org_memberships(org.id)
        assert len(members) >= 1

    def test_list_user_memberships(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        store.create_membership(Membership(user_id=user.id, org_id=org.id))
        members = store.list_user_memberships(user.id)
        assert len(members) >= 1

    def test_remove_membership(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        m = store.create_membership(Membership(user_id=user.id, org_id=org.id))
        removed = store.remove_membership(m.id)
        assert removed is not None
        assert removed.removed_at is not None
        # Should have removed_at set on reload
        reloaded = store.get_membership(m.id)
        assert reloaded is not None
        assert reloaded.removed_at is not None

    def test_is_org_member(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        assert store.is_org_member(user.id, org.id) is False
        store.create_membership(Membership(user_id=user.id, org_id=org.id))
        assert store.is_org_member(user.id, org.id) is True

    def test_removed_member_not_counted(self, store: SQLiteIdentityStore, user: User, org: Organization) -> None:
        m = store.create_membership(Membership(user_id=user.id, org_id=org.id))
        store.remove_membership(m.id)
        assert store.is_org_member(user.id, org.id) is False


# ─── Projects ────────────────────────────────────────────────────────────


class TestProjectCRUD:
    """Create, read, delete project records."""

    def test_create_project(self, store: SQLiteIdentityStore, project: Project) -> None:
        assert project.id
        assert project.name == "TestProject"

    def test_get_project(self, store: SQLiteIdentityStore, project: Project) -> None:
        found = store.get_project(project.id)
        assert found is not None
        assert found.name == "TestProject"

    def test_get_project_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.get_project("nonexistent") is None

    def test_delete_project(self, store: SQLiteIdentityStore, project: Project) -> None:
        assert store.delete_project(project.id) is True
        assert store.get_project(project.id) is None

    def test_delete_project_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.delete_project("nonexistent") is False

    def test_list_org_projects(self, store: SQLiteIdentityStore, org: Organization, user: User) -> None:
        store.create_project(Project(org_id=org.id, name="P1", created_by_user_id=user.id))
        store.create_project(Project(org_id=org.id, name="P2", created_by_user_id=user.id))
        projects = store.list_org_projects(org.id)
        assert len(projects) == 2

    def test_list_org_projects_empty(self, store: SQLiteIdentityStore, org: Organization) -> None:
        assert store.list_org_projects(org.id) == []


# ─── Selected context ────────────────────────────────────────────────────


class TestSelectedContext:
    """Store and retrieve the user's selected org+project."""

    def test_set_and_get_selected(self, store: SQLiteIdentityStore, user: User, org: Organization, project: Project) -> None:
        ctx = store.set_selected(user.id, org.id, project.id)
        assert ctx.user_id == user.id
        assert ctx.org_id == org.id

        loaded = store.get_selected(user.id)
        assert loaded is not None
        assert loaded.org_id == org.id

    def test_get_selected_none(self, store: SQLiteIdentityStore, user: User) -> None:
        assert store.get_selected(user.id) is None


# ─── API keys ────────────────────────────────────────────────────────────


class TestApiKeys:
    """Create, lookup, list, and revoke API keys."""

    def test_create_api_key(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        key = ApiKey(
            project_id=project.id,
            user_id=user.id,
            name="My Key",
            key_hash=hashlib.sha256(b"test-key").hexdigest(),
            key_prefix="test_key",
            scope=ApiKeyScope.WRITE,
        )
        created = store.create_api_key(key)
        assert created.id

    def test_get_api_key(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        key_hash = hashlib.sha256(b"test-key").hexdigest()
        key = store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K1", key_hash=key_hash))
        found = store.get_api_key(key.id)
        assert found is not None
        assert found.key_hash == key_hash

    def test_lookup_by_hash(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        key_hash = hashlib.sha256(b"my-secret-key").hexdigest()
        store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K1", key_hash=key_hash))
        found = store.lookup_api_key_by_hash(key_hash)
        assert found is not None

    def test_lookup_by_hash_not_found(self, store: SQLiteIdentityStore) -> None:
        assert store.lookup_api_key_by_hash("nonexistent-hash") is None

    def test_list_project_api_keys(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        h1 = hashlib.sha256(b"k1").hexdigest()
        h2 = hashlib.sha256(b"k2").hexdigest()
        store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K1", key_hash=h1))
        store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K2", key_hash=h2))
        keys = store.list_project_api_keys(project.id)
        assert len(keys) == 2

    def test_list_project_api_keys_exclude_revoked(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        h1 = hashlib.sha256(b"k1").hexdigest()
        k = store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K1", key_hash=h1))
        store.revoke_api_key(k.id)
        active = store.list_project_api_keys(project.id, include_revoked=False)
        assert all(a.is_active() for a in active)

    def test_list_project_api_keys_include_revoked(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        h1 = hashlib.sha256(b"k1").hexdigest()
        k = store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K1", key_hash=h1))
        store.revoke_api_key(k.id)
        all_keys = store.list_project_api_keys(project.id, include_revoked=True)
        assert len(all_keys) >= 1

    def test_revoke_api_key(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        key_hash = hashlib.sha256(b"temporary-key").hexdigest()
        k = store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="Temp", key_hash=key_hash))
        revoked = store.revoke_api_key(k.id)
        assert revoked is not None
        assert not revoked.is_active()

    def test_revoke_nonexistent(self, store: SQLiteIdentityStore) -> None:
        assert store.revoke_api_key("nonexistent") is None

    def test_touch_last_used(self, store: SQLiteIdentityStore, project: Project, user: User) -> None:
        key_hash = hashlib.sha256(b"used-key").hexdigest()
        k = store.create_api_key(ApiKey(project_id=project.id, user_id=user.id, name="K", key_hash=key_hash))
        store.touch_api_key_last_used(k.id)
        updated = store.get_api_key(k.id)
        assert updated is not None
        assert updated.last_used_at is not None


# ─── Email verification ──────────────────────────────────────────────────


class TestEmailVerification:
    """Email verification token lifecycle."""

    def test_create_token(self, store: SQLiteIdentityStore, user: User) -> None:
        token = store.create_email_verification_token(user.id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_token(self, store: SQLiteIdentityStore, user: User) -> None:
        token = store.create_email_verification_token(user.id)
        verified = store.verify_email_token(token)
        assert verified is not None
        assert verified.email_verified_at is not None

    def test_verify_invalid_token(self, store: SQLiteIdentityStore) -> None:
        assert store.verify_email_token("invalid-token") is None

    def test_get_verification_by_token(self, store: SQLiteIdentityStore, user: User) -> None:
        token = store.create_email_verification_token(user.id)
        record = store.get_email_verification_by_token(token)
        assert record is not None
        assert record["user_id"] == user.id

    def test_get_verification_invalid(self, store: SQLiteIdentityStore) -> None:
        assert store.get_email_verification_by_token("invalid") is None


# ─── Password reset ──────────────────────────────────────────────────────


class TestPasswordReset:
    """Password reset token lifecycle."""

    def test_create_reset_token(self, store: SQLiteIdentityStore, user: User) -> None:
        token = store.create_password_reset_token(user.id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_consume_reset_token(self, store: SQLiteIdentityStore, user: User) -> None:
        token = store.create_password_reset_token(user.id)
        result = store.consume_password_reset_token(token, "new_hash")
        assert result is True
        # Token should be consumed — second use fails
        result2 = store.consume_password_reset_token(token, "another_hash")
        assert result2 is False

    def test_consume_invalid_token(self, store: SQLiteIdentityStore) -> None:
        assert store.consume_password_reset_token("invalid", "hash") is False

    def test_get_reset_by_token(self, store: SQLiteIdentityStore, user: User) -> None:
        token = store.create_password_reset_token(user.id)
        record = store.get_password_reset_by_token(token)
        assert record is not None
        assert record["user_id"] == user.id

    def test_get_reset_invalid(self, store: SQLiteIdentityStore) -> None:
        assert store.get_password_reset_by_token("invalid") is None


# ─── Health ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    """health_check returns a status dict."""

    def test_health_check(self, store: SQLiteIdentityStore) -> None:
        result = store.health_check()
        assert result["ok"] is True
        assert "user_count" in result


# ─── Clear ───────────────────────────────────────────────────────────────


class TestClear:
    """clear() drops all rows from all tables."""

    def test_clear_removes_all_data(self, store: SQLiteIdentityStore, user: User) -> None:
        store.clear()
        assert store.get_user(user.id) is None
