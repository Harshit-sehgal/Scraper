"""Tests for storage/health/readiness endpoints."""

import asyncio

import httpx
from app.main import app

# Module-level in-memory job overrides —
# conftest.py usually resets these, but these tests
# only check liveness/readiness which does not depend
# on the in-memory store being populated.


class LocalASGIClient:
    """Small sync wrapper around httpx ASGITransport that avoids TestClient threads."""

    def __init__(self, app):
        self.app = app

    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        return asyncio.run(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)


client = LocalASGIClient(app)


class TestHealthEndpoint:
    """Tests for the /health liveness probe."""

    def test_health_returns_200(self) -> None:
        """/health should always return 200 with status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_is_fast(self) -> None:
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

    def _mock_sqlite_backend(self, monkeypatch):
        """Force SQLite backend for tests that assert sqlite-specific behavior."""
        from app.storage_interface import SQLiteJobRepository

        monkeypatch.setattr("app.main.get_job_repository", lambda: SQLiteJobRepository())

    def test_ready_returns_storage_ok(self) -> None:
        """/ready should check SQLite and return status."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["storage"] == "ok"
        assert data["migrations"] == "ok"

    def test_ready_includes_backend_type(self) -> None:
        """/ready should include the backend type."""
        response = client.get("/ready")
        data = response.json()
        assert "backend" in data
        assert data["backend"] in ("sqlite", "postgres")

    def test_ready_includes_schema_version(self, monkeypatch) -> None:
        """/ready should include schema_version >= 2."""
        self._mock_sqlite_backend(monkeypatch)
        response = client.get("/ready")
        data = response.json()
        assert "schema_version" in data
        assert data["schema_version"] >= 2

    def test_ready_includes_job_and_recycle_counts(self) -> None:
        """/ready should include job_count and recycle_bin_count."""
        response = client.get("/ready")
        data = response.json()
        assert "job_count" in data
        assert data["job_count"] >= 0
        assert "recycle_bin_count" in data
        assert data["recycle_bin_count"] >= 0


class TestDomainPolicyEndpoint:
    """Tests for the /api/system/domain-policy endpoint."""

    def test_domain_policy_returns_dict(self) -> None:
        """Domain policy endpoint should return a dict."""
        response = client.get("/api/system/domain-policy")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_domain_policy_includes_domain_keys(self) -> None:
        """After recording failures, the endpoint should include that domain."""
        from app.domain_runtime_policy import get_domain_runtime_policy, reset_domain_runtime_policy

        reset_domain_runtime_policy()
        policy = get_domain_runtime_policy()
        policy.record_failure("https://test-domain-policy.com/page")
        response = client.get("/api/system/domain-policy")
        data = response.json()
        assert "test-domain-policy.com" in data

    def test_domain_policy_includes_recommended_action(self) -> None:
        """Each domain entry should include a recommended_action."""
        from app.domain_runtime_policy import get_domain_runtime_policy, reset_domain_runtime_policy

        reset_domain_runtime_policy()
        policy = get_domain_runtime_policy()
        policy.record_failure("https://test-action.com/page")
        response = client.get("/api/system/domain-policy")
        data = response.json()
        entry = data.get("test-action.com", {})
        assert "recommended_action" in entry
        assert isinstance(entry["recommended_action"], str)

    def test_domain_policy_fields(self) -> None:
        """Each domain entry should have the expected fields."""
        from app.domain_runtime_policy import reset_domain_runtime_policy

        reset_domain_runtime_policy()
        from app.domain_runtime_policy import get_domain_runtime_policy

        policy = get_domain_runtime_policy()
        policy.record_failure("https://test-fields.com/page")
        policy.record_success("https://test-fields-ok.com/page")
        response = client.get("/api/system/domain-policy")
        data = response.json()
        for domain_key, entry in data.items():
            assert "max_parallel" in entry
            assert "cooldown_remaining" in entry
            assert "recent_failures" in entry
            assert "total_attempts" in entry
            assert "recommended_action" in entry


