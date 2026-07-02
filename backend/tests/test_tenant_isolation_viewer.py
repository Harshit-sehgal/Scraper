"""Tenant-isolation regression tests for the VIEWER membership role.

A VIEWER is the lowest-privilege membership: ``_MAX_KEY_SCOPE_FOR_ROLE``
restricts them to ``ApiKeyScope.READ``, which resolves to ``UserRole.USER``
in ``app.utils.rbac``. This module proves a VIEWER-scope key cannot reach
any admin-only or operator-only surface — neither by direct HTTP calls,
nor by trying to escalate to a higher key scope, nor by accessing another
org's data via a read endpoint.

If anyone moves a route to require a higher role without keeping the
read-only barrier intact, these tests fail.
"""

from __future__ import annotations

import pytest
from app.config import settings
from app.models import Job, JobStatus, ScrapeMode
from app.saas import CURRENT_AUP_VERSION
from app.saas.identity_store import get_identity_store
from app.saas.models import ApiKeyScope, MembershipRole

# ─── helpers ──────────────────────────────────────────────────────────────


def _configure_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable dev-auth bypass so the API key gate is real."""
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "ENV", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)


def _setup_two_orgs(tmp_path):
    """Seed two distinct orgs/projects each with one signed-up owner.

    Returns ``(reset_fn, org_a, org_b, keys_service)``.
    Does NOT issue any keys — callers control their own key scopes.
    """
    from app.saas import ApiKeyService, SignupService, reset_identity_store
    from app.saas.identity_store import SQLiteIdentityStore, get_identity_store

    reset_identity_store(SQLiteIdentityStore(storage_path=tmp_path / "identity.db"))
    store = get_identity_store()
    signup = SignupService()
    keys = ApiKeyService()
    org_a = signup.signup("viewer-a@example.com", "hunter2", org_name="OrgA", project_name="ProjA")
    org_b = signup.signup("viewer-b@example.com", "hunter2", org_name="OrgB", project_name="ProjB")
    # Accept AUP so route-level AUP checks do not 403 before RBAC runs
    from app.saas import CURRENT_AUP_VERSION as _AUP_VER

    store.mark_aup_accepted(org_a.user.id, aup_version=_AUP_VER)
    store.mark_aup_accepted(org_b.user.id, aup_version=_AUP_VER)
    return reset_identity_store, org_a, org_b, keys


def _make_viewer_user(org_a, email: str) -> str:
    """Create a user inside the identity store and assign VIEWER role.

    Returns the new user id. Uses the identity store directly so we do
    not need to spin up second ``signup()`` flows (those create OWNER
    memberships; we want to exercise the VIEWER ceiling).
    """
    import uuid as _uuid

    from app.saas import Membership, User, UserStatus
    from app.saas.identity_store import get_identity_store

    store = get_identity_store()
    viewer_user_id = str(_uuid.uuid4())
    store.create_user(
        User(
            id=viewer_user_id,
            email=email,
            display_name="Viewer User",
            status=UserStatus.ACTIVE,
            password_hash="",
        )
    )
    membership = Membership(
        id=str(_uuid.uuid4()),
        user_id=viewer_user_id,
        org_id=org_a.organization.id,
        role=MembershipRole.VIEWER,
    )
    store.create_membership(membership)
    return viewer_user_id


# ─── Endpoint matrix ──────────────────────────────────────────────────────
# Every pair is (method, path). These routes require either UserRole.ADMIN
# or (UserRole.ADMIN, UserRole.OPERATOR) — both scopes are above what a
# VIEWER's READ-scope API key can present.

_ADMIN_ONLY = [
    ("delete", "/api/jobs/some-id"),  # RBAC gates delete before entity lookup
    ("delete", "/api/templates/some-id"),
    ("get", "/api/system/audit-log"),
    ("post", "/api/operator/denylist"),
    ("delete", "/api/operator/denylist"),
]

_OPERATOR_ONLY = [
    ("post", "/api/discover"),
    ("post", "/api/schema/suggest"),
    ("post", "/api/jobs"),
    ("post", "/api/jobs/batch"),
    ("post", "/api/jobs/some-id/cancel"),
    ("post", "/api/jobs/some-id/reclean"),
    ("post", "/api/jobs/some-id/clone"),
    ("post", "/api/templates"),
    ("get", "/api/templates"),
    ("get", "/api/workflows"),
    ("post", "/api/workflows"),
    ("get", "/api/usage/stats"),
]


# ═══════════════════════════════════════════════════════════════════════════
# VIEWER cannot reach admin-only or operator-only surfaces
# ═══════════════════════════════════════════════════════════════════════════


class TestViewerKeyCannotReachAdminOrOperatorRoutes:
    @pytest.fixture
    def viewer_key(self, tmp_path, monkeypatch):
        """Create OrgA owner + VIEWER user + READ-scope key."""
        from app.saas import ApiKeyService

        reset_identity_store, org_a, _org_b, _keys = _setup_two_orgs(tmp_path)
        viewer_user_id = _make_viewer_user(org_a, email="viewer-rbac@example.com")
        keys = ApiKeyService()
        issued = keys.issue(
            project_id=org_a.project.id,
            user_id=viewer_user_id,
            name="viewer-read-only",
            scope=ApiKeyScope.READ,
        )
        try:
            yield issued.raw_key
        finally:
            reset_identity_store(None)

    def _assert_denied(self, client, viewer_key, method, path):
        response = client.request(
            method,
            path,
            headers={"X-API-Key": viewer_key},
            json={} if method == "post" else None,
        )
        assert response.status_code in {401, 403}, (
            f"VIEWER key must be denied on {method.upper()} {path} — got {response.status_code} {response.text!r}"
        )

    def test_admin_only_endpoints_reject_viewer_key(self, client, monkeypatch, viewer_key):
        _configure_keys(monkeypatch)
        for method, path in _ADMIN_ONLY:
            self._assert_denied(client, viewer_key, method, path)

    def test_operator_only_endpoints_reject_viewer_key(self, client, monkeypatch, viewer_key):
        _configure_keys(monkeypatch)
        for method, path in _OPERATOR_ONLY:
            self._assert_denied(client, viewer_key, method, path)


# ═══════════════════════════════════════════════════════════════════════════
# VIEWER ceiling check via project key-creation route
# ═══════════════════════════════════════════════════════════════════════════


class TestViewerCannotIssueHigherScopedKeys:
    """Single-test class: the membership scope ceiling must refuse an
    admin-scope key even when the caller holds a stronger-scoped API key."""

    def test_viewer_with_write_key_cannot_issue_admin_scoped_key(self, client, tmp_path, monkeypatch):
        from app.saas import ApiKeyService

        reset_identity_store, org_a, _org_b, _keys = _setup_two_orgs(tmp_path)
        viewer_user_id = _make_viewer_user(org_a, email="viewer-ceiling@example.com")
        get_identity_store().mark_aup_accepted(viewer_user_id, aup_version=CURRENT_AUP_VERSION)
        keys = ApiKeyService()
        # Issue a WRITE-scope key for the VIEWER (the route gate requires
        # ADMIN/OPERATOR; a WRITE key resolves to OPERATOR). The VIEWER's
        # membership ceiling is "read" — the per-user level ceiling must
        # still refuse admin issurance even when the caller's key-scope
        # is stronger than READ.
        viewer_key = keys.issue(
            project_id=org_a.project.id,
            user_id=viewer_user_id,
            name="viewer-write",
            scope=ApiKeyScope.WRITE,
        ).raw_key
        try:
            _configure_keys(monkeypatch)
            # READ-scope within VIEWER ceiling — allowed
            resp_read = client.post(
                f"/api/saas/projects/{org_a.project.id}/keys",
                headers={"X-API-Key": viewer_key},
                json={"name": "self-read-1", "scope": "read"},
            )
            assert resp_read.status_code in {200, 201}, (
                f"VIEWER (max=read, holding WRITE key) must be able to issue "
                f"a read-scope key — got {resp_read.status_code} {resp_read.text!r}"
            )
            # Write-scope exceeds VIEWER ceiling — must be refused
            resp_write = client.post(
                f"/api/saas/projects/{org_a.project.id}/keys",
                headers={"X-API-Key": viewer_key},
                json={"name": "escalation-write", "scope": "write"},
            )
            assert resp_write.status_code in {400, 403}, (
                f"VIEWER (max=read) must not be able to issue a write-scope "
                f"key via WRITE-key holder session — got "
                f"{resp_write.status_code} {resp_write.text!r}"
            )
            # Admin-scope exceeds VIEWER ceiling — must be refused
            resp_admin = client.post(
                f"/api/saas/projects/{org_a.project.id}/keys",
                headers={"X-API-Key": viewer_key},
                json={"name": "escalation-admin", "scope": "admin"},
            )
            assert resp_admin.status_code in {400, 403}, (
                f"VIEWER (max=read) must not be able to issue an admin-scope "
                f"key via WRITE-key holder session — got "
                f"{resp_admin.status_code} {resp_admin.text!r}"
            )
        finally:
            reset_identity_store(None)


# ═══════════════════════════════════════════════════════════════════════════
# VIEWER cannot read another org's data even on routes they can reach
# ═══════════════════════════════════════════════════════════════════════════


class TestViewerCannotReachAnotherOrgsData:
    def test_viewer_listing_jobs_excludes_other_orgs(self, client, tmp_path, monkeypatch):
        """A VIEWER calling /api/jobs must not see other-org job records."""
        import app.main as main_mod
        from app.saas import ApiKeyService

        reset_identity_store, org_a, _org_b, _keys = _setup_two_orgs(tmp_path)
        viewer_user_id = _make_viewer_user(org_a, email="viewer-list@example.com")
        keys = ApiKeyService()
        viewer_key = keys.issue(
            project_id=org_a.project.id,
            user_id=viewer_user_id,
            name="viewer-list",
            scope=ApiKeyScope.READ,
        ).raw_key

        # Plant a foreign-org job in the global store with mismatched
        # org_id/project_id so the principal filter would have to hide it.
        foreign_job = Job(
            id="other-orgs-job",
            name="other-orgs-job",
            mode=ScrapeMode.MANUAL,
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
            created_by=org_a.user.id,
            org_id="some-other-org",
            project_id="some-other-project",
        )
        main_mod.jobs_store[foreign_job.id] = foreign_job

        try:
            _configure_keys(monkeypatch)
            resp = client.get("/api/jobs", headers={"X-API-Key": viewer_key})
            assert resp.status_code == 200, f"VIEWER should be able to list jobs — got {resp.status_code} {resp.text!r}"
            payload = resp.json()
            items = payload.get("items") or payload.get("jobs") or []
            ids = {item.get("id") for item in items}
            assert "other-orgs-job" not in ids, f"VIEWER must not see other-orgs jobs in /api/jobs listing — got ids={ids}"
        finally:
            reset_identity_store(None)
            main_mod.jobs_store.pop("other-orgs-job", None)

    def test_viewer_direct_fetch_of_foreign_job_is_blocked(self, client, tmp_path, monkeypatch):
        """A VIEWER fetching /api/jobs/{id} for a foreign-org job is denied."""
        import app.main as main_mod
        from app.saas import ApiKeyService

        reset_identity_store, org_a, org_b, _keys = _setup_two_orgs(tmp_path)
        viewer_user_id = _make_viewer_user(org_a, email="viewer-fetch@example.com")
        keys = ApiKeyService()
        viewer_key = keys.issue(
            project_id=org_a.project.id,
            user_id=viewer_user_id,
            name="viewer-fetch",
            scope=ApiKeyScope.READ,
        ).raw_key

        # Plant a job that legitimately belongs to OrgB
        foreign_job = Job(
            id="orgb-private-job",
            name="OrgB-private-job",
            mode=ScrapeMode.MANUAL,
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
            created_by=org_b.user.id,
            org_id=org_b.organization.id,
            project_id=org_b.project.id,
        )
        main_mod.jobs_store[foreign_job.id] = foreign_job

        try:
            _configure_keys(monkeypatch)
            resp = client.get(f"/api/jobs/{foreign_job.id}", headers={"X-API-Key": viewer_key})
            assert resp.status_code in {403, 404}, (
                f"VIEWER must not be able to fetch OrgB's job by id — got {resp.status_code} {resp.text!r}"
            )
        finally:
            reset_identity_store(None)
            main_mod.jobs_store.pop("orgb-private-job", None)
