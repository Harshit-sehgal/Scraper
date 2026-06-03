import sqlite3
import tempfile
from pathlib import Path

from app.job_store import _run_migrations, persist_state_single
from app.models import Job, JobStatus


def test_recycle_bin_migration_preservation() -> None:
    """Verify that old recycle bin columns are dynamically preserved during v2 migration without failures."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        # 1. Initialize a simplified version 1 database schema
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")

        # Old jobs table
        conn.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT ''
            )
        """)

        # Old recycle_bin table with fewer columns (v1 schema)
        conn.execute("""
            CREATE TABLE recycle_bin (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'manual',
                topic TEXT DEFAULT '',
                urls TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT ''
            )
        """)

        # Seed v1 recycle_bin records
        conn.execute(
            "INSERT INTO recycle_bin (id, name, status, mode, topic, urls, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-job-1", "Old Scraper 1", "failed", "manual", "flights", "['http://old.com']", "2026-05-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO recycle_bin (id, name, status, mode, topic, urls, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-job-2", "Old Scraper 2", "completed", "auto", "hotels", "[]", "2026-05-02T00:00:00"),
        )
        conn.commit()
        conn.close()

        # 2. Run migrations (upgrading to current schema version)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        _run_migrations(conn)

        # 3. Assert old rows are fully preserved and new columns are added
        rows = conn.execute("SELECT * FROM recycle_bin ORDER BY id").fetchall()
        assert len(rows) == 2

        r1 = dict(rows[0])
        assert r1["id"] == "old-job-1"
        assert r1["name"] == "Old Scraper 1"
        assert r1["status"] == "failed"
        assert r1["mode"] == "manual"
        assert r1["topic"] == "flights"
        assert r1["urls"] == "['http://old.com']"
        assert r1["created_at"] == "2026-05-01T00:00:00"
        # New columns are populated with defaults
        assert "deleted_at" in r1
        assert r1["deleted_at"] == ""

        r2 = dict(rows[1])
        assert r2["id"] == "old-job-2"
        assert r2["name"] == "Old Scraper 2"
        assert r2["status"] == "completed"
        assert r2["mode"] == "auto"
        assert r2["topic"] == "hotels"
        assert r2["urls"] == "[]"
        assert r2["created_at"] == "2026-05-02T00:00:00"
        assert "deleted_at" in r2
        assert r2["deleted_at"] == ""

        conn.close()

    finally:
        if db_path.exists():
            db_path.unlink()


