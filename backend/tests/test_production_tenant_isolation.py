from __future__ import annotations

from app.utils.rbac import (
    UserRole,
    can_access_scoped_resource,
)


class TestTenantIsolation:
    def test_cross_tenant_access_denied_for_user(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.USER,
            "user_a",
            "org_a",
            "proj_a",
            resource_owner_id="user_b",
            resource_org_id="org_b",
            resource_project_id="proj_b",
        )
        assert allowed is False

    def test_admin_has_all_access(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.ADMIN,
            "admin1",
            "org_a",
            "proj_a",
            resource_owner_id="some_user",
            resource_org_id="org_b",
            resource_project_id="proj_b",
        )
        assert allowed is True

    def test_operator_with_project_scope_has_no_cross_tenant(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.OPERATOR,
            "op_scoped",
            "org_a",
            "proj_a",
            resource_owner_id="other_user",
            resource_org_id="org_b",
            resource_project_id="proj_b",
        )
        assert allowed is False

    def test_same_org_access_allowed(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.USER,
            "user_a",
            "org_shared",
            "",
            resource_owner_id="user_b",
            resource_org_id="org_shared",
            resource_project_id="",
        )
        assert allowed is True

    def test_same_project_access_allowed(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.USER,
            "user_a",
            "org_shared",
            "proj_x",
            resource_owner_id="user_b",
            resource_org_id="org_shared",
            resource_project_id="proj_x",
        )
        assert allowed is True

    def test_same_user_access_allowed(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.USER,
            "user_a",
            "",
            "",
            resource_owner_id="user_a",
            resource_org_id="",
            resource_project_id="",
        )
        assert allowed is True

    def test_cross_org_denied_even_with_same_user(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.USER,
            "user_a",
            "org_a",
            "",
            resource_owner_id="user_a",
            resource_org_id="org_b",
            resource_project_id="",
        )
        assert allowed is False

    def test_missing_owner_fails_for_user(self) -> None:
        allowed = can_access_scoped_resource(
            UserRole.USER,
            "user_a",
            "org_a",
            "",
            resource_owner_id=None,
            resource_org_id="org_b",
            resource_project_id="",
        )
        assert allowed is False
