"""Direct tests for rbac.can_access_scoped_resource + the router helpers
that delegate to it (auth_profiles._can_access_profile,
scheduled_monitoring._can_access_scheduled_job).

can_access_scoped_resource is the P0-SAAS-001 tenant-isolation primitive.
It had ZERO direct test coverage — every router that enforces data
isolation (auth-profiles, scheduled-monitoring, and the template/preview
endpoints) calls it via thin wrappers, so a bug here silently leaks
tenants' data to one another.

These tests cover every branch:

  - ADMIN returns True unconditionally (global superuser)
  - env-backed OPERATOR (empty org/project) with ENABLE_OPERATOR_CROSS_TENANT
    enabled → True and emits the CRITICAL cross-tenant audit
  - env-backed OPERATOR with the flag DISABLED → falls through to stricter
    owner/scoped checks (NOT blanket access) — issue #135 isolation
  - project-scoped principal+resource → match required, else False
  - org-scoped principal+resource → match required (project fallback)
  - pure owner fallback → owner match required; empty owner blocks all
  - mismatch on project_id → False (even if org matches)
  - mismatch on org_id → False (even if owner matches)
  - the router-helper wrappers delegate correctly (don't twist args)
  - _safe_profile strips encrypted_storage_state and ONLY that field
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from app.utils.rbac import UserRole, can_access_scoped_resource

# ── ADMIN ────────────────────────────────────────────────────────────


class TestCanAccessScopedResourceAdmin:
    """ADMIN bypasses every scope check — the global superuser."""

    def test_admin_access_ownerless_resource(self) -> None:
        assert can_access_scoped_resource(
            UserRole.ADMIN,
            "admin-1",
            "",
            "",
            resource_owner_id="",
            resource_org_id="",
            resource_project_id="",
        )

    def test_admin_access_other_tenant_owner(self) -> None:
        # Even a resource owned by an entirely different user/org/project.
        assert can_access_scoped_resource(
            UserRole.ADMIN,
            "admin-1",
            "org-a",
            "proj-a",
            resource_owner_id="user-X",
            resource_org_id="org-Z",
            resource_project_id="proj-Q",
        )

    def test_admin_access_does_not_emit_cross_tenant_audit(self) -> None:
        """ADMIN access MUST NOT fire the cross-tenant audit — it's normal."""
        with patch("app.utils.rbac._record_operator_cross_tenant") as spied:
            r = can_access_scoped_resource(
                UserRole.ADMIN,
                "admin-1",
                "",
                "",
                resource_owner_id="other-user",
            )
        assert r is True
        spied.assert_not_called()


# ── env-backed OPERATOR cross-tenant gate (issue #135) ───────────────


