"""SaaS identity package — users, organizations, projects, memberships, API keys.

This package scaffolds the persistent identity model that the rest of
the product will move to once the legacy env-backed API-key auth is
retired. It is intentionally decoupled from the job store: a separate
SQLite file is used so that the new identity tables can be deployed
alongside the existing v7 job schema without a complex dual-store
migration. When the identity model is wired into the request path,
``rbac.resolve_auth_context`` will consult this store to map
persistent API-key hashes to ``user_id`` / ``org_id`` / ``project_id``.

Public surface:
- ``models``: User, Organization, Membership, Project, ApiKey, enums.
- ``identity_store``: abstract ``IdentityStore`` + SQLite implementation.
- ``service``: ``SignupService``, ``ApiKeyService``, ``MembershipService``,
  password-hash helpers, and raw-key generation.
- ``CURRENT_AUP_VERSION``: the active Acceptable Use Policy version
  enforced by ``app.utils.aup.require_aup_accepted``. Lives here so
  routers and the enforcement dependency can share it without a cycle.

Tests live in ``backend/tests/test_saas_identity.py``.
"""

from app.saas.identity_store import (
    IdentityStore,
    SQLiteIdentityStore,
    get_identity_store,
    reset_identity_store,
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
from app.saas.service import (
    ApiKeyService,
    MembershipService,
    SignupService,
    generate_api_key,
    hash_api_key,
    hash_password,
    is_user_active,
    verify_password,
)

# Active Acceptable Use Policy version. Callers that gate behaviour on
# which AUP revision a user has accepted compare against this constant.
# Defined here (instead of in ``saas.router``) so ``app.utils.aup`` can
# import it at module load time without creating an import cycle
# through the router module that already depends on
# ``require_aup_accepted``.
CURRENT_AUP_VERSION = "2026-06-11-v1"

__all__ = [
    "CURRENT_AUP_VERSION",
    "ApiKey",
    "ApiKeyScope",
    "ApiKeyService",
    "IdentityStore",
    "Membership",
    "MembershipRole",
    "MembershipService",
    "Organization",
    "Project",
    "SQLiteIdentityStore",
    "SignupService",
    "User",
    "UserStatus",
    "generate_api_key",
    "get_identity_store",
    "hash_api_key",
    "hash_password",
    "is_user_active",
    "reset_identity_store",
    "verify_password",
]
