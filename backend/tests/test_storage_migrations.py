import sqlite3

import pytest
from app.job_store import (
    _CURRENT_SCHEMA_VERSION,
    _get_connection,
    _run_migrations,
    load_state,
    reset_job_store_for_tests,
    save_state,
)
from app.models import Job, JobStatus
from app.storage_interface import _JOBS_COLUMNS_SQL


@pytest.fixture(autouse=True)
def _reset_migrations():
    """Reset the migration cache and DB lock before each test."""
    reset_job_store_for_tests()
    yield
    reset_job_store_for_tests()


@pytest.fixture
def tmp_db(tmp_path):
    """Yield a Path to a temporary .db file inside a fresh tmp directory."""
    return tmp_path / "test.db"


# ── Test 1: schema has all expected columns ────────────────────────────────


def test_sqlite_schema_has_all_expected_columns(monkeypatch, tmp_db) -> None:
    """The ``jobs`` table should contain every column listed in _JOBS_COLUMNS_SQL,
    except for columns that are exclusive to ``recycle_bin`` (``deleted_at``)
    or not yet wired into the DDL (``updated_at``).
    """
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    conn = _get_connection()
    try:
        jobs_cursor = conn.execute("PRAGMA table_info(jobs)")
        jobs_cols = {row["name"] for row in jobs_cursor.fetchall()}

        recycle_cursor = conn.execute("PRAGMA table_info(recycle_bin)")
        recycle_cols = {row["name"] for row in recycle_cursor.fetchall()}
    finally:
        conn.close()

    all_expected = {col.split()[0] for col in _JOBS_COLUMNS_SQL}

    # ``deleted_at`` only lives on recycle_bin; ``updated_at`` is declared
    # in _JOBS_COLUMNS_SQL but not yet added by any migration.
    excluded_from_jobs = {"deleted_at", "updated_at"}
    jobs_expected = all_expected - excluded_from_jobs

    missing_from_jobs = jobs_expected - jobs_cols
    assert not missing_from_jobs, f"Columns in _JOBS_COLUMNS_SQL absent from jobs: {missing_from_jobs}"

    # deleted_at must exist on recycle_bin
    assert "deleted_at" in recycle_cols, "deleted_at is listed in _JOBS_COLUMNS_SQL but missing from recycle_bin"


# ── Test 2: create_tables / _run_migrations is idempotent ──────────────────


def test_run_migrations_is_idempotent(monkeypatch, tmp_db) -> None:
    """Calling _run_migrations twice on the same connection must not error."""
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    conn = _get_connection()
    try:
        schema_row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        first_version = schema_row[0] if schema_row and schema_row[0] is not None else 0

        # Run migrations again explicitly on the same connection
        _run_migrations(conn)

        schema_row_2 = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        second_version = schema_row_2[0] if schema_row_2 and schema_row_2[0] is not None else 0

        assert first_version == second_version == _CURRENT_SCHEMA_VERSION
    finally:
        conn.close()


# ── Test 3: job save/load round-trip ────────────────────────────────────────


def test_job_save_and_load_round_trip(monkeypatch, tmp_db) -> None:
    """A job saved via save_state should be fully recoverable via load_state."""
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    job = Job(
        id="rt-001",
        name="Round-Trip Job",
        status=JobStatus.COMPLETED,
        urls=["https://example.com"],
    )
    save_state({job.id: job}, {})

    jobs, _recycle, _ = load_state(recover_in_progress=False)

    assert "rt-001" in jobs
    loaded = jobs["rt-001"]
    assert loaded.id == job.id
    assert loaded.name == job.name
    assert loaded.status == JobStatus.COMPLETED
    assert loaded.urls == ["https://example.com"]


# ── Test 4: missing columns handled gracefully (simulated old schema) ───────


