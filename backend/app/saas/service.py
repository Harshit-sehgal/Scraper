"""Service layer for the SaaS identity model.

Holds the business logic on top of the ``IdentityStore``:

- ``SignupService.signup`` — creates a user + default organization +
  default project + owner membership in a single transaction.
- ``ApiKeyService.issue`` / ``authenticate`` / ``revoke`` — issue a
  raw key (shown once), store only the SHA-256 hash, look up by hash
  in constant time.
- ``MembershipService.add_member`` / ``remove_member`` /
  ``list_active_members``.
- Password hashing (PBKDF2-HMAC-SHA256 with a per-user random salt) and
  verification (constant-time ``hmac.compare_digest``).
- ``generate_api_key`` / ``hash_api_key`` — pure helpers used by the
  service and re-used by tests.

The store is passed in to keep the service unit-testable; the
module-level ``get_identity_store`` is the production wiring.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
from base64 import urlsafe_b64encode
from dataclasses import dataclass

from app.saas.identity_store import (
    IdentityStore,
    IdentityStoreError,
    get_identity_store,
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

logger = logging.getLogger(__name__)


# ─── Password hashing ────────────────────────────────────────────────
# PBKDF2-HMAC-SHA256 with 600_000 iterations (OWASP 2023+ guidance for
# SHA-256). The stored format is::
#
#     pbkdf2_sha256$<iterations>$<salt_b64url>$<hash_b64url>
#
# Iteration count is encoded so we can rotate it without breaking old
# hashes (callers can re-hash on next successful login).

_PBKDF2_ITERATIONS = 600_000
_PBKDF2_HASH_NAME = "sha256"
_PBKDF2_SALT_BYTES = 16
_PBKDF2_HASH_BYTES = 32


def hash_password(password: str) -> str:
    """Return a PBKDF2-HMAC-SHA256 password hash for *password*.

    Empty passwords are rejected. The output includes the iteration
    count and a per-call random salt.
    """
    if not password or not isinstance(password, str):
        msg = "password must be a non-empty string"
        raise ValueError(msg)
    salt = secrets.token_bytes(_PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH_NAME,
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_PBKDF2_HASH_BYTES,
    )
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        urlsafe_b64encode(derived).decode("ascii").rstrip("="),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verify of *password* against *stored_hash*.

    Returns ``False`` for any malformed hash so callers can treat the
    result as a single boolean. The hash comparison uses
    ``hmac.compare_digest`` to avoid leaking timing information.
    """
    if not password or not stored_hash or not isinstance(stored_hash, str):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = _b64decode(parts[2])
        expected = _b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH_NAME,
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    import base64

    return base64.urlsafe_b64decode(value + padding)


# ─── API key generation / hashing ────────────────────────────────────

_API_KEY_PREFIX = "dfk_"  # DataForge Key. Public, non-secret.
_API_KEY_BYTES = 32
_API_KEY_PREFIX_DISPLAY_LEN = 8


def generate_api_key() -> str:
    """Return a fresh raw API key string.

    Format: ``dfk_<43 url-safe chars>``. The ``dfk_`` prefix makes
    keys easy to recognise in logs/UI; the remaining 32 bytes
    (43 base64url chars) carry the entropy.
    """
    raw = secrets.token_urlsafe(_API_KEY_BYTES)
    return f"{_API_KEY_PREFIX}{raw}"


def hash_api_key(raw_key: str) -> str:
    """Return a SHA-256 hex digest of *raw_key*.

    Constant-time: callers should compare with ``hmac.compare_digest``.
    """
    if not raw_key:
        return ""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _key_prefix_display(raw_key: str) -> str:
    return raw_key[:_API_KEY_PREFIX_DISPLAY_LEN] if raw_key else ""


# ─── SignupService ───────────────────────────────────────────────────


@dataclass
class SignupResult:
    """Bundle returned by :meth:`SignupService.signup`."""

    user: User
    organization: Organization
    project: Project
    membership: Membership


