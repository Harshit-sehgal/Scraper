"""SQLite-backed identity store for the SaaS model.

Defines the ``IdentityStore`` contract and a concrete SQLite
implementation. Tables:

- ``users`` (id PK, email UNIQUE, password_hash, status, …)
- ``organizations`` (id PK, name, created_by_user_id)
- ``memberships`` (id PK, user_id, org_id, role, removed_at; UNIQUE(user_id, org_id))
- ``projects`` (id PK, org_id, name, created_by_user_id)
- ``api_keys`` (id PK, project_id, user_id, key_hash UNIQUE, key_prefix, scope, revoked_at)

The store is intentionally separate from ``job_store`` so the legacy
v7 job schema can stay untouched. When a single shared DB is desired
later, the schema helpers can be merged with ``app/job_store.py``'s
v8 migration.

The module-level singleton (``_identity_store``) is overridable in
tests via ``reset_identity_store``.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.saas.models import (
    ApiKey,
    ApiKeyScope,
    Membership,
    MembershipRole,
    Organization,
    Project,
    SelectedContext,
    User,
    UserStatus,
)

logger = logging.getLogger(__name__)


# Exceptions the store may raise. We surface DB errors as ``IdentityStoreError``
# so callers do not have to import ``sqlite3``.
class IdentityStoreError(RuntimeError):
    """Raised for any persistence error in the identity store."""


# Tuple of expected errors for fallback / log-only paths.
_DB_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    sqlite3.Error,
)


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _row_to_user(row: sqlite3.Row | dict) -> User:
    return User.model_validate(
        {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"] or "",
            "status": row["status"] or UserStatus.ACTIVE.value,
            "password_hash": row["password_hash"] or "",
            "created_at": row["created_at"] or "",
            "email_verified_at": row["email_verified_at"] or None,
            "aup_accepted_at": row["aup_accepted_at"] or None,
            "aup_version_accepted": row["aup_version_accepted"] or None,
        },
    )


def _row_to_organization(row: sqlite3.Row | dict) -> Organization:
    return Organization.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"] or "",
        },
    )


def _row_to_membership(row: sqlite3.Row | dict) -> Membership:
    return Membership.model_validate(
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "org_id": row["org_id"],
            "role": row["role"] or MembershipRole.MEMBER.value,
            "created_at": row["created_at"] or "",
            "removed_at": row["removed_at"] or None,
        },
    )


def _row_to_project(row: sqlite3.Row | dict) -> Project:
    return Project.model_validate(
        {
            "id": row["id"],
            "org_id": row["org_id"],
            "name": row["name"],
            "created_by_user_id": row["created_by_user_id"],
            "created_at": row["created_at"] or "",
        },
    )


def _row_to_api_key(row: sqlite3.Row | dict) -> ApiKey:
    return ApiKey.model_validate(
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "user_id": row["user_id"] or "",
            "name": row["name"],
            "key_hash": row["key_hash"],
            "key_prefix": row["key_prefix"] or "",
            "scope": row["scope"] or ApiKeyScope.WRITE.value,
            "created_at": row["created_at"] or "",
            "last_used_at": row["last_used_at"] or None,
            "revoked_at": row["revoked_at"] or None,
        },
    )


# ───────────────────────────────────────────────────────────────────────
# Abstract contract
# ───────────────────────────────────────────────────────────────────────


class IdentityStore(ABC):
    """Persistent store for users, organizations, memberships, projects, API keys."""

    @abstractmethod
    def create_user(self, user: User) -> User: ...

    @abstractmethod
    def get_user(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_user_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def set_user_status(self, user_id: str, status: UserStatus) -> User | None: ...

    @abstractmethod
    def mark_aup_accepted(
        self,
        user_id: str,
        accepted_at: str | None = None,
        aup_version: str | None = None,
    ) -> User | None: ...

    @abstractmethod
    def create_organization(self, org: Organization) -> Organization: ...

    @abstractmethod
    def get_organization(self, org_id: str) -> Organization | None: ...

    @abstractmethod
    def delete_organization(self, org_id: str) -> bool: ...

    @abstractmethod
    def list_user_organizations(self, user_id: str, include_removed: bool = False) -> list[Organization]: ...

    @abstractmethod
    def create_membership(self, membership: Membership) -> Membership: ...

    @abstractmethod
    def list_org_memberships(self, org_id: str, include_removed: bool = False) -> list[Membership]: ...

    @abstractmethod
    def list_user_memberships(self, user_id: str, include_removed: bool = False) -> list[Membership]: ...

    @abstractmethod
    def get_membership(self, membership_id: str) -> Membership | None: ...

    @abstractmethod
    def remove_membership(self, membership_id: str) -> Membership | None: ...

    @abstractmethod
    def is_org_member(self, user_id: str, org_id: str) -> bool: ...

    @abstractmethod
    def create_project(self, project: Project) -> Project: ...

    @abstractmethod
    def get_project(self, project_id: str) -> Project | None: ...

    @abstractmethod
    def delete_project(self, project_id: str) -> bool: ...

    @abstractmethod
    def list_org_projects(self, org_id: str) -> list[Project]: ...

    @abstractmethod
    def set_selected(self, user_id: str, org_id: str, project_id: str) -> SelectedContext: ...

    @abstractmethod
    def get_selected(self, user_id: str) -> SelectedContext | None: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def create_api_key(self, api_key: ApiKey) -> ApiKey: ...

    @abstractmethod
    def get_api_key(self, api_key_id: str) -> ApiKey | None: ...

    @abstractmethod
    def lookup_api_key_by_hash(self, key_hash: str) -> ApiKey | None: ...

    @abstractmethod
    def list_project_api_keys(self, project_id: str, include_revoked: bool = False) -> list[ApiKey]: ...

    @abstractmethod
    def revoke_api_key(self, api_key_id: str) -> ApiKey | None: ...

    @abstractmethod
    def touch_api_key_last_used(self, api_key_id: str) -> None: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    # ── Email Verification ────────────────────────────────────────────────

    @abstractmethod
    def create_email_verification_token(self, user_id: str) -> str: ...

    @abstractmethod
    def verify_email_token(self, token: str) -> User | None: ...

    @abstractmethod
    def get_email_verification_by_token(self, token: str) -> dict | None: ...

    # ── Password Reset ────────────────────────────────────────────────

    @abstractmethod
    def create_password_reset_token(self, user_id: str) -> str: ...

    @abstractmethod
    def consume_password_reset_token(self, token: str, new_password_hash: str) -> bool: ...

    @abstractmethod
    def get_password_reset_by_token(self, token: str) -> dict | None: ...

    # ── Team Invitations ──────────────────────────────────────────────

    @abstractmethod
    def create_team_invitation(self, org_id: str, invited_email: str, invited_by_user_id: str, role: str) -> dict: ...

    @abstractmethod
    def list_org_invitations(self, org_id: str, status: str | None = None) -> list[dict]: ...

    @abstractmethod
    def respond_to_invitation(self, invitation_id: str, accept: bool) -> dict | None: ...

    @abstractmethod
    def get_pending_invitation_by_email(self, email: str) -> dict | None: ...


# ───────────────────────────────────────────────────────────────────────
# SQLite implementation
# ───────────────────────────────────────────────────────────────────────


class SQLiteIdentityStore(IdentityStore):
    """Single-file SQLite store. Thread-safe via a per-instance lock.

    The DB file is created on first use. A separate file is used so the
    SaaS identity tables can be deployed alongside the v7 job schema
    without touching ``app/job_store.py``. The path is overridable for
    tests (see ``get_identity_store`` and ``reset_identity_store``).
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        if storage_path is None:
            storage_path = self._default_path()
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialized = False
        self._init_schema()

    @staticmethod
    def _default_path() -> Path:
        from app.config import settings

        if getattr(settings, "IDENTITY_DB_PATH", ""):
            return Path(settings.IDENTITY_DB_PATH).expanduser()
        # Co-locate with the job store, but use a different file.
        from app.job_store import _get_db_path

        return _get_db_path().with_name("identity.db")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        if self._initialized:
            return
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    password_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    email_verified_at TEXT DEFAULT NULL,
                    aup_accepted_at TEXT DEFAULT NULL,
                    aup_version_accepted TEXT DEFAULT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_organizations_creator
                    ON organizations(created_by_user_id);

                CREATE TABLE IF NOT EXISTS memberships (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    created_at TEXT NOT NULL DEFAULT '',
                    removed_at TEXT DEFAULT NULL,
                    UNIQUE(user_id, org_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memberships_user
                    ON memberships(user_id, removed_at);
                CREATE INDEX IF NOT EXISTS idx_memberships_org
                    ON memberships(org_id, removed_at);

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);

                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_prefix TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'write',
                    created_at TEXT NOT NULL DEFAULT '',
                    last_used_at TEXT DEFAULT NULL,
                    revoked_at TEXT DEFAULT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_api_keys_project
                    ON api_keys(project_id, revoked_at);

                CREATE TABLE IF NOT EXISTS user_selections (
                    user_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL DEFAULT '',
                    consumed_at TEXT DEFAULT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_email_verification_user
                    ON email_verification_tokens(user_id);

                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL DEFAULT '',
                    consumed_at TEXT DEFAULT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_password_reset_user
                    ON password_reset_tokens(user_id);

                CREATE TABLE IF NOT EXISTS team_invitations (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    invited_email TEXT NOT NULL,
                    invited_by_user_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL DEFAULT '',
                    responded_at TEXT DEFAULT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_team_invitations_org
                    ON team_invitations(org_id);
                CREATE INDEX IF NOT EXISTS idx_team_invitations_email
                    ON team_invitations(invited_email);
                """,
            )
            with suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE users ADD COLUMN aup_version_accepted TEXT DEFAULT NULL")
            conn.commit()
        self._initialized = True

    # ── Users ─────────────────────────────────────────────────────────

    def create_user(self, user: User) -> User:
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users
                        (id, email, display_name, status, password_hash,
                         created_at, email_verified_at, aup_accepted_at, aup_version_accepted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.id,
                        user.email.lower(),
                        user.display_name or "",
                        user.status.value,
                        user.password_hash or "",
                        user.created_at or _now_iso(),
                        user.email_verified_at,
                        user.aup_accepted_at,
                        user.aup_version_accepted,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                msg = f"user with email {user.email!r} already exists"
                raise IdentityStoreError(msg) from e
        return user

    def get_user(self, user_id: str) -> User | None:
        if not user_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        if not email:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email.strip(),),
            ).fetchone()
        return _row_to_user(row) if row else None

    def set_user_status(self, user_id: str, status: UserStatus) -> User | None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET status = ? WHERE id = ?",
                (status.value, user_id),
            )
            conn.commit()
        return self.get_user(user_id)

    def mark_aup_accepted(
        self,
        user_id: str,
        accepted_at: str | None = None,
        aup_version: str | None = None,
    ) -> User | None:
        """Record that *user_id* accepted the Acceptable Use Policy.

        ``accepted_at`` defaults to "now" in UTC ISO format. Re-accepting
        the same AUP version keeps the first timestamp. Accepting a new
        AUP version updates both the version and acceptance timestamp.

        Returns the updated user, or ``None`` if no such user exists.
        """
        if not user_id:
            return None
        new_ts = (accepted_at or _now_iso()).strip() or _now_iso()
        version = (aup_version or "").strip()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET
                    aup_accepted_at = CASE
                        WHEN aup_accepted_at IS NULL OR COALESCE(aup_version_accepted, '') != ?
                        THEN ?
                        ELSE aup_accepted_at
                    END,
                    aup_version_accepted = CASE
                        WHEN COALESCE(aup_version_accepted, '') != ?
                        THEN ?
                        ELSE aup_version_accepted
                    END
                WHERE id = ?
                """,
                (version, new_ts, version, version, user_id),
            )
            conn.commit()
        return self.get_user(user_id)

    # ── Organizations ─────────────────────────────────────────────────

    def create_organization(self, org: Organization) -> Organization:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO organizations
                    (id, name, created_by_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    org.id,
                    org.name,
                    org.created_by_user_id,
                    org.created_at or _now_iso(),
                ),
            )
            conn.commit()
        return org

    def get_organization(self, org_id: str) -> Organization | None:
        if not org_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM organizations WHERE id = ?",
                (org_id,),
            ).fetchone()
        return _row_to_organization(row) if row else None

    def delete_organization(self, org_id: str) -> bool:
        if not org_id:
            return False
        with self._lock, self._connect() as conn:
            # Cascade: drop api keys for any projects of this org, then
            # the projects, memberships, user_selections pointing at the
            # org, and finally the org row.
            conn.execute(
                "DELETE FROM api_keys WHERE project_id IN (SELECT id FROM projects WHERE org_id = ?)",
                (org_id,),
            )
            conn.execute("DELETE FROM projects WHERE org_id = ?", (org_id,))
            conn.execute("DELETE FROM memberships WHERE org_id = ?", (org_id,))
            conn.execute("DELETE FROM user_selections WHERE org_id = ?", (org_id,))
            cursor = conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_user_organizations(self, user_id: str, include_removed: bool = False) -> list[Organization]:
        if not user_id:
            return []
        sql = "SELECT o.* FROM organizations o INNER JOIN memberships m ON m.org_id = o.id WHERE m.user_id = ?"
        if not include_removed:
            sql += " AND m.removed_at IS NULL"
        sql += " ORDER BY o.created_at ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return [_row_to_organization(r) for r in rows]

    # ── Memberships ───────────────────────────────────────────────────

    def create_membership(self, membership: Membership) -> Membership:
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO memberships
                        (id, user_id, org_id, role, created_at, removed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        membership.id,
                        membership.user_id,
                        membership.org_id,
                        membership.role.value,
                        membership.created_at or _now_iso(),
                        membership.removed_at,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                msg = f"user {membership.user_id!r} already has a membership in org {membership.org_id!r}"
                raise IdentityStoreError(msg) from e
        return membership

    def get_membership(self, membership_id: str) -> Membership | None:
        if not membership_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memberships WHERE id = ?",
                (membership_id,),
            ).fetchone()
        return _row_to_membership(row) if row else None

    def list_org_memberships(self, org_id: str, include_removed: bool = False) -> list[Membership]:
        if not org_id:
            return []
        sql = "SELECT * FROM memberships WHERE org_id = ?"
        params: tuple[Any, ...] = (org_id,)
        if not include_removed:
            sql += " AND removed_at IS NULL"
        sql += " ORDER BY created_at ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_membership(r) for r in rows]

    def list_user_memberships(self, user_id: str, include_removed: bool = False) -> list[Membership]:
        if not user_id:
            return []
        sql = "SELECT * FROM memberships WHERE user_id = ?"
        params: tuple[Any, ...] = (user_id,)
        if not include_removed:
            sql += " AND removed_at IS NULL"
        sql += " ORDER BY created_at ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_membership(r) for r in rows]

    def remove_membership(self, membership_id: str) -> Membership | None:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE memberships SET removed_at = ? WHERE id = ? AND removed_at IS NULL",
                (now, membership_id),
            )
            conn.commit()
        return self.get_membership(membership_id)

    def is_org_member(self, user_id: str, org_id: str) -> bool:
        if not user_id or not org_id:
            return False
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM memberships WHERE user_id = ? AND org_id = ? AND removed_at IS NULL LIMIT 1",
                (user_id, org_id),
            ).fetchone()
        return row is not None

    # ── Projects ──────────────────────────────────────────────────────

    def create_project(self, project: Project) -> Project:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects
                    (id, org_id, name, created_by_user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.org_id,
                    project.name,
                    project.created_by_user_id,
                    project.created_at or _now_iso(),
                ),
            )
            conn.commit()
        return project

    def get_project(self, project_id: str) -> Project | None:
        if not project_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _row_to_project(row) if row else None

    def delete_project(self, project_id: str) -> bool:
        if not project_id:
            return False
        with self._lock, self._connect() as conn:
            # Cascade: drop api keys for this project, then the project row.
            conn.execute("DELETE FROM api_keys WHERE project_id = ?", (project_id,))
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_org_projects(self, org_id: str) -> list[Project]:
        if not org_id:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE org_id = ? ORDER BY created_at ASC",
                (org_id,),
            ).fetchall()
        return [_row_to_project(r) for r in rows]

    # ── API keys ──────────────────────────────────────────────────────

    def create_api_key(self, api_key: ApiKey) -> ApiKey:
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO api_keys
                        (id, project_id, user_id, name, key_hash, key_prefix,
                         scope, created_at, last_used_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        api_key.id,
                        api_key.project_id,
                        api_key.user_id,
                        api_key.name,
                        api_key.key_hash,
                        api_key.key_prefix or "",
                        api_key.scope.value,
                        api_key.created_at or _now_iso(),
                        api_key.last_used_at,
                        api_key.revoked_at,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                msg = "api key with that hash already exists"
                raise IdentityStoreError(msg) from e
        return api_key

    def get_api_key(self, api_key_id: str) -> ApiKey | None:
        if not api_key_id:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE id = ?",
                (api_key_id,),
            ).fetchone()
        return _row_to_api_key(row) if row else None

    def lookup_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        if not key_hash:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?",
                (key_hash,),
            ).fetchone()
        return _row_to_api_key(row) if row else None

    def list_project_api_keys(self, project_id: str, include_revoked: bool = False) -> list[ApiKey]:
        if not project_id:
            return []
        sql = "SELECT * FROM api_keys WHERE project_id = ?"
        params: tuple[Any, ...] = (project_id,)
        if not include_revoked:
            sql += " AND revoked_at IS NULL"
        sql += " ORDER BY created_at DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_api_key(r) for r in rows]

    def revoke_api_key(self, api_key_id: str) -> ApiKey | None:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, api_key_id),
            )
            conn.commit()
        return self.get_api_key(api_key_id)

    def touch_api_key_last_used(self, api_key_id: str) -> None:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (now, api_key_id),
            )
            conn.commit()

    def health_check(self) -> dict[str, Any]:
        try:
            with self._lock, self._connect() as conn:
                users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
                orgs = conn.execute("SELECT COUNT(*) AS n FROM organizations").fetchone()["n"]
                keys = conn.execute(
                    "SELECT COUNT(*) AS n FROM api_keys WHERE revoked_at IS NULL",
                ).fetchone()["n"]
            return {
                "ok": True,
                "backend": "sqlite",
                "user_count": int(users),
                "org_count": int(orgs),
                "active_api_key_count": int(keys),
            }
        except _DB_ERRORS as e:
            return {"ok": False, "backend": "sqlite", "error": str(e)}

    def set_selected(self, user_id: str, org_id: str, project_id: str) -> SelectedContext:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_selections (user_id, org_id, project_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    org_id = excluded.org_id,
                    project_id = excluded.project_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, org_id, project_id, now),
            )
            conn.commit()
        return SelectedContext(user_id=user_id, org_id=org_id, project_id=project_id, updated_at=now)

    def get_selected(self, user_id: str) -> SelectedContext | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_selections WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return SelectedContext(
            user_id=row["user_id"],
            org_id=row["org_id"],
            project_id=row["project_id"],
            updated_at=row["updated_at"] or _now_iso(),
        )

    # ── Email Verification ──────────────────────────────────────────

    def create_email_verification_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = _now_iso()
        expires = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO email_verification_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now, expires),
            )
            conn.commit()
        return token

    def verify_email_token(self, token: str) -> User | None:
        if not token:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_verification_tokens WHERE token = ? AND consumed_at IS NULL AND expires_at > ?",
                (token, _now_iso()),
            ).fetchone()
            if not row:
                return None
            user_id = row["user_id"]
            conn.execute(
                "UPDATE email_verification_tokens SET consumed_at = ? WHERE token = ?",
                (_now_iso(), token),
            )
            conn.execute(
                "UPDATE users SET email_verified_at = ? WHERE id = ? AND email_verified_at IS NULL",
                (_now_iso(), user_id),
            )
            conn.commit()
        return self.get_user(user_id)

    def get_email_verification_by_token(self, token: str) -> dict | None:
        if not token:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_verification_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    # ── Password Reset ──────────────────────────────────────────────

    def create_password_reset_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = _now_iso()
        expires = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now, expires),
            )
            conn.commit()
        return token

    def consume_password_reset_token(self, token: str, new_password_hash: str) -> bool:
        if not token:
            return False
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token = ? AND consumed_at IS NULL AND expires_at > ?",
                (token, _now_iso()),
            ).fetchone()
            if not row:
                return False
            user_id = row["user_id"]
            conn.execute(
                "UPDATE password_reset_tokens SET consumed_at = ? WHERE token = ?",
                (_now_iso(), token),
            )
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_password_hash, user_id),
            )
            conn.commit()
        return True

    def get_password_reset_by_token(self, token: str) -> dict | None:
        if not token:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    # ── Team Invitations ────────────────────────────────────────────

    def create_team_invitation(self, org_id: str, invited_email: str, invited_by_user_id: str, role: str) -> dict:
        invite_id = str(uuid.uuid4())
        now = _now_iso()
        expires = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        clean_email = invited_email.strip().lower()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO team_invitations
                    (id, org_id, invited_email, invited_by_user_id, role, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (invite_id, org_id, clean_email, invited_by_user_id, role, now, expires),
            )
            conn.commit()
        return {
            "id": invite_id,
            "org_id": org_id,
            "invited_email": clean_email,
            "invited_by_user_id": invited_by_user_id,
            "role": role,
            "status": "pending",
            "created_at": now,
            "expires_at": expires,
        }

    def list_org_invitations(self, org_id: str, status: str | None = None) -> list[dict]:
        if not org_id:
            return []
        sql = "SELECT * FROM team_invitations WHERE org_id = ?"
        params: list[object] = [org_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def respond_to_invitation(self, invitation_id: str, accept: bool) -> dict | None:
        if not invitation_id:
            return None
        now = _now_iso()
        new_status = "accepted" if accept else "declined"
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM team_invitations WHERE id = ? AND status = 'pending' AND expires_at > ?",
                (invitation_id, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE team_invitations SET status = ?, responded_at = ? WHERE id = ?",
                (new_status, now, invitation_id),
            )

            # If accepted and user exists, auto-create membership
            if accept:
                invited_email = row["invited_email"]
                role = row["role"]
                user_row = conn.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?)",
                    (invited_email,),
                ).fetchone()
                if user_row:
                    # Check if already a member
                    existing = conn.execute(
                        "SELECT 1 FROM memberships WHERE user_id = ? AND org_id = ? AND removed_at IS NULL",
                        (user_row["id"], row["org_id"]),
                    ).fetchone()
                    if not existing:
                        membership_id = str(uuid.uuid4())
                        conn.execute(
                            "INSERT INTO memberships (id, user_id, org_id, role, created_at) VALUES (?, ?, ?, ?, ?)",
                            (membership_id, user_row["id"], row["org_id"], role, now),
                        )
            conn.commit()
        return {
            "id": invitation_id,
            "org_id": row["org_id"],
            "invited_email": row["invited_email"],
            "status": new_status,
            "responded_at": now,
        }

    def get_pending_invitation_by_email(self, email: str) -> dict | None:
        if not email:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM team_invitations WHERE LOWER(invited_email) = LOWER(?) AND status = 'pending' AND expires_at > ?",
                (email.strip(), _now_iso()),
            ).fetchone()
        return dict(row) if row else None

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM user_selections")
            conn.execute("DELETE FROM api_keys")
            conn.execute("DELETE FROM memberships")
            conn.execute("DELETE FROM team_invitations")
            conn.execute("DELETE FROM password_reset_tokens")
            conn.execute("DELETE FROM email_verification_tokens")
            conn.execute("DELETE FROM projects")
            conn.execute("DELETE FROM organizations")
            conn.execute("DELETE FROM users")
            conn.commit()


# ───────────────────────────────────────────────────────────────────────
# Module-level singleton
# ───────────────────────────────────────────────────────────────────────


_identity_store: IdentityStore | None = None
_identity_store_lock = threading.Lock()


def get_identity_store() -> IdentityStore:
    """Return the module-level identity store singleton.

    Tests can replace the singleton via ``reset_identity_store``; production
    callers should treat the return value as the canonical store for the
    process lifetime.
    """
    global _identity_store
    if _identity_store is not None:
        return _identity_store
    with _identity_store_lock:
        if _identity_store is None:
            _identity_store = SQLiteIdentityStore()
    return _identity_store


def reset_identity_store(store: IdentityStore | None = None) -> None:
    """Reset the module-level identity store singleton (for tests)."""
    global _identity_store
    _identity_store = store


# Re-exported for test introspection.
__all__ = [
    "IdentityStore",
    "IdentityStoreError",
    "SQLiteIdentityStore",
    "get_identity_store",
    "reset_identity_store",
]
