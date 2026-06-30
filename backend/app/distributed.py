"""Horizontal Scaling Support — node identity, distributed locks, and job claims.

Provides:
- ``NodeIdentity``: unique per-node identity persisted to ``data/node_id.txt``,
  with role (api / worker / scheduler / standalone) from ``DATAFORGE_NODE_ROLE``.
- ``DistributedLock``: advisory locks using SQLite ``BEGIN EXCLUSIVE`` or
  PostgreSQL ``pg_advisory_lock`` so that multi-node deployments can safely
  share the database without stepping on each other.
- ``JobClaimService``: atomic job claim/release via DB-level lock, heartbeat
  tracking, and stale-claim cleanup for crashed/restarted nodes.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ── Node Identity ────────────────────────────────────────────────────────


@dataclass
class NodeIdentity:
    """Unique identity for this node in a multi-node deployment.

    Attributes:
        node_id: UUID4, persisted to ``data/node_id.txt`` so it survives
            restarts.  A new ID is generated only when the file is missing.
        node_start_time: ISO-format UTC timestamp of when this node
            process was initialised.
        node_role: One of ``api``, ``worker``, ``scheduler``, or
            ``standalone`` (default).  Read from the ``DATAFORGE_NODE_ROLE``
            environment variable.
        last_heartbeat: Monotonic timestamp of the most recent heartbeat.
    """

    node_id: str
    node_start_time: str
    node_role: str = "standalone"
    last_heartbeat: float = field(default_factory=time.time)


_NODE_IDENTITY: NodeIdentity | None = None
_NODE_IDENTITY_LOCK = threading.Lock()


def _generate_node_id(data_dir: str | None = None) -> str:
    """Generate a UUID4 and persist it so the node keeps its identity across restarts."""
    ddir = Path(data_dir or settings.DATA_DIR).resolve()
    ddir.mkdir(parents=True, exist_ok=True)
    node_id_file = ddir / "node_id.txt"

    if node_id_file.exists():
        try:
            existing = node_id_file.read_text().strip()
            if existing:
                return existing
        except (OSError, ValueError):
            logger.debug("Failed to read existing node_id.txt, generating a new ID")

    new_id = str(uuid.uuid4())
    try:
        node_id_file.write_text(new_id)
    except OSError:
        logger.warning("Failed to persist node ID to %s; using ephemeral ID", node_id_file)
    return new_id


def get_node_identity() -> NodeIdentity:
    """Return the singleton NodeIdentity for this process.

    The node role is read from the ``DATAFORGE_NODE_ROLE`` env var at
    each call so that late-bound environment changes are respected.
    """
    global _NODE_IDENTITY
    with _NODE_IDENTITY_LOCK:
        if _NODE_IDENTITY is None:
            node_id = _generate_node_id()
            role = (os.environ.get("DATAFORGE_NODE_ROLE") or "standalone").strip().lower()
            if role not in {"api", "worker", "scheduler", "standalone"}:
                logger.warning("Unknown DATAFORGE_NODE_ROLE=%r, defaulting to 'standalone'", role)
                role = "standalone"
            _NODE_IDENTITY = NodeIdentity(
                node_id=node_id,
                node_start_time=datetime.datetime.now(tz=datetime.UTC).isoformat(),
                node_role=role,
            )
        else:
            # Refresh role from env on each access (allows dynamic reconfiguration)
            _NODE_IDENTITY.node_role = (os.environ.get("DATAFORGE_NODE_ROLE") or "standalone").strip().lower()
            if _NODE_IDENTITY.node_role not in {"api", "worker", "scheduler", "standalone"}:
                _NODE_IDENTITY.node_role = "standalone"
        _NODE_IDENTITY.last_heartbeat = time.time()
        return _NODE_IDENTITY


def reset_node_identity() -> None:
    """Drop the singleton (testing only)."""
    global _NODE_IDENTITY
    with _NODE_IDENTITY_LOCK:
        _NODE_IDENTITY = None


# ── Distributed Lock ────────────────────────────────────────────────────


class DistributedLock:
    """Advisory lock for shared resources across multiple nodes.

    For **SQLite**: uses ``BEGIN EXCLUSIVE`` on a lock table row so that
    only one writer can hold the lock at a time.  The lock is automatically
    released when the transaction commits or rolls back.

    For **PostgreSQL**: uses ``pg_advisory_lock(hash32(lock_name))``
    which is session-level (released on disconnect or explicit unlock).

    Usage::

        lock = DistributedLock("my_resource")
        if lock.acquire(timeout=5.0):
            try:
                # critical section
                ...
            finally:
                lock.release()
    """

    def __init__(
        self,
        lock_name: str,
        db_path: Path | None = None,
        backend: str | None = None,
    ) -> None:
        self.lock_name = lock_name
        self._db_path = db_path
        self._backend = backend or (os.environ.get("DATAFORGE_QUEUE_BACKEND") or "sqlite").strip().lower()
        self._lock_hash: int | None = None
        self._conn: sqlite3.Connection | None = None
        self._pg_conn: Any | None = None

    def _hash_lock_name(self) -> int:
        """Produce a stable int32 hash from the lock name for pg_advisory_lock."""
        digest = hashlib.sha256(self.lock_name.encode()).digest()
        return int.from_bytes(digest[:4], "big", signed=True)

    def _ensure_lock_table(self, conn: sqlite3.Connection) -> None:
        """Create the distributed_lock table if it doesn't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS distributed_lock (
                lock_name TEXT PRIMARY KEY,
                holder_node_id TEXT,
                acquired_at REAL
            )
        """)
        conn.commit()

    def acquire(self, timeout: float = 10.0) -> bool:
        """Attempt to acquire the distributed lock.

        Returns True if the lock was obtained within *timeout* seconds,
        False otherwise.
        """
        if self._backend == "postgres":
            return self._acquire_postgres(timeout)
        return self._acquire_sqlite(timeout)

    def _acquire_sqlite(self, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                db_path = self._db_path or Path(settings.DATA_DIR).resolve() / "worker_queue.db"
                conn = sqlite3.connect(str(db_path), timeout=timeout, isolation_level="EXCLUSIVE")
                conn.execute("PRAGMA journal_mode=WAL")
                self._ensure_lock_table(conn)
                # Try to insert this lock row — if it already exists the
                # INSERT fails and we retry.
                try:
                    node_id = get_node_identity().node_id
                    conn.execute(
                        "INSERT INTO distributed_lock (lock_name, holder_node_id, acquired_at) VALUES (?, ?, ?)",
                        (self.lock_name, node_id, time.time()),
                    )
                    conn.commit()
                    self._conn = conn
                    return True
                except sqlite3.IntegrityError:
                    # Lock already held — check if it's stale
                    row = conn.execute(
                        "SELECT holder_node_id, acquired_at FROM distributed_lock WHERE lock_name = ?",
                        (self.lock_name,),
                    ).fetchone()
                    if row is not None:
                        conn.rollback()
                        conn.close()
                    continue
            except sqlite3.OperationalError:
                # Database is locked by another process — retry
                if self._conn:
                    with contextlib.suppress(Exception):
                        self._conn.close()
                    self._conn = None
                remaining = deadline - time.time()
                if remaining > 0:
                    time.sleep(min(0.1, remaining))
                continue
            except Exception:
                logger.debug("[DistributedLock] Unexpected error acquiring SQLite lock", exc_info=True)
                if self._conn:
                    with contextlib.suppress(Exception):
                        self._conn.close()
                    self._conn = None
                return False
        return False

    def _acquire_postgres(self, timeout: float) -> bool:
        """Acquire a PostgreSQL advisory lock."""
        deadline = time.time() + timeout
        lock_int = self._hash_lock_name()
        while time.time() < deadline:
            try:
                import psycopg2

                from app.postgres_repository import get_database_url

                conn = psycopg2.connect(get_database_url())
                conn.autocommit = True
                with conn.cursor() as cur:
                    # pg_advisory_lock blocks until acquired; use try_lock for non-blocking
                    cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_int,))
                    acquired = cur.fetchone()[0]
                if acquired:
                    self._pg_conn = conn
                    return True
                conn.close()
                remaining = deadline - time.time()
                if remaining > 0:
                    time.sleep(min(0.5, remaining))
            except Exception:
                logger.debug("[DistributedLock] Postgres lock error", exc_info=True)
                return False
        return False

    def release(self) -> None:
        """Release the distributed lock."""
        if self._backend == "postgres":
            self._release_postgres()
        else:
            self._release_sqlite()

    def _release_sqlite(self) -> None:
        if self._conn is not None:
            try:
                self._conn.execute("DELETE FROM distributed_lock WHERE lock_name = ?", (self.lock_name,))
                self._conn.commit()
            except (sqlite3.OperationalError, sqlite3.ProgrammingError):
                logger.debug("[DistributedLock] Error releasing SQLite lock", exc_info=True)
            finally:
                with contextlib.suppress(Exception):
                    self._conn.close()
                self._conn = None

    def _release_postgres(self) -> None:
        if self._pg_conn is not None:
            lock_int = self._hash_lock_name()
            try:
                with self._pg_conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (lock_int,))
            except Exception:
                logger.debug("[DistributedLock] Error releasing Postgres lock", exc_info=True)
            finally:
                with contextlib.suppress(Exception):
                    self._pg_conn.close()
                self._pg_conn = None


# ── Job Claim Service ──────────────────────────────────────────────────


class JobClaimService:
    """Prevents duplicate job processing across nodes.

    Uses database-level locks to atomically claim a job for processing,
    so only one node in a horizontal deployment can work on a given job
    at a time.
    """

    HEARTBEAT_STALE_THRESHOLD: float = 60.0
    """Seconds after which a node is considered dead and its claims can be released."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        db_path = self._db_path or Path(settings.DATA_DIR).resolve() / "worker_queue.db"
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_claims (
                    job_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    claimed_at REAL NOT NULL,
                    last_heartbeat REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_claims_node
                    ON job_claims(node_id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_heartbeats (
                    node_id TEXT PRIMARY KEY,
                    last_heartbeat REAL NOT NULL,
                    started_at TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def claim_job(self, job_id: str) -> bool:
        """Atomically claim a job for this node.

        Returns True if the claim was successful (this node now owns the
        job), False if another node already holds the claim.
        """
        node = get_node_identity()
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Check if already claimed
            row = conn.execute(
                "SELECT node_id FROM job_claims WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is not None:
                conn.execute("ROLLBACK")
                return False
            now = time.time()
            conn.execute(
                "INSERT INTO job_claims (job_id, node_id, claimed_at, last_heartbeat) VALUES (?, ?, ?, ?)",
                (job_id, node.node_id, now, now),
            )
            conn.execute("COMMIT")
            return True
        except (sqlite3.OperationalError, sqlite3.IntegrityError):
            with contextlib.suppress(Exception):
                conn.execute("ROLLBACK")
            return False
        finally:
            conn.close()

    def release_claim(self, job_id: str) -> None:
        """Release a job claim so another node can pick it up."""
        node = get_node_identity()
        conn = self._conn()
        try:
            conn.execute(
                "DELETE FROM job_claims WHERE job_id = ? AND node_id = ?",
                (job_id, node.node_id),
            )
            conn.commit()
        finally:
            conn.close()

    def heartbeat(self) -> None:
        """Update this node's heartbeat timestamp.

        Should be called periodically (e.g. every 30 s) from the worker
        main loop so that other nodes can detect if this one is alive.
        """
        node = get_node_identity()
        node.last_heartbeat = time.time()
        conn = self._conn()
        try:
            now = time.time()
            conn.execute(
                """INSERT INTO node_heartbeats (node_id, last_heartbeat, started_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(node_id) DO UPDATE SET last_heartbeat = ?""",
                (node.node_id, now, node.node_start_time, now),
            )
            conn.commit()
        finally:
            conn.close()

    def stale_claim_cleanup(self) -> int:
        """Release claims held by nodes with stale heartbeats.

        A node is considered stale when its last heartbeat was more than
        ``HEARTBEAT_STALE_THRESHOLD`` seconds ago (default 60 s).  Nodes
        that have never sent a heartbeat (crashed before first tick) but
        whose ``claimed_at`` is older than the threshold are also released.

        Returns the number of claims released.
        """
        cutoff = time.time() - self.HEARTBEAT_STALE_THRESHOLD
        conn = self._conn()
        try:
            # Find stale node IDs (those whose heartbeat timestamp is older
            # than the threshold — either deceased or paused).
            stale_nodes = conn.execute(
                "SELECT node_id FROM node_heartbeats WHERE last_heartbeat < ?",
                (cutoff,),
            ).fetchall()
            stale_ids = [row["node_id"] for row in stale_nodes]

            released = 0
            for stale_id in stale_ids:
                result = conn.execute(
                    "DELETE FROM job_claims WHERE node_id = ?",
                    (stale_id,),
                )
                released += max(result.rowcount, 0)

            # Orphan claims: nodes with no heartbeat record at all
            # nosec B608 — parameterised query, placeholder '?' is used
            result = conn.execute(
                """
                DELETE FROM job_claims
                WHERE node_id NOT IN (SELECT node_id FROM node_heartbeats)
                AND claimed_at < ?
                """,
                (cutoff,),
            )
            released += max(result.rowcount, 0)
            conn.commit()
            if released > 0:
                logger.info("[JobClaimService] Released %d stale job claims", released)
            return released
        finally:
            conn.close()

    def is_claimed(self, job_id: str) -> bool:
        """Check whether a job is currently claimed by any node."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM job_claims WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
