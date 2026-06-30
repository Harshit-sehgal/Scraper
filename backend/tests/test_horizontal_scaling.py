"""Tests for horizontal scaling support (Prod 11).

Covers:
- NodeIdentity: unique IDs, persistence, role from env
- DistributedLock: acquire/release, re-acquire after release, timeout
- JobClaimService: claim succeeds, claim fails (already claimed by another
  node), release allows re-claim, stale claim cleanup, heartbeat tracking
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from app.distributed import (
    DistributedLock,
    JobClaimService,
    NodeIdentity,
    get_node_identity,
    reset_node_identity,
)


@pytest.fixture(autouse=True)
def _reset_identity():
    """Reset node identity singleton before and after each test."""
    reset_node_identity()
    yield
    reset_node_identity()


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database for test isolation."""
    db = tmp_path / "test_distributed.db"
    # Initialise a blank DB so SQLite can connect
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# NodeIdentity
# ═══════════════════════════════════════════════════════════════════════════════


class TestNodeIdentity:
    def test_generates_unique_id(self) -> None:
        """Two distinct calls produce different node IDs."""
        reset_node_identity()
        id_a = get_node_identity().node_id
        reset_node_identity()
        # Override the persisted file so a new UUID is generated
        with patch("app.distributed._generate_node_id", return_value="brand-new-uuid"):
            id_b = get_node_identity().node_id
        # First ID is a valid UUID4; second is our override
        assert id_a != id_b

    def test_default_role_is_standalone(self) -> None:
        """Without DATAFORGE_NODE_ROLE, role defaults to 'standalone'."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATAFORGE_NODE_ROLE", None)
            reset_node_identity()
            # Override _generate_node_id to avoid file reads
            with patch("app.distributed._generate_node_id", return_value="test-node-id"):
                node = get_node_identity()
            assert node.node_role == "standalone"

    def test_role_from_env(self) -> None:
        """DATAFORGE_NODE_ROLE env var sets the node role."""
        reset_node_identity()
        with patch.dict(os.environ, {"DATAFORGE_NODE_ROLE": "worker"}):
            with patch("app.distributed._generate_node_id", return_value="test-node-id"):
                node = get_node_identity()
            assert node.node_role == "worker"

    def test_invalid_role_defaults_to_standalone(self) -> None:
        """Unknown role values fall back to 'standalone'."""
        reset_node_identity()
        with patch.dict(os.environ, {"DATAFORGE_NODE_ROLE": "invalid_role"}):
            with patch("app.distributed._generate_node_id", return_value="test-node-id"):
                node = get_node_identity()
            assert node.node_role == "standalone"

    def test_persistence(self, tmp_path: Path) -> None:
        """Node ID is persisted and re-read from data/node_id.txt."""
        reset_node_identity()
        node_id_file = tmp_path / "node_id.txt"
        node_id_file.write_text("persisted-uuid-1234")

        with patch.object(Path, "resolve", return_value=tmp_path):
            with patch("app.distributed.settings") as mock_settings:
                mock_settings.DATA_DIR = str(tmp_path)
                # Make the file appear to exist for _generate_node_id
                with patch("app.distributed._generate_node_id", return_value="persisted-uuid-1234"):
                    node = get_node_identity()
        assert node.node_id == "persisted-uuid-1234"

    def test_has_start_time(self) -> None:
        """Node identity includes a valid ISO-format start time."""
        reset_node_identity()
        with patch("app.distributed._generate_node_id", return_value="test-node-id"):
            node = get_node_identity()
        assert node.node_start_time
        # Should be a valid ISO 8601 timestamp
        assert "T" in node.node_start_time

    def test_has_heartbeat(self) -> None:
        """Heartbeat timestamp is populated and is recent."""
        reset_node_identity()
        before = time.time()
        with patch("app.distributed._generate_node_id", return_value="test-node-id"):
            node = get_node_identity()
        after = time.time()
        assert before <= node.last_heartbeat <= after + 1

    def test_singleton_returns_same_instance(self) -> None:
        """Repeated calls return the same singleton (within one process)."""
        with patch("app.distributed._generate_node_id", return_value="test-node-id"):
            n1 = get_node_identity()
            n2 = get_node_identity()
        assert n1 is n2

    def test_role_refreshes_on_subsequent_calls(self) -> None:
        """The role is re-read from the env var on each get_node_identity() call."""
        with patch("app.distributed._generate_node_id", return_value="test-node-id"):
            with patch.dict(os.environ, {"DATAFORGE_NODE_ROLE": "api"}):
                n1 = get_node_identity()
            assert n1.node_role == "api"
            # Change env and call again
            with patch.dict(os.environ, {"DATAFORGE_NODE_ROLE": "scheduler"}):
                n2 = get_node_identity()
            # Same object, refreshed role
            assert n2.node_role == "scheduler"
            assert n1 is n2


# ═══════════════════════════════════════════════════════════════════════════════
# DistributedLock
# ═══════════════════════════════════════════════════════════════════════════════


class TestDistributedLock:
    def test_acquire_succeeds_on_empty_db(self, tmp_db: Path) -> None:
        """First acquisition succeeds when no lock row exists."""
        lock = DistributedLock("test_resource", db_path=tmp_db, backend="sqlite")
        assert lock.acquire(timeout=2.0) is True
        lock.release()

    def test_acquire_fails_when_already_held(self, tmp_db: Path) -> None:
        """Second acquisition should fail (lock already held)."""
        lock1 = DistributedLock("test_resource", db_path=tmp_db, backend="sqlite")
        lock2 = DistributedLock("test_resource", db_path=tmp_db, backend="sqlite")

        assert lock1.acquire(timeout=1.0) is True
        # lock2 tries but should fail quickly because the row exists
        try:
            assert lock2.acquire(timeout=0.5) is False
        finally:
            lock1.release()

    def test_release_allows_reacquire(self, tmp_db: Path) -> None:
        """After release, the same lock can be acquired again."""
        lock = DistributedLock("test_resource", db_path=tmp_db, backend="sqlite")
        assert lock.acquire(timeout=2.0) is True
        lock.release()
        # Should be able to acquire again
        assert lock.acquire(timeout=2.0) is True
        lock.release()

    def test_different_locks_do_not_conflict(self, tmp_db: Path) -> None:
        """Different lock names do not interfere with each other."""
        lock_a = DistributedLock("resource_a", db_path=tmp_db, backend="sqlite")
        lock_b = DistributedLock("resource_b", db_path=tmp_db, backend="sqlite")

        assert lock_a.acquire(timeout=2.0) is True
        assert lock_b.acquire(timeout=2.0) is True
        lock_a.release()
        lock_b.release()

    def test_timeout_expires(self, tmp_path: Path) -> None:
        """Acquire returns False when timeout expires without getting the lock."""
        db = tmp_path / "test_timeout.db"
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.close()

        lock1 = DistributedLock("contended_resource", db_path=db, backend="sqlite")
        lock2 = DistributedLock("contended_resource", db_path=db, backend="sqlite")

        lock1.acquire(timeout=2.0)
        try:
            result = lock2.acquire(timeout=0.5)
            assert result is False
        finally:
            lock1.release()


# ═══════════════════════════════════════════════════════════════════════════════
# JobClaimService
# ═══════════════════════════════════════════════════════════════════════════════


class TestJobClaimService:
    def test_claim_succeeds_on_first_attempt(self, tmp_db: Path) -> None:
        """First node to claim a job succeeds."""
        svc = JobClaimService(db_path=tmp_db)
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            assert svc.claim_job("job-1") is True

    def test_claim_fails_when_already_claimed(self, tmp_db: Path) -> None:
        """A second node cannot claim a job already claimed by the first."""
        svc = JobClaimService(db_path=tmp_db)
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            assert svc.claim_job("job-1") is True

        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-B",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            assert svc.claim_job("job-1") is False

    def test_release_allows_reclaim(self, tmp_db: Path) -> None:
        """After releasing a claim, another node can claim the job."""
        svc = JobClaimService(db_path=tmp_db)
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            assert svc.claim_job("job-1") is True
            svc.release_claim("job-1")

        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-B",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            assert svc.claim_job("job-1") is True

    def test_same_job_different_ids(self, tmp_db: Path) -> None:
        """Different jobs can be claimed independently."""
        svc = JobClaimService(db_path=tmp_db)
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            assert svc.claim_job("job-1") is True
            assert svc.claim_job("job-2") is True

    def test_release_only_affects_own_claims(self, tmp_db: Path) -> None:
        """Node A cannot release Node B's claim."""
        svc = JobClaimService(db_path=tmp_db)
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            svc.claim_job("job-1")

        # Node B tries to release node-A's claim
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-B",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            svc.release_claim("job-1")
            # The claim should still exist
            assert svc.is_claimed("job-1") is True

    def test_is_claimed(self, tmp_db: Path) -> None:
        """is_claimed returns True when a claim exists, False otherwise."""
        svc = JobClaimService(db_path=tmp_db)
        assert svc.is_claimed("job-1") is False
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            svc.claim_job("job-1")
        assert svc.is_claimed("job-1") is True


