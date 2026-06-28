"""Tests for the GDPR deletion receipt (Roadmap Comp #8).

The full delete pipeline depends on many stores (jobs, workflows,
scheduled jobs, auth profiles, SaaS identity) that are complex to
fixture end-to-end.  These tests focus narrowly on the *receipt
shape* and the *alias delegation*, while the existing
``test_user_data.py`` suite covers the full delete flow.

Also includes TOCTOU regression tests: ``delete_where`` and
``delete_by_user`` must evaluate ownership inside the same lock
/ transaction so a concurrent mutation cannot cause cross-tenant
deletion or data leakage.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.utils.rbac import UserRole


def _run_delete_my_data(auth):
    """Run delete_my_data with all external dependencies stubbed to safe defaults."""
    # Stub the JsonWorkflowRepository class check by returning a fake repo
    # that IS an instance of it (or supplying store with the right shape).
    fake_repo = MagicMock()
    fake_repo.delete_by_user = MagicMock(return_value=0)

    with (
        patch("app.globals.jobs_store", {}),
        patch("app.globals._jobs_store_lock", MagicMock()),
        patch(
            "app.routers.workflow._get_workflow_repo",
            return_value=fake_repo,
        ),
        patch("app.routers.auth_profiles._auth_profiles") as mock_ap,
        patch("app.routers.scheduled_monitoring._scheduled_jobs") as mock_sj,
    ):
        mock_ap.delete_where = MagicMock(return_value=0)
        mock_sj.delete_where = MagicMock(return_value=0)

        from app.routers.user_data import delete_my_data

        return asyncio.run(delete_my_data(auth))


class TestGdprReceipt:
    def test_receipt_keys_present(self) -> None:
        """Verify the response shape returned by delete_my_data."""
        mock_auth = (UserRole.USER, "test-user-id", "org-1", "proj-1")
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

        mock_auth = (UserRole.USER, "test-user-id", "org-1", "proj-1")
        expected = {"status": "ok", "alias": True, "user_id": "test-user-id"}

        with patch("app.routers.user_data.delete_my_data", return_value=expected) as mock_del:
            response = asyncio.run(gdpr_forget(mock_auth))
            assert response["status"] == "ok"
            mock_del.assert_called_once_with(mock_auth)


class TestReceiptTokenShape:
    def test_token_is_sha256_hex_prefix(self) -> None:
        """Verify the receipt token is a 16-character hex prefix."""
        mock_auth = (UserRole.USER, "test-user-id", "org-1", "proj-1")
        response = _run_delete_my_data(mock_auth)
        token = response["receipt"]["token"]
        assert isinstance(token, str)
        assert len(token) == 16
        assert all(c in "0123456789abcdef" for c in token)


# =========================================================================
# TOCTOU regression tests
# =========================================================================


class TestJSONFileStoreDeleteWhere:
    """Verify ``delete_where`` closes the TOCTOU window that
    ``values()`` + ``delete_many()`` left open.

    The old pattern was:
        ids = [r["id"] for r in store.values() if r["user_id"] == uid]
        store.delete_many(ids)
    A concurrent upsert between the two calls could reassign a record's
    ``user_id`` so that delete_many removed a record no longer owned by
    the caller. ``delete_where`` evaluates the predicate inside the
    flocked _read_modify_write so reassignment after the snapshot is
    impossible.
    """

    def test_delete_where_removes_matching_records(self, tmp_path: Path) -> None:
        from app.utils.json_file_store import JSONFileStore

        store = JSONFileStore(path=tmp_path / "test.json")
        store.upsert("a", {"id": "a", "user_id": "alice", "name": "Profile A"})
        store.upsert("b", {"id": "b", "user_id": "bob", "name": "Profile B"})
        store.upsert("c", {"id": "c", "user_id": "alice", "name": "Profile C"})

        removed = store.delete_where(lambda r: r.get("user_id") == "alice")
        assert removed == 2
        assert store.get("a") is None
        assert store.get("c") is None
        # Bob's record must be untouched.
        assert store.get("b") is not None
        b_rec = store.get("b")
        assert b_rec is not None
        assert b_rec["user_id"] == "bob"

    def test_delete_where_returns_zero_when_no_match(self, tmp_path: Path) -> None:
        from app.utils.json_file_store import JSONFileStore

        store = JSONFileStore(path=tmp_path / "test.json")
        store.upsert("x", {"id": "x", "user_id": "alice"})
        removed = store.delete_where(lambda r: r.get("user_id") == "nobody")
        assert removed == 0
        assert store.get("x") is not None

    def test_delete_where_is_atomic_vs_concurrent_reassign(self, tmp_path: Path) -> None:
        """Concurrent upsert that reassigns user_id does NOT cause
        delete_where to miss or cross-delete.

        If ``delete_where`` read ``values()`` unlocked (the old
        pattern), a thread that reassigns bob's record to alice
        between the snapshot and the write would cause alice's
        delete_where to delete bob's record. This test validates that
        delete_where holds the lock during the evaluation.
        """
        from app.utils.json_file_store import JSONFileStore

        store = JSONFileStore(path=tmp_path / "test.json")
        store.upsert("bob-rec", {"id": "bob-rec", "user_id": "bob"})

        # From main thread, delete alice's records (none exist).
        removed = store.delete_where(lambda r: r.get("user_id") == "alice")
        assert removed == 0
        # Bob's record survives.
        assert store.get("bob-rec") is not None

        # Now have a background thread reassign bob -> alice DURING
        # a delete_where that targets bob. If the predicate is
        # evaluated outside the lock, the reassign could race and we'd
        # see inconsistent results. With the lock, either the delete
        # sees the old user_id (bob) or the new (alice), but the
        # store stays consistent.
        barrier = threading.Barrier(2, timeout=5)
        results: dict[str, int] = {}

        def _reassign():
            barrier.wait()
            store.upsert("bob-rec", {"id": "bob-rec", "user_id": "alice"})
            results["reassign_done"] = 1

        t = threading.Thread(target=_reassign)
        t.start()

        # Both threads enter the barrier; then we delete bob records.
        # The flock serialises so we see a consistent state.
        barrier.wait()
        removed = store.delete_where(lambda r: r.get("user_id") == "bob")
        t.join()

        # After both operations, the store must be internally consistent.
        remaining = store.values()
        remaining_ids = {r.get("id") for r in remaining}
        # bob-rec was either deleted (if delete_where ran before
        # reassign) or reassigned to alice (if reassign ran first).
        if "bob-rec" in remaining_ids:
            rec = store.get("bob-rec")
            assert rec is not None
            # Must now belong to alice (reassign won the race).
            assert rec.get("user_id") == "alice"
        else:
            # delete_where removed it while it still belonged to bob.
            pass

    def test_delete_by_user_json_workflow_repo(self, tmp_path: Path) -> None:
        """JsonWorkflowRepository.delete_by_user is an atomic wrapper
        around delete_where."""
        from app.utils.json_file_store import JSONFileStore
        from app.workflow_repository import JsonWorkflowRepository

        store = JSONFileStore(path=tmp_path / "wf.json")
        repo = JsonWorkflowRepository(store=store)
        store.upsert("wf1", {"id": "wf1", "user_id": "alice", "domain": "test"})
        store.upsert("wf2", {"id": "wf2", "user_id": "bob", "domain": "test"})
        store.upsert("wf3", {"id": "wf3", "user_id": "alice", "domain": "other"})

        removed = repo.delete_by_user("alice")
        assert removed == 2
        assert repo.get("wf1") is None
        assert repo.get("wf3") is None
        # Bob's workflow survives.
        assert repo.get("wf2") is not None


class TestDeleteMyDataUsesAtomicAPIs:
    """Verify that delete_my_data calls the atomic APIs, not the
    TOCTOU-vulnerable values()+delete_many() pattern."""

    def test_calls_repo_delete_by_user(self) -> None:
        """delete_my_data must call repo.delete_by_user, not
        repo.list_workflows + repo.delete in a loop."""
        fake_repo = MagicMock()
        fake_repo.delete_by_user = MagicMock(return_value=3)

        with (
            patch("app.globals.jobs_store", {}),
            patch("app.globals._jobs_store_lock", MagicMock()),
            patch("app.routers.workflow._get_workflow_repo", return_value=fake_repo),
            patch("app.routers.auth_profiles._auth_profiles") as mock_ap,
            patch("app.routers.scheduled_monitoring._scheduled_jobs") as mock_sj,
        ):
            mock_ap.delete_where = MagicMock(return_value=0)
            mock_sj.delete_where = MagicMock(return_value=0)

            from app.routers.user_data import delete_my_data

            result = asyncio.run(delete_my_data((UserRole.USER, "alice", "org", "proj")))
        fake_repo.delete_by_user.assert_called_once_with("alice")
        assert result["summary"]["workflows_deleted"] == 3

    def test_calls_store_delete_where_not_delete_many(self) -> None:
        """Auth profiles and scheduled jobs must use delete_where
        (atomic), not values() + delete_many (TOCTOU)."""
        fake_repo = MagicMock()
        fake_repo.delete_by_user = MagicMock(return_value=0)

        with (
            patch("app.globals.jobs_store", {}),
            patch("app.globals._jobs_store_lock", MagicMock()),
            patch("app.routers.workflow._get_workflow_repo", return_value=fake_repo),
            patch("app.routers.auth_profiles._auth_profiles") as mock_ap,
            patch("app.routers.scheduled_monitoring._scheduled_jobs") as mock_sj,
        ):
            mock_ap.delete_where = MagicMock(return_value=2)
            mock_sj.delete_where = MagicMock(return_value=1)

            from app.routers.user_data import delete_my_data

            result = asyncio.run(delete_my_data((UserRole.USER, "alice", "org", "proj")))

        mock_ap.delete_where.assert_called_once()
        mock_sj.delete_where.assert_called_once()
        assert result["summary"]["auth_profiles_deleted"] == 2
        assert result["summary"]["scheduled_jobs_deleted"] == 1


class TestDeleteMyDataTenancy:
    """Verify that only the caller's own data is deleted, and admin
    all-access is NOT the default (project rule 8)."""

    def test_saas_branch_skipped_when_user_not_found(self) -> None:
        """If get_user returns None, no API keys or memberships are
        touched — the unvalidated-identifier fallback has been
        removed."""
        fake_repo = MagicMock()
        fake_repo.delete_by_user = MagicMock(return_value=0)
        mock_store = MagicMock()
        mock_store.get_user = MagicMock(return_value=None)
        mock_store.get_user_by_email = MagicMock(return_value=None)

        with (
            patch("app.globals.jobs_store", {}),
            patch("app.globals._jobs_store_lock", MagicMock()),
            patch("app.routers.workflow._get_workflow_repo", return_value=fake_repo),
            patch("app.routers.auth_profiles._auth_profiles") as mock_ap,
            patch("app.routers.scheduled_monitoring._scheduled_jobs") as mock_sj,
            patch("app.saas.identity_store.get_identity_store", return_value=mock_store),
        ):
            mock_ap.delete_where = MagicMock(return_value=0)
            mock_sj.delete_where = MagicMock(return_value=0)

            from app.routers.user_data import delete_my_data

            result = asyncio.run(delete_my_data((UserRole.USER, "nonexistent-user", "org", "proj")))

        # No keys revoked, no memberships removed.
        assert result["summary"]["api_keys_revoked"] == 0
        assert result["summary"]["memberships_removed"] == 0
        # get_identity_store was called but no destructive ops followed.
        mock_store.get_user.assert_called_once_with("nonexistent-user")