class TestStorageStatusEndpoint:
    """Tests for the /api/system/storage/status endpoint."""

    def _mock_sqlite_backend(self, monkeypatch):
        """Force SQLite backend for tests that assert sqlite-specific behavior."""
        from app.storage_interface import SQLiteJobRepository

        monkeypatch.setattr("app.main.get_job_repository", lambda: SQLiteJobRepository())

    def test_storage_status_returns_200(self, monkeypatch) -> None:
        """Storage status should return 200 with SQLite backend info."""
        self._mock_sqlite_backend(monkeypatch)
        response = client.get("/api/system/storage/status")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "sqlite"
        assert "db_path" in data
        assert data["db_path"].endswith(".db")

    def test_storage_status_includes_schema_version(self, monkeypatch) -> None:
        """Storage status should report schema version."""
        self._mock_sqlite_backend(monkeypatch)
        response = client.get("/api/system/storage/status")
        data = response.json()
        assert "schema_version" in data
        assert data["schema_version"] >= 2
        assert "latest_schema_version" in data

    def test_storage_status_includes_job_counts(self) -> None:
        """Storage status should report job and recycle bin counts."""
        response = client.get("/api/system/storage/status")
        data = response.json()
        assert "job_count" in data
        assert data["job_count"] >= 0
        assert "recycle_bin_count" in data

    def test_storage_status_includes_wal_mode(self, monkeypatch) -> None:
        """Storage status should report WAL mode."""
        self._mock_sqlite_backend(monkeypatch)
        response = client.get("/api/system/storage/status")
        data = response.json()
        assert "wal_mode" in data
        assert data["wal_mode"] == "wal"

    def test_ready_reports_sqlite_backend(self, monkeypatch) -> None:
        """/ready should report sqlite backend when using SQLite."""
        self._mock_sqlite_backend(monkeypatch)
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "sqlite"

    def test_storage_status_reports_sqlite(self, monkeypatch) -> None:
        """/api/system/storage/status should report sqlite backend when using SQLite."""
        self._mock_sqlite_backend(monkeypatch)
        response = client.get("/api/system/storage/status")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "sqlite"
        assert "db_path" in data
        assert data["db_path"].endswith(".db")


class TestReadyWithMockedPostgres:
    """Tests for /ready and /storage/status when using a mocked Postgres repository."""

    def _make_mock_postgres_repo(self, healthy: bool = True):
        """Create a mock PostgresJobRepository-like object."""
        from unittest.mock import MagicMock

        mock_repo = MagicMock()
        mock_repo.backend = "postgres"

        if healthy:
            mock_repo.health_check.return_value = {
                "ok": True,
                "backend": "postgres",
                "schema_version": 2,
                "expected_version": 2,
                "job_count": 5,
                "recycle_bin_count": 2,
            }
        else:
            mock_repo.health_check.return_value = {
                "ok": False,
                "backend": "postgres",
                "error": "Connection refused",
                "schema_version": 0,
                "expected_version": 2,
            }
        return mock_repo

    def test_ready_reports_postgres_backend(self, monkeypatch) -> None:
        """/ready should report postgres backend when Postgres repository is active."""
        mock_repo = self._make_mock_postgres_repo(healthy=True)
        monkeypatch.setattr("app.main.get_job_repository", lambda: mock_repo)

        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "postgres"
        assert data["storage"] == "ok"
        assert data["job_count"] == 5
        assert data["recycle_bin_count"] == 2

    def test_ready_returns_503_when_postgres_unhealthy(self, monkeypatch) -> None:
        """/ready should return 503 when Postgres repository is unhealthy."""
        mock_repo = self._make_mock_postgres_repo(healthy=False)
        monkeypatch.setattr("app.main.get_job_repository", lambda: mock_repo)

        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert "error" in data

    def test_storage_status_reports_postgres_counts(self, monkeypatch) -> None:
        """/api/system/storage/status should report postgres backend with counts."""
        mock_repo = self._make_mock_postgres_repo(healthy=True)
        monkeypatch.setattr("app.main.get_job_repository", lambda: mock_repo)

        response = client.get("/api/system/storage/status")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "postgres"
        assert data["ok"] is True
        assert data["schema_version"] == 2
        assert data["job_count"] == 5
        assert data["recycle_bin_count"] == 2

    def test_storage_status_reports_postgres_unhealthy(self, monkeypatch) -> None:
        """/api/system/storage/status should report postgres as not ok when unhealthy."""
        mock_repo = self._make_mock_postgres_repo(healthy=False)
        monkeypatch.setattr("app.main.get_job_repository", lambda: mock_repo)

        response = client.get("/api/system/storage/status")
        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == "postgres"
        assert data["ok"] is False
        assert "error" in data
