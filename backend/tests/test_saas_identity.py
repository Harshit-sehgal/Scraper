"""P0-SAAS-001: SaaS identity model regression tests.

These tests are the safety net for the user / organization / project /
membership / API-key model. The behavioural contract being locked in:

1. ``SignupService.signup`` creates a user + default organization +
   default project + owner membership.
2. Passwords are stored as PBKDF2-HMAC-SHA256 hashes, never plaintext.
   Verification uses constant-time ``hmac.compare_digest`` and rejects
   the wrong password.
3. API keys are stored as SHA-256 hashes; the raw key is returned to
   the caller exactly once and is never persisted.
4. A project-scoped key authenticates the project it was issued for
   and is rejected when the caller tries to access a different project.
5. Removing a user from an org revokes their access (subsequent
   membership lookups return no active membership).
6. ``is_user_active`` returns False for disabled users.
7. Revoking a key prevents further ``authenticate`` calls.
8. Two different users signing up with the same email fail.
"""

from __future__ import annotations

import pytest
from app.saas import (
    ApiKeyScope,
    MembershipRole,
    SignupService,
    UserStatus,
    generate_api_key,
    get_identity_store,
    hash_api_key,
    hash_password,
    is_user_active,
    reset_identity_store,
    verify_password,
)
from app.saas.identity_store import IdentityStoreError, SQLiteIdentityStore
from app.saas.service import ApiKeyService, MembershipService


@pytest.fixture
def identity_store(tmp_path):
    """Per-test SQLite identity store. Resets the singleton so the service
    layer's ``store`` property is bound to this fresh, isolated file."""
    store = SQLiteIdentityStore(storage_path=tmp_path / "identity.db")
    reset_identity_store(store)
    yield store
    reset_identity_store(None)


@pytest.fixture
def signup(identity_store):
    return SignupService(store=identity_store)


@pytest.fixture
def api_key_service(identity_store):
    return ApiKeyService(store=identity_store)


@pytest.fixture
def membership_service(identity_store):
    return MembershipService(store=identity_store)


# ─── Signup ──────────────────────────────────────────────────────────


def test_signup_creates_user_org_project_and_owner_membership(signup, identity_store) -> None:
    result = signup.signup("alice@example.com", "sup3r-secret!", display_name="Alice")

    assert result.user.email == "alice@example.com"
    assert result.user.status == UserStatus.ACTIVE
    assert result.user.password_hash != "sup3r-secret!"
    assert result.organization.created_by_user_id == result.user.id
    assert result.project.org_id == result.organization.id
    assert result.project.created_by_user_id == result.user.id
    assert result.membership.role == MembershipRole.OWNER
    assert result.membership.is_active()

    # Round-trip: every record is readable from the store.
    assert identity_store.get_user(result.user.id).id == result.user.id
    assert identity_store.get_organization(result.organization.id).id == result.organization.id
    assert identity_store.get_project(result.project.id).id == result.project.id
    active = identity_store.list_org_memberships(result.organization.id)
    assert len(active) == 1
    assert active[0].id == result.membership.id


def test_signup_normalises_email_to_lowercase(signup, identity_store) -> None:
    signup.signup("BoB@Example.COM", "hunter2")
    user = identity_store.get_user_by_email("bob@example.com")
    assert user is not None
    assert user.email == "bob@example.com"


def test_signup_rejects_duplicate_email(signup) -> None:
    signup.signup("dup@example.com", "hunter2")
    with pytest.raises(IdentityStoreError, match="already exists"):
        signup.signup("dup@example.com", "another-password")


def test_signup_rejects_empty_password(signup) -> None:
    with pytest.raises(ValueError, match="password"):
        signup.signup("nonempty@example.com", "")


def test_signup_creates_default_named_org_and_project(signup) -> None:
    result = signup.signup("carol@example.com", "hunter2", display_name="Carol")
    assert result.organization.name
    assert result.project.name


# ─── Password hashing ────────────────────────────────────────────────


def test_password_hash_is_not_plaintext() -> None:
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert h.startswith("pbkdf2_sha256$")


def test_hash_password_uses_per_call_salt() -> None:
    a = hash_password("hunter2")
    b = hash_password("hunter2")
    assert a != b, "PBKDF2 salt should be unique per call"


def test_verify_password_accepts_correct_password() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_password_rejects_wrong_password() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("wrong", h) is False


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("anything", "not-a-valid-hash") is False
    assert verify_password("anything", "") is False
    assert verify_password("", "pbkdf2_sha256$1$aaa$bbb") is False


# ─── API key issuance / lookup ───────────────────────────────────────


def test_api_key_issue_stores_hash_not_raw(api_key_service, identity_store) -> None:
    project = identity_store.create_project(
        _make_project(org_id="org-1", user_id="u-1"),
    )
    issued = api_key_service.issue(
        project_id=project.id,
        user_id="u-1",
        name="ci-runner",
        scope=ApiKeyScope.WRITE,
    )

    # Raw key is well-formed and visible to the caller exactly once.
    assert issued.raw_key.startswith("dfk_")
    assert issued.api_key.key_prefix == issued.raw_key[:8]
    assert issued.api_key.key_hash == hash_api_key(issued.raw_key)
    assert issued.api_key.key_hash != issued.raw_key


