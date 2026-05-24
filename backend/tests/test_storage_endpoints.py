"""Tests for storage/health/readiness endpoints."""

from fastapi.testclient import TestClient
from app.main import app

# Module-level in-memory job overrides —
# conftest.py usually resets these, but these tests
# only check liveness/readiness which does not depend
# on the in-memory store being populated.

client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the /health liveness probe."""

    def test_health_returns_200(self):
        """/health should always return 200 with status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_is_fast(self):
        """/health should respond quickly (lightweight check)."""
        import time
        start = time.monotonic()
        for _ in range(10):
            client.get("/health")
        elapsed = time.monotonic() - start
        # 10 calls in < 5s is very generous for a local health check
        assert elapsed < 5.0, f"Health check too slow: {elapsed:.2f}s for 10 calls"


class TestReadyEndpoint:
    """Tests for the /ready readiness probe."""

    def test_ready_returns_storage_ok(self):
        """/ready should check SQLite and return status."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["storage"] == "ok"
        assert data["migrations"] == "ok"

    def test_ready_includes_db_path(self):
        """/ready should include the database path."""
        response = client.get("/ready")
        data = response.json()
        assert "db_path" in data
        assert data["db_path"].endswith(".db")


class TestStorageStatusEndpoint:
    """Tests for the /api/system/storage/status endpoint."""

    def test_storage_status_returns_200(self):
        """Storage status should return 200 with SQLite backend info."""
        response = client.get("/api/system/storage/status")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "sqlite"
        assert "db_path" in data
        assert data["db_path"].endswith(".db")

    def test_storage_status_includes_schema_version(self):
        """Storage status should report schema version."""
        response = client.get("/api/system/storage/status")
        data = response.json()
        assert "schema_version" in data
        assert data["schema_version"] >= 2
        assert "latest_schema_version" in data

    def test_storage_status_includes_job_counts(self):
        """Storage status should report job and recycle bin counts."""
        response = client.get("/api/system/storage/status")
        data = response.json()
        assert "job_count" in data
        assert data["job_count"] >= 0
        assert "recycle_bin_count" in data

    def test_storage_status_includes_wal_mode(self):
        """Storage status should report WAL mode."""
        response = client.get("/api/system/storage/status")
        data = response.json()
        assert "wal_mode" in data
        assert data["wal_mode"] == "wal"