class TestEnvBackedOperatorGate:
    """The blanket-operator-all-access path is gated behind the
    ENABLE_OPERATOR_CROSS_TENANT flag — isolation MUST hold by default."""

    def test_operator_cross_tenant_enabled_returns_true_and_audits(self) -> None:
        with patch("app.config.settings.ENABLE_OPERATOR_CROSS_TENANT", True):
            from app.config import settings

            with patch.object(settings, "ENABLE_OPERATOR_CROSS_TENANT", True):
                with patch("app.utils.rbac._record_operator_cross_tenant") as spied:
                    r = can_access_scoped_resource(
                        UserRole.OPERATOR,
                        "op-1",
                        "",
                        "",
                        resource_owner_id="other-user",
                        resource_org_id="",
                        resource_project_id="",
                    )
        assert r is True
        # The CRITICAL audit MUST be emitted whenever blanket access is granted.
        spied.assert_called_once()

    def test_operator_cross_tenant_disabled_falls_through_to_owner(self) -> None:
        """When the flag is OFF, env-backed operator does NOT bypass
        tenant isolation — checks fall through to owner/scoped match."""
        from app.config import settings

        with patch.object(settings, "ENABLE_OPERATOR_CROSS_TENANT", False):
            with patch("app.utils.rbac._record_operator_cross_tenant") as spied:
                # owner doesn't match → no access.
                r = can_access_scoped_resource(
                    UserRole.OPERATOR,
                    "op-1",
                    "",
                    "",
                    resource_owner_id="other-user",
                )
        assert r is False
        # No audit when access was DENIED.
        spied.assert_not_called()

    def test_operator_cross_tenant_disabled_but_owner_matches(self) -> None:
        from app.config import settings

        with patch.object(settings, "ENABLE_OPERATOR_CROSS_TENANT", False):
            r = can_access_scoped_resource(
                UserRole.OPERATOR,
                "op-1",
                "",
                "",
                resource_owner_id="op-1",
            )
        assert r is True

    def test_operator_with_org_id_is_persistent_key_not_env_backed(self) -> None:
        """A persistent SaaS OPERATOR key carries org_id — that path is the
        scoped-resource check, NOT the env-backed gate.  Even when the
        cross-tenant flag is True, an operator with an org_id should keep
        using the org-scoped check (mismatch → no access)."""
        from app.config import settings

        with patch.object(settings, "ENABLE_OPERATOR_CROSS_TENANT", True):
            with patch("app.utils.rbac._record_operator_cross_tenant") as spied:
                r = can_access_scoped_resource(
                    UserRole.OPERATOR,
                    "op-1",
                    "org-mine",
                    "",
                    resource_owner_id="op-1",
                    resource_org_id="org-other",
                )
        assert r is False
        # Persistent keys do NOT fire the cross-tenant audit.
        spied.assert_not_called()


# ── project-scoped path ───────────────────────────────────────────────


class TestProjectScoped:
    """Two non-empty project_ids → must match (project_id == resource_project)."""

    def test_project_match_grants_access(self) -> None:
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-x",
            "proj-1",
            resource_owner_id="u2",
            resource_project_id="proj-1",
        )
        assert r is True

    def test_project_mismatch_denies_even_if_owner_matches(self) -> None:
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-x",
            "proj-mine",
            resource_owner_id="u1",
            resource_project_id="proj-theirs",
        )
        assert r is False

    def test_principal_project_set_resource_project_empty_falls_through(self) -> None:
        """When the resource has no project set, project-scope can't
        grant — falls through to org/owner."""
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-mine",
            "proj-mine",
            resource_owner_id="u1",
            resource_project_id="",
        )
        # Resource has no project → not "both projects set" → falls to owner.
        assert r is True  # owner matches


# ── org-scoped path ───────────────────────────────────────────────────


class TestOrgScoped:
    """When projects aren't both set, two non-empty org_ids must match."""

    def test_org_match_grants_access(self) -> None:
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-shared",
            "",
            resource_owner_id="other",
            resource_org_id="org-shared",
        )
        assert r is True

    def test_org_mismatch_denies(self) -> None:
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-mine",
            "",
            resource_owner_id="u1",
            resource_org_id="org-theirs",
        )
        assert r is False


# ── owner fallback (last branch) ──────────────────────────────────────


class TestOwnerFallback:
    """When neither project nor org scopes apply → owner_id == user_id."""

    def test_owner_match_grants_access(self) -> None:
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "",
            "",
            resource_owner_id="u1",
        )
        assert r is True

    def test_owner_mismatch_denies(self) -> None:
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "",
            "",
            resource_owner_id="someone-else",
        )
        assert r is False

    def test_empty_resource_owner_denies_everyone(self) -> None:
        """A resource with no recorded owner is inaccessible via the
        owner fallback — critical data-isolation assurance."""
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "",
            "",
            resource_owner_id="",
        )
        assert r is False

    def test_none_resource_owner_denies(self) -> None:
        """``None`` coalesces to empty string and denies."""
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "",
            "",
            resource_owner_id=None,
        )
        assert r is False


# ── Precedence (project before org before owner) ──────────────────────


