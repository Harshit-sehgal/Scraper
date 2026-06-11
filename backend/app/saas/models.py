"""Pydantic models for the SaaS identity model.

Defines the persistent records that the request path will eventually
resolve identities against. The legacy ``created_by`` (a free-form
fingerprint) is replaced by ``user_id`` (a real ``users.id``); the
``mvp_created_by_owner`` policy in the routers is updated separately
to use ``org_id`` / ``project_id`` when the migration lands.

These models are the single source of truth for the shape of the
identity tables. The store layer (``identity_store.py``) is responsible
for translating between these objects and the underlying row format.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# EmailStr from pydantic[email] is intentionally not used: the project
# does not depend on the optional email-validator extra, and the
# conservative regex below is good enough for the MVP signup flow.
# When the project adopts pydantic[email] we can swap in ``EmailStr``
# for stricter RFC-5321 validation.


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if not value or not isinstance(value, str):
        msg = "email must be a non-empty string"
        raise ValueError(msg)
    cleaned = value.strip().lower()
    if not _EMAIL_RE.fullmatch(cleaned):
        msg = "email is not a valid address"
        raise ValueError(msg)
    return cleaned


class UserStatus(StrEnum):
    """Account state. Disabled users cannot create jobs or issue keys."""

    ACTIVE = "active"
    DISABLED = "disabled"


class User(BaseModel):
    """A single human (or service principal) that can sign in and own resources."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    display_name: str = ""
    status: UserStatus = UserStatus.ACTIVE
    password_hash: str = Field(default="", description="PBKDF2-SHA256 hash, never the raw password")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    email_verified_at: str | None = None
    aup_accepted_at: str | None = Field(
        default=None,
        description="ISO timestamp at which the user accepted the Acceptable Use Policy. None = not yet accepted.",
    )
    aup_version_accepted: str | None = Field(
        default=None,
        description="AUP version accepted by this user. None = not yet accepted.",
    )

    @field_validator("email")
    @classmethod
    def _validate_email_field(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not v or len(v) > 64:
            msg = "user id must be a non-empty string up to 64 characters"
            raise ValueError(msg)
        return v


class Organization(BaseModel):
    """A tenant. Owns projects and memberships."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    created_by_user_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v or len(v) > 120:
            msg = "organization name must be a non-empty string up to 120 characters"
            raise ValueError(msg)
        return v


class MembershipRole(StrEnum):
    """Role of a user inside an organization.

    MVP roles. Future SaaS: ``billing_admin``, ``security_auditor``,
    custom roles per plan tier.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Membership(BaseModel):
    """The relationship between a user and an organization."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    org_id: str
    role: MembershipRole = MembershipRole.MEMBER
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    removed_at: str | None = None

    def is_active(self) -> bool:
        return self.removed_at is None


class Project(BaseModel):
    """A project belongs to an organization. Jobs will be project-scoped."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    name: str
    created_by_user_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v or len(v) > 120:
            msg = "project name must be a non-empty string up to 120 characters"
            raise ValueError(msg)
        return v


class ApiKeyScope(StrEnum):
    """Permission tier for a project-scoped API key."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ApiKey(BaseModel):
    """A long-lived API key bound to a project.

    The raw key is shown to the user exactly once at creation; the
    stored record carries only ``key_hash`` (SHA-256 of the raw key)
    and ``key_prefix`` (first 8 characters of the raw key, for display
    in dashboards). All auth decisions compare the request's raw key
    against ``key_hash`` using constant-time comparison.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    user_id: str = Field(default="", description="User who created/owns the key")
    name: str
    key_hash: str
    key_prefix: str = ""
    scope: ApiKeyScope = ApiKeyScope.WRITE
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_used_at: str | None = None
    revoked_at: str | None = None

    def is_active(self) -> bool:
        return self.revoked_at is None