class SignupService:
    """Create a new account with a default org + project + owner membership."""

    def __init__(self, store: IdentityStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> IdentityStore:
        return self._store or get_identity_store()

    def signup(
        self,
        email: str,
        password: str,
        *,
        display_name: str = "",
        org_name: str | None = None,
        project_name: str | None = None,
    ) -> SignupResult:
        """Create a user + default org + default project + owner membership.

        Args:
            email: validated + lowercased; must be unique.
            password: hashed with PBKDF2 before storage. Never logged.
            display_name: optional human label.
            org_name: optional override; defaults to ``"<email>'s workspace"``.
            project_name: optional override; defaults to ``"default"``.

        Raises:
            ValueError: bad email / password.
            IdentityStoreError: email already in use.
        """
        if not email or not isinstance(email, str):
            msg = "email is required"
            raise ValueError(msg)
        email_normalized = email.strip().lower()
        if "@" not in email_normalized:
            msg = "email is not valid"
            raise ValueError(msg)
        if self.store.get_user_by_email(email_normalized) is not None:
            msg = f"user with email {email_normalized!r} already exists"
            raise IdentityStoreError(msg)

        if not password or not isinstance(password, str):
            msg = "password is required"
            raise ValueError(msg)

        user = User(
            email=email_normalized,
            display_name=display_name.strip() if display_name else "",
            password_hash=hash_password(password),
        )
        self.store.create_user(user)

        org = Organization(
            name=(org_name or f"{user.display_name or user.email}'s workspace").strip()[:120],
            created_by_user_id=user.id,
        )
        self.store.create_organization(org)

        project = Project(
            org_id=org.id,
            name=(project_name or "default").strip()[:120] or "default",
            created_by_user_id=user.id,
        )
        self.store.create_project(project)

        membership = Membership(
            user_id=user.id,
            org_id=org.id,
            role=MembershipRole.OWNER,
        )
        self.store.create_membership(membership)

        return SignupResult(user=user, organization=org, project=project, membership=membership)


# ─── ApiKeyService ──────────────────────────────────────────────────


@dataclass
class IssuedApiKey:
    """Bundle returned by :meth:`ApiKeyService.issue`."""

    api_key: ApiKey
    raw_key: str  # Shown to the user exactly once; never persisted.


class ApiKeyService:
    """Issue, authenticate, and revoke project-scoped API keys."""

    def __init__(self, store: IdentityStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> IdentityStore:
        return self._store or get_identity_store()

    def issue(
        self,
        project_id: str,
        user_id: str,
        name: str,
        *,
        scope: ApiKeyScope = ApiKeyScope.WRITE,
    ) -> IssuedApiKey:
        """Create a new API key for *project_id*.

        Returns the persisted record (with hash) plus the raw key. The
        raw key is shown to the caller exactly once; subsequent
        :meth:`authenticate` calls match it against the stored hash.
        """
        if not project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not name or not name.strip():
            msg = "name is required"
            raise ValueError(msg)
        raw_key = generate_api_key()
        record = ApiKey(
            project_id=project_id,
            user_id=user_id or "",
            name=name.strip()[:120],
            key_hash=hash_api_key(raw_key),
            key_prefix=_key_prefix_display(raw_key),
            scope=scope,
        )
        self.store.create_api_key(record)
        return IssuedApiKey(api_key=record, raw_key=raw_key)

    def authenticate(self, raw_key: str) -> ApiKey | None:
        """Return the active API key matching *raw_key*, or None.

        A revoked key, a wrong key, or an empty key all return ``None``.
        On a successful match, the ``last_used_at`` column is bumped
        (best-effort; the bump is not on the auth hot path's success
        branch in tests that patch the store).
        """
        if not raw_key:
            return None
        record = self.store.lookup_api_key_by_hash(hash_api_key(raw_key))
        if record is None or not record.is_active():
            return None
        try:
            self.store.touch_api_key_last_used(record.id)
        except (IdentityStoreError, sqlite3.Error, OSError) as e:
            logger.debug("Failed to bump api_key.last_used_at for %s: %s", record.id, e)
        return record

    def revoke(self, api_key_id: str) -> ApiKey | None:
        return self.store.revoke_api_key(api_key_id)

    def list_for_project(self, project_id: str, include_revoked: bool = False) -> list[ApiKey]:
        return self.store.list_project_api_keys(project_id, include_revoked=include_revoked)


# ─── MembershipService ──────────────────────────────────────────────


class MembershipService:
    """Add, remove, and inspect org memberships."""

    def __init__(self, store: IdentityStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> IdentityStore:
        return self._store or get_identity_store()

    def add_member(
        self,
        org_id: str,
        user_id: str,
        role: MembershipRole = MembershipRole.MEMBER,
    ) -> Membership:
        if not org_id or not user_id:
            msg = "org_id and user_id are required"
            raise ValueError(msg)
        existing = [m for m in self.store.list_user_memberships(user_id) if m.org_id == org_id]
        if existing:
            msg = f"user {user_id!r} is already a member of org {org_id!r}"
            raise IdentityStoreError(msg)
        membership = Membership(user_id=user_id, org_id=org_id, role=role)
        self.store.create_membership(membership)
        return membership

    def remove_member(self, membership_id: str) -> Membership | None:
        return self.store.remove_membership(membership_id)

    def remove_user_from_org(self, user_id: str, org_id: str) -> bool:
        for m in self.store.list_user_memberships(user_id, include_removed=True):
            if m.org_id == org_id and m.is_active():
                self.store.remove_membership(m.id)
                return True
        return False

    def list_active_members(self, org_id: str) -> list[Membership]:
        return self.store.list_org_memberships(org_id, include_removed=False)

    def is_active_member(self, user_id: str, org_id: str) -> bool:
        return self.store.is_org_member(user_id, org_id)


# ─── Convenience: project + user access predicate ───────────────────


def is_user_active(user: User | None) -> bool:
    """Return True when *user* is non-disabled. ``None`` users are not active."""
    return user is not None and user.status == UserStatus.ACTIVE


__all__ = [
    "ApiKeyService",
    "IssuedApiKey",
    "MembershipService",
    "SignupResult",
    "SignupService",
    "generate_api_key",
    "hash_api_key",
    "hash_password",
    "is_user_active",
    "verify_password",
]