class TestScopePrecedence:
    """Project scope wins over org scope; org scope wins over owner."""

    def test_project_match_even_when_org_mismatches(self) -> None:
        """If project goes orgranoff, project still wins — even with
        differing org, project_id == resource_project grants."""
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-A",
            "proj-shared",
            resource_owner_id="other",
            resource_org_id="org-B",
            resource_project_id="proj-shared",
        )
        assert r is True

    def test_org_match_even_when_owner_mismatches(self) -> None:
        """If projects aren't both set, org match wins — even with
        a differing owner."""
        r = can_access_scoped_resource(
            UserRole.USER,
            "u1",
            "org-shared",
            "",
            resource_owner_id="other",
            resource_org_id="org-shared",
        )
        assert r is True


# ── Router helpers delegate correctly ────────────────────────────────


@pytest.fixture
def _four_tuple():
    """A canonical (role, user_id, org_id, project_id) auth tuple as the
    routers receive from require_principal."""
    return (UserRole.USER, "u1", "org-1", "proj-1")


class TestRouterHelpersDelegate:
    """The router-level wrappers (_can_access_profile,
    _can_access_scheduled_job) MUST pass the four auth tuple components
    and the resource's owner/org/project straight into
    can_access_scoped_resource without twisting argument order."""

    def test_auth_profiles_helper_delegates(self, _four_tuple: tuple) -> None:
        from app.routers.auth_profiles import _can_access_profile

        # Project match → granted, even though owner differs from principal.
        item: dict[str, Any] = {
            "user_id": "u1",
            "org_id": "org-1",
            "project_id": "proj-1",
        }
        assert _can_access_profile(item, _four_tuple) is True
        # Project mismatch → denied (project_id == resource_project fails).
        item["project_id"] = "proj-other"
        assert _can_access_profile(item, _four_tuple) is False

    def test_scheduled_monitoring_helper_delegates(self, _four_tuple: tuple) -> None:
        from app.routers.scheduled_monitoring import _can_access_scheduled_job

        # Project scope grants.
        item: dict[str, Any] = {
            "user_id": "u1",
            "org_id": "org-1",
            "project_id": "proj-1",
        }
        assert _can_access_scheduled_job(item, _four_tuple) is True
        # Project mismatch → denied.
        item["project_id"] = "proj-other"
        assert _can_access_scheduled_job(item, _four_tuple) is False

    def test_helpers_coerce_missing_keys_to_empty(self, _four_tuple: tuple) -> None:
        """A resource dict missing one of the scope keys MUST not crash —
        ``item.get("user_id") or ""`` coalesces None/absent to empty str.
        No scope keys at all → owner fallback with no owner → denied.
        (Principal has proj-1 / org-1 set, but resource has None for both
        — only owner fallback applies, and there's no owner to match.)"""
        from app.routers.auth_profiles import _can_access_profile
        from app.routers.scheduled_monitoring import _can_access_scheduled_job

        orphan = {"id": "x"}
        assert _can_access_profile(orphan, _four_tuple) is False
        assert _can_access_scheduled_job(orphan, _four_tuple) is False


class TestSafeProfileStrip:
    """_safe_profile strips encrypted_storage_state and ONLY that field."""

    def test_strips_encrypted_state_and_keeps_rest(self) -> None:
        from app.routers.auth_profiles import _safe_profile

        item = {
            "id": "abc",
            "name": "Login X",
            "domain": "example.com",
            "status": "active",
            "encrypted_storage_state": "REDACTED-SECRET",
            "user_id": "u1",
        }
        safe = _safe_profile(item)
        assert "encrypted_storage_state" not in safe
        assert safe["id"] == "abc"
        assert safe["user_id"] == "u1"
        assert safe["domain"] == "example.com"

    def test_does_not_mutate_original(self) -> None:
        from app.routers.auth_profiles import _safe_profile

        item = {"id": "abc", "encrypted_storage_state": "SECRET"}
        _safe_profile(item)
        # Real caller dict untouched (defensive — passes-by-reference et al.).
        assert "encrypted_storage_state" in item

    def test_dict_without_encrypted_field_passes_through(self) -> None:
        from app.routers.auth_profiles import _safe_profile

        item = {"id": "abc", "name": "n"}
        assert _safe_profile(item) == item