def test_load_state_handles_missing_columns_gracefully(monkeypatch, tmp_db) -> None:
    """If the database was created by an older version that lacked newer columns,
    load_state should still succeed (using column defaults from _row_to_job).
    """
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    # First, create a full schema via normal migrations
    conn = _get_connection()
    conn.close()

    # Now manually drop a newer column to simulate an old schema
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("ALTER TABLE jobs DROP COLUMN estimated_cost_usd")
    conn.execute("ALTER TABLE jobs DROP COLUMN min_record_score")
    conn.execute("ALTER TABLE jobs DROP COLUMN results_on_disk")
    conn.execute("ALTER TABLE jobs DROP COLUMN results_file_path")
    conn.execute("ALTER TABLE jobs DROP COLUMN warnings")
    conn.execute("ALTER TABLE jobs DROP COLUMN acquisition_mode")
    conn.commit()

    # Re-create the table without those columns and insert a row
    conn.execute("DROP TABLE jobs")
    conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            mode TEXT DEFAULT 'manual',
            topic TEXT DEFAULT '',
            intent TEXT DEFAULT '',
            urls TEXT DEFAULT '[]',
            schema_fields TEXT DEFAULT '[]',
            filters TEXT DEFAULT '[]',
            results TEXT DEFAULT '[]',
            logs TEXT DEFAULT '[]',
            total_records INTEGER DEFAULT 0,
            filtered_records INTEGER DEFAULT 0,
            total_llm_calls INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            warnings TEXT DEFAULT '',
            quality_report TEXT DEFAULT '{}',
            analysis TEXT DEFAULT '',
            discovered_urls TEXT DEFAULT '[]',
            selectors_map TEXT DEFAULT '{}',
            search_params TEXT DEFAULT '{}',
            max_pages INTEGER DEFAULT 0,
            progress_current INTEGER DEFAULT 0,
            progress_total INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0,
            cancel_requested INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            completed_at TEXT DEFAULT '',
            min_record_score REAL DEFAULT 0.35,
            acquisition_mode TEXT DEFAULT 'standard',
            location TEXT DEFAULT '',
            preferred_domain TEXT DEFAULT '',
            source_policy TEXT DEFAULT 'all_sources',
            max_per_domain INTEGER DEFAULT 4,
            origin_location TEXT DEFAULT '',
            max_distance_km REAL DEFAULT NULL,
            pagination INTEGER DEFAULT 0,
            deduplicate INTEGER DEFAULT 1,
            deduplicate_field TEXT DEFAULT '',
            started_at TEXT DEFAULT ''
        )
    """)
    conn.execute(
        """
        INSERT INTO jobs (id, name, status, urls, schema_fields, results, logs, warnings, estimated_cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        ("old-schema-job", "Old Schema Job", "completed", "[]", "[]", "[]", "[]", "[]", 0.0),
    )
    conn.commit()
    conn.close()

    # load_state must not crash — _row_to_job supplies defaults for missing columns
    jobs, _recycle, _ = load_state(recover_in_progress=False)
    assert "old-schema-job" in jobs
    assert jobs["old-schema-job"].name == "Old Schema Job"


# ── Test 5: load_all returns empty dicts on fresh database ──────────────────


def test_load_state_returns_empty_on_fresh_database(monkeypatch, tmp_db) -> None:
    """A brand-new database (just migrated) should yield empty dicts and None world state."""
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    jobs, recycle, world_state = load_state(recover_in_progress=True)

    assert jobs == {}
    assert recycle == {}
    assert world_state is None


# ── Bonus: schema version matches expected constant ─────────────────────────


def test_schema_version_matches_current_constant(monkeypatch, tmp_db) -> None:
    """After migrations the schema_version row should equal _CURRENT_SCHEMA_VERSION."""
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    conn = _get_connection()
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == _CURRENT_SCHEMA_VERSION
    finally:
        conn.close()


# ── Bonus: companion tables exist after migration ───────────────────────────