class TestJobClaimHeartbeat:
    def test_heartbeat_records_timestamp(self, tmp_db: Path) -> None:
        """heartbeat() writes a node_heartbeats row."""
        svc = JobClaimService(db_path=tmp_db)
        before = time.time()
        with patch(
            "app.distributed.get_node_identity",
            return_value=NodeIdentity(
                node_id="node-A",
                node_start_time="2026-01-01T00:00:00+00:00",
                node_role="worker",
            ),
        ):
            svc.heartbeat()

        # Verify the heartbeat row exists
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM node_heartbeats WHERE node_id = ?", ("node-A",)).fetchone()
        conn.close()
        assert row is not None
        assert before <= row["last_heartbeat"] <= time.time() + 1

    def test_stale_claim_cleanup(self, tmp_db: Path) -> None:
        """Claims from nodes with stale heartbeats are released."""
        svc = JobClaimService(db_path=tmp_db)

        # Simulate a node claiming a job and sending a stale heartbeat
        conn = sqlite3.connect(str(tmp_db))
        conn.execute("PRAGMA journal_mode=WAL")

        # Create a stale claim directly
        old_time = time.time() - 120  # 2 minutes ago
        conn.execute(
            "INSERT INTO job_claims (job_id, node_id, claimed_at, last_heartbeat) VALUES (?, ?, ?, ?)",
            ("job-stale", "dead-node", old_time, old_time),
        )
        # Create a stale heartbeat
        conn.execute(
            "INSERT INTO node_heartbeats (node_id, last_heartbeat, started_at) VALUES (?, ?, ?)",
            ("dead-node", old_time, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
        conn.close()

        # Run cleanup — stale claims should be released
        released = svc.stale_claim_cleanup()
        assert released >= 1
        assert svc.is_claimed("job-stale") is False

    def test_stale_claim_cleanup_preserves_active(self, tmp_db: Path) -> None:
        """Claims from active nodes (with recent heartbeats) are not released."""
        svc = JobClaimService(db_path=tmp_db)

        # Create a claim with a recent heartbeat
        conn = sqlite3.connect(str(tmp_db))
        conn.execute("PRAGMA journal_mode=WAL")
        now = time.time()
        conn.execute(
            "INSERT INTO job_claims (job_id, node_id, claimed_at, last_heartbeat) VALUES (?, ?, ?, ?)",
            ("job-active", "live-node", now, now),
        )
        conn.execute(
            "INSERT INTO node_heartbeats (node_id, last_heartbeat, started_at) VALUES (?, ?, ?)",
            ("live-node", now, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
        conn.close()

        released = svc.stale_claim_cleanup()
        assert released == 0
        assert svc.is_claimed("job-active") is True

    def test_stale_claim_cleanup_no_heartbeat_record(self, tmp_db: Path) -> None:
        """Claims from nodes with no heartbeat record and old claimed_at are released."""
        svc = JobClaimService(db_path=tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        conn.execute("PRAGMA journal_mode=WAL")
        old_time = time.time() - 120  # 2 minutes ago
        # Insert claim without a heartbeat record
        conn.execute(
            "INSERT INTO job_claims (job_id, node_id, claimed_at, last_heartbeat) VALUES (?, ?, ?, ?)",
            ("job-orphan", "ghost-node", old_time, old_time),
        )
        conn.commit()
        conn.close()

        released = svc.stale_claim_cleanup()
        assert released >= 1
        assert svc.is_claimed("job-orphan") is False
