"""Contract tests for ``GET /api/jobs`` pagination.

The route accepts ``limit`` and ``cursor`` query parameters and returns
``next_cursor`` in addition to ``jobs``. The shape is additive so older
callers that ignore ``next_cursor`` keep working.
"""

import importlib

import pytest


@pytest.fixture
def client():
    """Build a TestClient with a fresh app module per test."""
    import os
    import sys

    os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
    os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
    os.environ.setdefault("PYTHONPATH", "backend")
    # Make sure the backend root is on sys.path.
    backend = os.path.join(os.getcwd(), "backend")  # noqa: PTH109, PTH118
    if backend not in sys.path:
        sys.path.insert(0, backend)
    # Reload main to pick up the env vars set in this fixture.
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


class TestListJobsPagination:
    def test_response_includes_jobs_and_next_cursor(self, client) -> None:
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert "jobs" in body
        assert "next_cursor" in body

    def test_default_limit_is_100(self, client) -> None:
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["jobs"], list)
        assert len(body["jobs"]) <= 100

    def test_limit_query_param_is_honored(self, client) -> None:
        resp = client.get("/api/jobs?limit=5")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["jobs"]) <= 5

    def test_limit_above_max_is_rejected(self, client) -> None:
        resp = client.get("/api/jobs?limit=10000")
        # FastAPI returns 422 for Query validation failures.
        assert resp.status_code == 422

    def test_limit_below_min_is_rejected(self, client) -> None:
        resp = client.get("/api/jobs?limit=0")
        assert resp.status_code == 422

    def test_next_cursor_is_none_when_under_limit(self, client) -> None:
        # With a very large limit the result set is not exhausted, so
        # next_cursor should be None on a typical CI fixture.
        resp = client.get("/api/jobs?limit=500")
        body = resp.json()
        if len(body["jobs"]) < 500:
            assert body["next_cursor"] is None

    def test_next_cursor_is_set_when_exactly_at_limit(self, client) -> None:
        # Pick a small limit that will likely exhaust the fixture data.
        resp = client.get("/api/jobs?limit=1")
        body = resp.json()
        if len(body["jobs"]) == 1:
            assert body["next_cursor"] == body["jobs"][0]["created_at"]

    def test_cursor_pagination_is_stable(self, client) -> None:
        """The first page's next_cursor should yield the second page."""
        first = client.get("/api/jobs?limit=1")
        if first.json()["next_cursor"] is None:
            pytest.skip("Fixture has only 0 or 1 jobs; cannot test cursor")
        cursor = first.json()["next_cursor"]
        second = client.get(f"/api/jobs?limit=1&cursor={cursor}")
        assert second.status_code == 200
        second_body = second.json()
        # The second page must not include the first page's job.
        first_id = first.json()["jobs"][0]["id"]
        second_ids = {j["id"] for j in second_body["jobs"]}
        assert first_id not in second_ids

    def test_invalid_cursor_returns_200_or_422_not_500(self, client) -> None:
        resp = client.get("/api/jobs?cursor=not-a-real-cursor")
        # The implementation treats the cursor opaquely; an opaque
        # value can either filter to zero rows (200) or trigger a
        # validation error (422). It must NOT 500.
        assert resp.status_code in (200, 422)

    def test_pagination_preserves_summary_shape(self, client) -> None:
        """Each summary dict must carry the same fields as before."""
        resp = client.get("/api/jobs?limit=10")
        body = resp.json()
        if not body["jobs"]:
            pytest.skip("No jobs in fixture")
        sample = body["jobs"][0]
        expected = {
            "id",
            "name",
            "mode",
            "urls",
            "topic",
            "status",
            "created_at",
            "started_at",
            "completed_at",
            "total_records",
            "filtered_records",
            "progress_current",
            "progress_total",
            "error",
        }
        assert expected.issubset(sample.keys())