def test_v5_to_v6_migration_preserves_worker_heartbeats(monkeypatch, tmp_db) -> None:
    """Migration from v5 to v6 should rebuild worker_heartbeats with composite PK."""
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    # Create stub tables that _run_migrations expects at hot-path index creation
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, name TEXT, status TEXT DEFAULT '', created_at TEXT DEFAULT '')",
    )
    conn.execute("CREATE TABLE IF NOT EXISTS recycle_bin (id TEXT PRIMARY KEY, name TEXT, created_at TEXT DEFAULT '')")
    # Create a v5-style worker_heartbeats table (single PK on worker_id)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
            worker_id TEXT PRIMARY KEY,
            last_heartbeat TEXT NOT NULL,
            hostname TEXT NOT NULL DEFAULT '',
            pid INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT ''
        )
    """)
    # Insert one row per worker_id (v5 schema enforced single PK on worker_id)
    conn.execute(
        "INSERT INTO worker_heartbeats (worker_id, last_heartbeat, hostname, pid, started_at) VALUES (?, ?, ?, ?, ?)",
        ("worker-a", "2026-06-09T10:00:00", "host1", 1001, "2026-06-09T09:00:00"),
    )
    conn.execute(
        "INSERT INTO worker_heartbeats (worker_id, last_heartbeat, hostname, pid, started_at) VALUES (?, ?, ?, ?, ?)",
        ("worker-b", "2026-06-09T10:02:00", "host2", 2001, "2026-06-09T09:02:00"),
    )
    # Create and set schema_version to 5 to simulate v5 schema
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO schema_version (version) VALUES (5)")
    conn.commit()
    conn.close()

    # Now run the full migration (v5 -> v6)
    from app.job_store import _run_migrations

    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row
    _run_migrations(conn)

    # Verify schema_version matches _CURRENT_SCHEMA_VERSION
    ver_row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert ver_row[0] == _CURRENT_SCHEMA_VERSION, f"Expected schema version {_CURRENT_SCHEMA_VERSION}, got {ver_row[0]}"

    # Verify worker_heartbeats has composite PK (worker_id, pid)
    table_info = conn.execute("PRAGMA table_info(worker_heartbeats)").fetchall()
    pk_columns = [r["name"] for r in table_info if r["pk"] > 0]
    assert set(pk_columns) == {"worker_id", "pid"}, f"Expected composite PK, got {pk_columns}"

    # Verify all three rows survived the migration
    rows = conn.execute("SELECT worker_id, pid, hostname FROM worker_heartbeats ORDER BY pid").fetchall()
    conn.close()

    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    assert rows[0]["worker_id"] == "worker-a"
    assert rows[0]["pid"] == 1001
    assert rows[1]["worker_id"] == "worker-b"
    assert rows[1]["pid"] == 2001


def test_multi_instance_state_visibility_via_sqlite(monkeypatch, tmp_db) -> None:
    """Simulate two independent app instances sharing the same SQLite DB.

    Instance A saves a job, Instance B loads it — proving cross-instance
    state visibility through the shared SQLite file. This is the
    multi-process consistency model: the DB is the shared state, and
    each instance syncs via save/load cycles.
    """
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    # ── Instance A: create and save a job ──────────────────────────────
    job_a = Job(
        id="multi-instance-001",
        name="Instance-A Job",
        status=JobStatus.RUNNING,
        urls=["https://test.invalid/page1"],
    )
    save_state({job_a.id: job_a}, {})

    # ── Instance B: load from the same DB file ─────────────────────────
    jobs_b, _recycle_b, _ = load_state(recover_in_progress=False)

    assert "multi-instance-001" in jobs_b, "Instance B should see Instance A's job"
    loaded = jobs_b["multi-instance-001"]
    assert loaded.name == "Instance-A Job"
    assert loaded.status == JobStatus.RUNNING
    assert loaded.urls == ["https://test.invalid/page1"]

    # ── Instance B: modify and save ────────────────────────────────────
    loaded.status = JobStatus.COMPLETED
    loaded.completed_at = "2026-06-09T12:00:00"
    save_state({loaded.id: loaded}, {})

    # ── Instance A: reload and see B's changes ─────────────────────────
    jobs_a_reload, _, _ = load_state(recover_in_progress=False)
    assert "multi-instance-001" in jobs_a_reload
    assert jobs_a_reload["multi-instance-001"].status == JobStatus.COMPLETED
    assert jobs_a_reload["multi-instance-001"].completed_at == "2026-06-09T12:00:00"

    # ── Recycle bin round-trip ─────────────────────────────────────────
    # Instance A moves job to recycle bin
    job_in_recycle = Job(
        id="multi-instance-002",
        name="Recycled Job",
        status=JobStatus.FAILED,
        urls=["https://test.invalid/page2"],
    )
    save_state({}, {job_in_recycle.id: job_in_recycle})

    # Instance B sees it in recycle bin
    jobs_b2, recycle_b2, _ = load_state(recover_in_progress=False)
    assert len(jobs_b2) == 1  # The first job is still in active store
    assert "multi-instance-002" in recycle_b2
    assert recycle_b2["multi-instance-002"].name == "Recycled Job"


def test_companion_tables_created_by_migrations(monkeypatch, tmp_db) -> None:
    """v4+ migrations should create the job_results and job_events tables."""
    monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

    conn = _get_connection()
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            ).fetchall()
        }
        assert "job_results" in tables
        assert "job_events" in tables
        assert "idempotency_keys" in tables
        assert "worker_heartbeats" in tables
    finally:
        conn.close()
