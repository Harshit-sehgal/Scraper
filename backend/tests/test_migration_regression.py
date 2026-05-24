import sqlite3
import tempfile
from pathlib import Path
from app.job_store import _run_migrations, persist_state_single
from app.models import Job, JobStatus

def test_recycle_bin_migration_preservation():
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
            ("old-job-1", "Old Scraper 1", "failed", "manual", "flights", "['http://old.com']", "2026-05-01T00:00:00")
        )
        conn.execute(
            "INSERT INTO recycle_bin (id, name, status, mode, topic, urls, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-job-2", "Old Scraper 2", "completed", "auto", "hotels", "[]", "2026-05-02T00:00:00")
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


def test_persist_state_single(monkeypatch):
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
            progress_total=10
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