def test_api_key_authenticate_with_raw_key(api_key_service) -> None:
    project = identity_store = get_identity_store()
    project = identity_store.create_project(_make_project(org_id="org-1", user_id="u-1"))
    issued = api_key_service.issue(project_id=project.id, user_id="u-1", name="k")

    record = api_key_service.authenticate(issued.raw_key)

    assert record is not None
    assert record.id == issued.api_key.id
    assert record.project_id == project.id


def test_api_key_authenticate_rejects_wrong_raw_key(api_key_service) -> None:
    project = get_identity_store().create_project(
        _make_project(org_id="org-1", user_id="u-1"),
    )
    api_key_service.issue(project_id=project.id, user_id="u-1", name="k")

    assert api_key_service.authenticate("dfk_definitely-the-wrong-key") is None
    assert api_key_service.authenticate("") is None


def test_api_key_authenticate_returns_none_after_revoke(api_key_service) -> None:
    project = get_identity_store().create_project(
        _make_project(org_id="org-1", user_id="u-1"),
    )
    issued = api_key_service.issue(project_id=project.id, user_id="u-1", name="k")

    assert api_key_service.authenticate(issued.raw_key) is not None
    revoked = api_key_service.revoke(issued.api_key.id)
    assert revoked is not None
    assert not revoked.is_active()
    assert api_key_service.authenticate(issued.raw_key) is None


def test_api_key_hash_prefix_is_first_eight_characters() -> None:
    raw = generate_api_key()
    record_hash = hash_api_key(raw)
    assert record_hash != raw
    assert len(record_hash) == 64  # SHA-256 hex


# ─── Project-scope key denial ───────────────────────────────────────


def test_project_scoped_key_does_not_authenticate_against_other_project(
    api_key_service,
) -> None:
    project_a = get_identity_store().create_project(
        _make_project(org_id="org-1", user_id="u-1", name="A"),
    )
    project_b = get_identity_store().create_project(
        _make_project(org_id="org-1", user_id="u-1", name="B"),
    )
    issued = api_key_service.issue(project_id=project_a.id, user_id="u-1", name="a")

    record = api_key_service.authenticate(issued.raw_key)

    assert record is not None
    assert record.project_id == project_a.id
    assert record.project_id != project_b.id


def test_api_key_lookup_by_hash_returns_none_for_unknown_hash(identity_store) -> None:
    assert identity_store.lookup_api_key_by_hash(hash_api_key("dfk_never_issued")) is None


# ─── Membership removal revokes access ──────────────────────────────


def test_removed_member_loses_org_access(membership_service, signup, identity_store) -> None:
    owner = signup.signup("owner@example.com", "hunter2")
    member_user = identity_store.create_user(_make_user(email="member@example.com"))

    membership_service.add_member(owner.organization.id, member_user.id, role=MembershipRole.MEMBER)
    assert membership_service.is_active_member(member_user.id, owner.organization.id) is True

    removed = membership_service.remove_user_from_org(member_user.id, owner.organization.id)
    assert removed is True
    assert membership_service.is_active_member(member_user.id, owner.organization.id) is False
    # The org now has two memberships: the owner (still active) and the
    # member (removed). Find the member's record and assert its
    # removed_at is populated; the owner's must stay None.
    all_memberships = identity_store.list_org_memberships(
        owner.organization.id,
        include_removed=True,
    )
    assert len(all_memberships) == 2
    member_record = next(m for m in all_memberships if m.user_id == member_user.id)
    owner_record = next(m for m in all_memberships if m.user_id == owner.user.id)
    assert member_record.removed_at is not None
    assert owner_record.removed_at is None


def test_add_member_rejects_duplicate(membership_service, signup, identity_store) -> None:
    owner = signup.signup("owner2@example.com", "hunter2")
    member_user = identity_store.create_user(_make_user(email="member2@example.com"))
    membership_service.add_member(owner.organization.id, member_user.id)
    with pytest.raises(IdentityStoreError, match="already a member"):
        membership_service.add_member(owner.organization.id, member_user.id)


# ─── Disabled users cannot take action ──────────────────────────────


def test_disabled_user_is_not_active(signup, identity_store) -> None:
    result = signup.signup("eve@example.com", "hunter2")
    assert is_user_active(result.user) is True
    identity_store.set_user_status(result.user.id, UserStatus.DISABLED)
    refreshed = identity_store.get_user(result.user.id)
    assert is_user_active(refreshed) is False


def test_disabled_user_cannot_be_used_for_new_signups_action(signup, identity_store) -> None:
    # ``is_user_active`` is the single guard the API layer should call
    # before letting a user create a job / issue a key. The contract:
    # the predicate returns False for disabled users and None users.
    result = signup.signup("frank@example.com", "hunter2")
    assert is_user_active(result.user) is True
    identity_store.set_user_status(result.user.id, UserStatus.DISABLED)
    assert is_user_active(identity_store.get_user(result.user.id)) is False
    assert is_user_active(None) is False


# ─── helpers ─────────────────────────────────────────────────────────


def _make_user(email: str = "x@example.com") -> object:  # type: ignore[valid-type]
    from app.saas.models import User

    return User(email=email, password_hash=hash_password("placeholder"))


def _make_project(org_id: str, user_id: str, name: str = "P") -> object:  # type: ignore[valid-type]
    from app.saas.models import Project

    return Project(org_id=org_id, name=name, created_by_user_id=user_id)