def test_persist_state_single(monkeypatch) -> None:
    """Verify that persist_state_single correctly performs single-row upserts."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr("app.job_store._get_db_path", lambda: db_path)

        job = Job(
            id="persist-single-123",
            name="Single Persist Test",
            status=JobStatus.RUNNING,
            url="https://example.com",
            schema_fields=[],
            filters=[],
            progress_current=5,
            progress_total=10,
        )

        # Upsert single job row
        persist_state_single(job)

        # Verify row exists in table and values match
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", ("persist-single-123",)).fetchone()
        assert row is not None

        r = dict(row)
        assert r["name"] == "Single Persist Test"
        assert r["status"] == "running"
        assert r["progress_current"] == 5
        assert r["progress_total"] == 10
        conn.close()

    finally:
        if db_path.exists():
            db_path.unlink()


def test_migrations_cached_per_db_path(monkeypatch) -> None:
    """Verify that migrations are correctly cached per database path when STATE_FILE_PATH changes."""
    from app.config import settings
    from app.job_store import _MIGRATIONS_RUN_FOR, _get_connection, reset_job_store_for_tests

    # Reset migration cache for the test
    reset_job_store_for_tests()

    with (
        tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp1,
        tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp2,
    ):
        db_path1 = Path(tmp1.name)
        db_path2 = Path(tmp2.name)

    try:
        # DB 1 setup: change settings.STATE_FILE_PATH dynamically
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path1))

        # Connect to DB 1: this should run migrations
        conn1 = _get_connection()
        conn1.close()

        assert db_path1 in _MIGRATIONS_RUN_FOR
        assert db_path2 not in _MIGRATIONS_RUN_FOR

        # DB 2 setup: change settings.STATE_FILE_PATH dynamically
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path2))

        # Connect to DB 2: this should run migrations again for the new path
        conn2 = _get_connection()
        conn2.close()

        assert db_path2 in _MIGRATIONS_RUN_FOR

        # Verify that schema version tables were created in both databases
        for path in [db_path1, db_path2]:
            conn = sqlite3.connect(str(path))
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            assert row is not None
            assert row[0] == 3
            conn.close()

    finally:
        if db_path1.exists():
            db_path1.unlink()
        if db_path2.exists():
            db_path2.unlink()


def test_progress_persistence_without_full_state_rewrite(monkeypatch) -> None:
    """Verify that run_job uses single-row persistence instead of full state saves."""
    import asyncio

    from app.domain_runtime_policy import reset_domain_runtime_policy
    from app.models import Job, JobStatus
    from app.services.job_runner import run_job

    # Counter to verify which persistence functions were called
    full_state_writes = 0
    single_row_writes = 0

    def mock_persist_state():
        nonlocal full_state_writes
        full_state_writes += 1

    def mock_persist_single():
        nonlocal single_row_writes
        single_row_writes += 1

    # Define minimal job and store
    job_id = "test-job-hot-updates"
    job = Job(
        id=job_id, name="Hot Update Test", status=JobStatus.PENDING, urls=["https://example.com"], schema_fields=[], filters=[]
    )
    jobs_store = {job_id: job}

    # Let's mock scrape_url_with_recovery to return result immediately
    async def mock_scrape_url_with_recovery(*args, **kwargs):
        return [{"title": "Test record"}], {"acquisition_lineage": {}, "recovery_attempts": 0}

    async def mock_generate_data_insight(*args, **kwargs):
        return "Mock insight."

    reset_domain_runtime_policy()
    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", mock_scrape_url_with_recovery)
    monkeypatch.setattr("app.scraper.generate_data_insight", mock_generate_data_insight)
    monkeypatch.setattr("app.services.job_runner.load_semantic_state", lambda: None)
    monkeypatch.setattr("app.services.job_runner.save_semantic_state", lambda: None)

    # Let's run run_job with the mocks
    try:
        asyncio.run(
            run_job(
                job_id=job_id,
                jobs_store=jobs_store,
                persist_state_fn=mock_persist_state,
                max_discovery_urls=5,
                max_job_runtime_seconds=5,
                per_url_scrape_timeout_seconds=5,
                ai_structuring_timeout_seconds=5,
                insight_timeout_seconds=5,
                persist_state_single_fn=mock_persist_single,
                persist_state_single_critical_fn=mock_persist_single,
            )
        )
    finally:
        reset_domain_runtime_policy()

    # Assert that the job successfully completed
    assert job.status == JobStatus.COMPLETED

    # Assert that single-row writes were called (for progress/log updates) and full-state writes were NOT called!
    assert single_row_writes > 0
    assert full_state_writes == 0


def test_schema_invalidation_and_recreation(monkeypatch) -> None:
    """Verify that _get_connection correctly handles SQLite database recreation when cached."""
    from app.config import settings
    from app.job_store import _get_connection, reset_job_store_for_tests

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))

        # 1. Establish connection (runs migrations)
        conn = _get_connection()
        conn.close()

        # 2. Delete the database file (as in dynamic developer/test file removal)
        db_path.unlink()

        # 3. Establish connection again. Because _MIGRATIONS_RUN_FOR holds the path,
        # it would skip migrations unless it verifies the schema exists in the DB.
        conn = _get_connection()
        # Verify schema is recreated successfully
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        assert row is not None
        assert row[0] == 3
        conn.close()

    finally:
        if db_path.exists():
            db_path.unlink()


def test_save_and_load_job_from_sqlite(monkeypatch) -> None:
    """Verify full serialization and deserialization cycle of all Job fields using save_state and load_state."""
    from app.config import settings
    from app.job_store import load_state, reset_job_store_for_tests, save_state
    from app.models import FieldType, Job, JobStatus, SchemaField, ScrapeMode

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))

        job = Job(
            id="job-full-serde",
            name="Full Serde Scraper",
            status=JobStatus.COMPLETED,
            mode=ScrapeMode.AUTO,
            topic="flights",
            intent="find cheap flights",
            urls=["https://example.com/flights"],
            schema_fields=[SchemaField(name="price", field_type=FieldType.CURRENCY)],
            results=[{"price": "$200"}],
            total_records=1,
            filtered_records=1,
            total_llm_calls=3,
            estimated_cost_usd=0.07,
            cancel_requested=False,
        )

        jobs_store = {job.id: job}
        recycle_bin_store: dict = {}

        save_state(jobs_store, recycle_bin_store)

        loaded_jobs, loaded_recycle, _ = load_state()

        assert job.id in loaded_jobs
        loaded_job = loaded_jobs[job.id]

        assert loaded_job.name == job.name
        assert loaded_job.status == job.status
        assert loaded_job.mode == job.mode
        assert loaded_job.topic == job.topic
        assert loaded_job.intent == job.intent
        assert loaded_job.urls == job.urls
        assert [f.name for f in loaded_job.schema_fields] == ["price"]
        assert loaded_job.results == job.results
        assert loaded_job.total_records == job.total_records
        assert loaded_job.filtered_records == job.filtered_records
        assert loaded_job.total_llm_calls == job.total_llm_calls
        assert loaded_job.estimated_cost_usd == job.estimated_cost_usd
        assert loaded_job.cancel_requested == job.cancel_requested

    finally:
        if db_path.exists():
            db_path.unlink()


def test_running_job_marked_failed_after_restart(monkeypatch) -> None:
    """Verify that jobs in PENDING/DISCOVERING/RUNNING state are transitioned to FAILED with a restart error when loaded on restart."""  # noqa: E501
    from app.config import settings
    from app.job_store import load_state, reset_job_store_for_tests, save_state
    from app.models import Job, JobStatus

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))

        job_running = Job(
            id="job-running-restart",
            name="Running Scraper",
            status=JobStatus.RUNNING,
            urls=["https://example.com"],
            schema_fields=[],
        )

        jobs_store = {job_running.id: job_running}
        recycle_bin_store: dict = {}

        save_state(jobs_store, recycle_bin_store)

        loaded_jobs, _, _ = load_state()

        assert job_running.id in loaded_jobs
        loaded = loaded_jobs[job_running.id]
        assert loaded.status == JobStatus.FAILED
        assert "Recovered after restart" in loaded.error

    finally:
        if db_path.exists():
            db_path.unlink()


def test_persist_state_single_updates_only_one_job(monkeypatch) -> None:
    """Verify that persist_state_single only updates the single target job row and does not affect other jobs."""
    from app.config import settings
    from app.job_store import persist_state_single, reset_job_store_for_tests, save_state
    from app.models import Job, JobStatus

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))
        monkeypatch.setattr("app.job_store._get_db_path", lambda: db_path)

        j1 = Job(id="j1", name="Job 1", status=JobStatus.COMPLETED, urls=["https://url1"], schema_fields=[])
        j2 = Job(id="j2", name="Job 2", status=JobStatus.PENDING, urls=["https://url2"], schema_fields=[])

        save_state({j1.id: j1, j2.id: j2}, {})

        # Modify j1 only and persist single
        j1.status = JobStatus.FAILED
        j1.error = "Forced fail"
        persist_state_single(j1)

        # Verify db contents directly
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        r1 = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", ("j1",)).fetchone())
        r2 = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", ("j2",)).fetchone())
        conn.close()

        assert r1["status"] == "failed"
        assert r1["error"] == "Forced fail"

        # Ensure j2 remained untouched
        assert r2["status"] == "pending"
        assert r2["error"] == ""

    finally:
        if db_path.exists():
            db_path.unlink()


def test_json_to_sqlite_migration_imports_existing_jobs(monkeypatch) -> None:
    """Verify that if a legacy JSON state file is present, it is successfully imported into a fresh SQLite database on load."""
    import json

    from app.config import settings
    from app.job_store import load_state, reset_job_store_for_tests
    from app.models import JobStatus

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = Path(tmp_db.name)
    json_path = db_path.with_suffix(".json")

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))

        # Write mock legacy JSON state
        legacy_data = {
            "jobs": [
                {"id": "legacy-j1", "name": "Legacy 1", "status": "completed", "urls": ["https://legacy"], "schema_fields": []}
            ],
            "recycle_bin": [],
        }
        json_path.write_text(json.dumps(legacy_data))

        # Load state: this should trigger json migration
        loaded_jobs, _, _ = load_state()

        assert "legacy-j1" in loaded_jobs
        assert loaded_jobs["legacy-j1"].name == "Legacy 1"
        assert loaded_jobs["legacy-j1"].status == JobStatus.COMPLETED

    finally:
        if db_path.exists():
            db_path.unlink()
        if json_path.exists():
            json_path.unlink()


def test_same_domain_concurrency_respected(monkeypatch) -> None:
    """Verify that domain-level concurrency max_parallel limit is respected when scraping multiple same-domain URLs."""
    import asyncio

    from app.domain_runtime_policy import get_domain_runtime_policy, reset_domain_runtime_policy
    from app.models import Job, JobStatus
    from app.services.job_runner import run_job

    # Configure the test domain to have max_parallel = 1
    reset_domain_runtime_policy()
    policy = get_domain_runtime_policy()
    policy.get_or_create("https://testdomain.com/1").max_parallel = 1

    concurrency_record = []
    active_scrapes = 0
    max_active_scrapes = 0

    async def mock_scrape_url_with_recovery(*args, **kwargs):
        nonlocal active_scrapes, max_active_scrapes
        active_scrapes += 1
        max_active_scrapes = max(max_active_scrapes, active_scrapes)
        concurrency_record.append(active_scrapes)
        await asyncio.sleep(0.05)  # Simulate network delay
        active_scrapes -= 1
        return [{"title": "Record"}], {"acquisition_lineage": {}, "recovery_attempts": 0}

    async def mock_generate_data_insight(*args, **kwargs):
        return "Mock insight."

    monkeypatch.setattr("app.services.job_runner.scrape_url_with_recovery", mock_scrape_url_with_recovery)
    monkeypatch.setattr("app.scraper.generate_data_insight", mock_generate_data_insight)
    monkeypatch.setattr("app.services.job_runner.load_semantic_state", lambda: None)
    monkeypatch.setattr("app.services.job_runner.save_semantic_state", lambda: None)

    # We create a job with 3 URLs of the SAME domain
    job = Job(
        id="domain-concurrency-job",
        name="Domain Concurrency",
        status=JobStatus.PENDING,
        urls=[
            "https://testdomain.com/1",
            "https://testdomain.com/2",
            "https://testdomain.com/3",
        ],
        schema_fields=[],
        filters=[],
    )

    # Run the job
    try:
        asyncio.run(
            run_job(
                job_id=job.id,
                jobs_store={job.id: job},
                persist_state_fn=lambda: None,
                max_discovery_urls=5,
                max_job_runtime_seconds=5,
                per_url_scrape_timeout_seconds=5,
                ai_structuring_timeout_seconds=5,
                insight_timeout_seconds=5,
            )
        )
    finally:
        reset_domain_runtime_policy()

    # Since same domain has max_parallel = 1, the active_scrapes must never exceed 1!
    assert max_active_scrapes == 1
    assert job.status == JobStatus.COMPLETED


def test_sqlite_preserves_all_job_fields(monkeypatch) -> None:
    """Verify that all Job model fields (e.g. location, source_policy, results_on_disk, etc.) are fully preserved in SQLite."""
    from app.config import settings
    from app.job_store import load_state, reset_job_store_for_tests, save_state
    from app.models import Job, JobStatus, SourcePolicy

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))

        job = Job(
            id="job-all-fields-serde",
            name="All Fields Scraper",
            status=JobStatus.COMPLETED,
            location="London, UK",
            preferred_domain="example.co.uk",
            source_policy=SourcePolicy.OFFICIAL_ONLY,
            max_per_domain=12,
            origin_location="New York",
            max_distance_km=25.5,
            pagination=True,
            deduplicate=False,
            deduplicate_field="email",
            started_at="2026-05-25T12:00:00",
            results_on_disk=True,
            results_file_path="/tmp/results.json.gz",
        )

        save_state({job.id: job}, {})

        loaded_jobs, _, _ = load_state()
        assert job.id in loaded_jobs
        loaded = loaded_jobs[job.id]

        assert loaded.location == "London, UK"
        assert loaded.preferred_domain == "example.co.uk"
        assert loaded.source_policy == SourcePolicy.OFFICIAL_ONLY
        assert loaded.max_per_domain == 12
        assert loaded.origin_location == "New York"
        assert loaded.max_distance_km == 25.5
        assert loaded.pagination is True
        assert loaded.deduplicate is False
        assert loaded.deduplicate_field == "email"
        assert loaded.started_at == "2026-05-25T12:00:00"
        assert loaded.results_on_disk is True
        assert loaded.results_file_path == "/tmp/results.json.gz"

    finally:
        if db_path.exists():
            db_path.unlink()


def test_offloaded_results_survive_restart(monkeypatch) -> None:
    """Verify that offloaded results settings survive reboot/recovery status transitions safely."""
    from app.config import settings
    from app.job_store import load_state, reset_job_store_for_tests, save_state
    from app.models import Job, JobStatus

    reset_job_store_for_tests()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(db_path))

        job = Job(
            id="job-offload-survive",
            name="Offloaded Job",
            status=JobStatus.RUNNING,
            results_on_disk=True,
            results_file_path="/tmp/offloaded_records.json.gz",
            results=[],
        )

        save_state({job.id: job}, {})

        # Load state triggers restart transition to FAILED
        loaded_jobs, _, _ = load_state()

        assert job.id in loaded_jobs
        loaded = loaded_jobs[job.id]
        assert loaded.status == JobStatus.FAILED
        assert loaded.results_on_disk is True
        assert loaded.results_file_path == "/tmp/offloaded_records.json.gz"

    finally:
        if db_path.exists():
            db_path.unlink()
