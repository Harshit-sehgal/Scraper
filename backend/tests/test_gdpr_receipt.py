"""Tests for the GDPR deletion receipt (Roadmap Comp #8).

The full delete pipeline depends on many stores (jobs, workflows,
scheduled jobs, auth profiles, SaaS identity) that are complex to
fixture end-to-end.  These tests focus narrowly on the *receipt
shape* and the *alias delegation*, while the existing
``test_user_data.py`` suite covers the full delete flow.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


def _run_delete_my_data(auth):
    """Run delete_my_data with all external dependencies stubbed to safe defaults."""
    from app.workflow_repository import JsonWorkflowRepository

    # Stub the JsonWorkflowRepository class check by returning a fake repo
    # that IS an instance of it (or supplying store with the right shape).
    fake_repo = MagicMock()

    with (
        patch("app.globals.jobs_store", {}),
        patch("app.globals._jobs_store_lock", MagicMock()),
        patch(
            "app.routers.workflow._get_workflow_repo",
            return_value=fake_repo,
        ),
        patch.object(JsonWorkflowRepository, "__instancecheck__", lambda self, instance: True),
        # Patch the repo to be an instance check
        patch("app.routers.auth_profiles._auth_profiles") as mock_ap,
        patch("app.routers.scheduled_monitoring._scheduled_jobs") as mock_sj,
    ):
        mock_ap.delete_many = MagicMock(side_effect=len)
        mock_sj.delete_many = MagicMock(side_effect=len)

        from app.routers.user_data import delete_my_data

        return asyncio.run(delete_my_data(auth))


class TestGdprReceipt:
    def test_receipt_keys_present(self) -> None:
        """Verify the response shape returned by delete_my_data."""
        mock_auth = ("user-role", "test-user-id", "org-1", "proj-1")
        response = _run_delete_my_data(mock_auth)
        assert response["status"] == "ok"
        assert response["user_id"] == "test-user-id"
        assert "summary" in response
        assert "receipt" in response
        receipt = response["receipt"]
        assert "id" in receipt
        assert "timestamp" in receipt
        assert "token" in receipt


class TestGdprForgetAlias:
    def test_alias_delegates_to_delete(self) -> None:
        """Verify /api/compliance/gdpr/forget delegates to delete_my_data."""
        from app.routers.user_data import gdpr_forget

        mock_auth = ("user-role", "test-user-id", "org-1", "proj-1")
        expected = {"status": "ok", "alias": True, "user_id": "test-user-id"}

        with patch("app.routers.user_data.delete_my_data", return_value=expected) as mock_del:
            response = asyncio.run(gdpr_forget(mock_auth))
            assert response["status"] == "ok"
            mock_del.assert_called_once_with(mock_auth)


class TestReceiptTokenShape:
    def test_token_is_sha256_hex_prefix(self) -> None:
        """Verify the receipt token is a 16-character hex prefix."""
        mock_auth = ("user-role", "test-user-id", "org-1", "proj-1")
        response = _run_delete_my_data(mock_auth)
        token = response["receipt"]["token"]
        assert isinstance(token, str)
        assert len(token) == 16
        assert all(c in "0123456789abcdef" for c in token)
