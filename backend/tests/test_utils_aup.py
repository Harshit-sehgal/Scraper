"""Unit tests for ``app.utils.aup`` - AUP enforcement dependency."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.utils.aup import require_aup_accepted
from app.utils.rbac import UserRole
from fastapi import HTTPException


def _make_request() -> MagicMock:
    return MagicMock()


def _make_context(
    role: UserRole = UserRole.USER,
    user_id: str = "user-123",
    org_id: str | None = "org-1",
    source: str = "session",
) -> MagicMock:
    ctx = MagicMock()
    ctx.role = role
    ctx.user_id = user_id
    ctx.org_id = org_id
    ctx.source = source
    return ctx


class TestRequireAupAccepted:
    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    async def test_skipped_when_auth_not_resolved(self, mock_resolve) -> None:
        mock_resolve.side_effect = HTTPException(status_code=401, detail="Not authenticated")
        request = _make_request()
        result = await require_aup_accepted(request)
        assert result == {"skipped": True}

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    async def test_returns_401_when_no_user_id(self, mock_resolve) -> None:
        mock_resolve.return_value = _make_context(user_id="")
        request = _make_request()
        with pytest.raises(HTTPException) as exc:
            await require_aup_accepted(request)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    @patch("app.utils.aup.get_identity_store")
    async def test_skipped_for_shadow_user(self, mock_store, mock_resolve) -> None:
        mock_resolve.return_value = _make_context()
        mock_store.return_value.get_user.return_value = None
        request = _make_request()
        result = await require_aup_accepted(request)
        assert result["skipped"] is True
        assert result["user_id"] == "user-123"

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    @patch("app.utils.aup.get_identity_store")
    async def test_raises_403_when_aup_not_accepted(self, mock_store, mock_resolve) -> None:
        mock_resolve.return_value = _make_context()
        user = MagicMock()
        user.aup_accepted_at = None
        user.aup_version_accepted = None
        mock_store.return_value.get_user.return_value = user
        request = _make_request()
        with pytest.raises(HTTPException) as exc:
            await require_aup_accepted(request)
        assert exc.value.status_code == 403
        assert "Acceptable Use Policy" in exc.value.detail

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    @patch("app.utils.aup.get_identity_store")
    async def test_raises_403_when_version_mismatch(self, mock_store, mock_resolve) -> None:
        mock_resolve.return_value = _make_context()
        user = MagicMock()
        user.aup_accepted_at = "2025-01-01"
        user.aup_version_accepted = "v1"
        mock_store.return_value.get_user.return_value = user
        request = _make_request()
        with patch("app.utils.aup.CURRENT_AUP_VERSION", "v2"):
            with pytest.raises(HTTPException) as exc:
                await require_aup_accepted(request)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    @patch("app.utils.aup.get_identity_store")
    async def test_returns_accepted_when_up_to_date(self, mock_store, mock_resolve) -> None:
        mock_resolve.return_value = _make_context()
        user = MagicMock()
        user.aup_accepted_at = "2025-01-01"
        user.aup_version_accepted = "v2"
        mock_store.return_value.get_user.return_value = user
        request = _make_request()
        with patch("app.utils.aup.CURRENT_AUP_VERSION", "v2"):
            result = await require_aup_accepted(request)
            assert result["accepted"] is True
            assert result["user_id"] == "user-123"

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    async def test_env_admin_bypasses_when_cross_tenant_enabled(self, mock_resolve) -> None:
        ctx = _make_context(role=UserRole.ADMIN, user_id="admin-1", org_id=None, source="api_key")
        mock_resolve.return_value = ctx
        request = _make_request()
        with patch("app.config.settings") as mock_settings:
            mock_settings.ENABLE_OPERATOR_CROSS_TENANT = True
            result = await require_aup_accepted(request)
            assert result["skipped"] is True

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    @patch("app.utils.aup.get_identity_store")
    async def test_env_admin_does_not_bypass_when_cross_tenant_disabled(self, mock_store, mock_resolve) -> None:
        ctx = _make_context(role=UserRole.ADMIN, user_id="admin-1", org_id=None, source="api_key")
        mock_resolve.return_value = ctx
        request = _make_request()
        mock_store.return_value.get_user.return_value = MagicMock()
        mock_store.return_value.get_user.return_value.aup_accepted_at = None
        mock_store.return_value.get_user.return_value.aup_version_accepted = None
        with patch("app.config.settings") as mock_settings:
            mock_settings.ENABLE_OPERATOR_CROSS_TENANT = False
            with pytest.raises(HTTPException) as exc:
                await require_aup_accepted(request)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("app.utils.aup.resolve_auth_context")
    @patch("app.utils.aup.get_identity_store")
    async def test_session_admin_never_bypasses(self, mock_store, mock_resolve) -> None:
        ctx = _make_context(role=UserRole.ADMIN, user_id="admin-1", org_id="org-1", source="session")
        mock_resolve.return_value = ctx
        request = _make_request()
        user = MagicMock()
        user.aup_accepted_at = None
        user.aup_version_accepted = None
        mock_store.return_value.get_user.return_value = user
        with pytest.raises(HTTPException) as exc:
            await require_aup_accepted(request)
        assert exc.value.status_code == 403
