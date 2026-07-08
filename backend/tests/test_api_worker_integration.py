"""API / Worker integration tests.

Verifies:
- API creates job and enqueues when DATAFORGE_WORKER_QUEUE=true
- Worker picks queued job and updates repository
- Worker preserves recycle_bin during full save

These tests use a temp SQLite queue DB and mocked scraping to avoid
real browser/network dependencies.
"""

import asyncio
import os
from pathlib import Path

import httpx
import pytest

from app.models import Job, JobStatus
from app.storage_interface import (
    SQLiteJobRepository,
    get_job_repository,
    reset_repository,
)


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

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset repository and in-memory stores between tests."""
    reset_repository()
    from app.main import jobs_store, recycle_bin_store
    jobs_store.clear()
    recycle_bin_store.clear()
    yield
    reset_repository()
    jobs_store.clear()
    recycle_bin_store.clear()


@pytest.fixture()
def client(monkeypatch):
    """Create a test client with mocked run_job and background scheduling."""
    # Mock run_job to keep jobs in pending state
    async def fake_run_job(job_id: str):
        await asyncio.sleep(0.01)

    from app import main as main_mod
    monkeypatch.setattr(main_mod, "run_job", fake_run_job)
    monkeypatch.setattr(
        main_mod, "_schedule_background_task", lambda coro: None
    )
    yield LocalASGIClient(main_mod.app)


@pytest.fixture()
def tmp_queue_db(tmp_path):
    """Provide a temporary worker queue database path and reset singleton."""
    from app.worker_queue import reset_worker_queue
    reset_worker_queue()
    db_path = tmp_path / "worker_queue.db"
    yield db_path
    reset_worker_queue()


# ─────────────────────────────────────────────────────────────────────
# Phase 3 — Test 1: API creates job and enqueues when worker queue enabled
# ─────────────────────────────────────────────────────────────────────


class TestApiEnqueuesJob:
    """Verify that the API enqueues a job to the worker queue when enabled."""

    def test_job_is_enqueued_when_worker_queue_enabled(
        self, client, tmp_queue_db, monkeypatch
    ):
        """When DATAFORGE_WORKER_QUEUE=true, creating a job should enqueue it."""
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

        from app.worker_queue import get_worker_queue

        queue = get_worker_queue(db_path=tmp_queue_db)

        response = client.post(
            "/api/jobs",
            json={
                "name": "Integration Test Job",
                "mode": "manual",
                "urls": ["https://example.com"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        job_id = data["job_id"]
        assert job_id is not None

        # Verify the job is in the worker queue
        status = queue.get_status()
        assert status["pending"] >= 1, f"Expected >=1 pending tasks, got {status}"

        # Verify the queued task has the correct job_id
        next_tasks = status.get("next_tasks", [])
        task_ids = [t["id"] for t in next_tasks]
        assert job_id in task_ids, f"Job {job_id} not found in queued tasks: {task_ids}"

    def test_job_is_not_enqueued_when_worker_queue_disabled(
        self, client, tmp_queue_db, monkeypatch
    ):
        """When DATAFORGE_WORKER_QUEUE is not set, job should not be enqueued."""
        monkeypatch.delenv("DATAFORGE_WORKER_QUEUE", raising=False)

        from app.worker_queue import get_worker_queue

        queue = get_worker_queue(db_path=tmp_queue_db)

        response = client.post(
            "/api/jobs",
            json={
                "name": "Inline Test Job",
                "mode": "manual",
                "urls": ["https://example.com"],
            },
        )
        assert response.status_code == 200

        status = queue.get_status()
        assert status["pending"] == 0, (
            f"Expected 0 pending tasks with worker queue disabled, got {status['pending']}"
        )


# ─────────────────────────────────────────────────────────────────────
# Phase 3 — Test 2: Worker picks queued job and updates repository
# ─────────────────────────────────────────────────────────────────────


class TestWorkerPicksQueuedJob:
    """Verify that the worker dequeue and job execution flow works correctly."""

    def test_worker_picks_queued_job_and_updates_repo(
        self, client, tmp_queue_db, monkeypatch
    ):
        """Worker should dequeue a job, process it, and update the repository."""
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

        queue = get_worker_queue(db_path=tmp_queue_db)

        # Register a mock handler that simulates job completion
        async def mock_handler(task):
            from app.services.job_runner import run_job
            from app.config import settings
            from app.storage_interface import get_job_repository

            job_id = task.payload.get("job_id")
            repo = get_job_repository()
            jobs_store, recycle_bin_store, _ = repo.load_all()

            job = jobs_store.get(job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            await run_job(
                job_id=job_id,
                jobs_store=jobs_store,
                persist_state_fn=lambda: repo.save_all(jobs_store, recycle_bin_store),
                max_discovery_urls=settings.MAX_DISCOVERY_URLS,
                max_job_runtime_seconds=settings.MAX_JOB_RUNTIME_SECONDS,
                per_url_scrape_timeout_seconds=settings.PER_URL_TIMEOUT_SECONDS,
                ai_structuring_timeout_seconds=settings.AI_STRUCTURING_TIMEOUT_SECONDS,
                insight_timeout_seconds=settings.INSIGHT_TIMEOUT_SECONDS,
                persist_state_single_fn=lambda: repo.save_single(
                    jobs_store[job_id]
                ),
                persist_state_single_critical_fn=lambda: repo.save_single(
                    jobs_store[job_id]
                ),
            )
            return {
                "job_id": job_id,
                "status": job.status.value,
                "total_records": job.total_records,
            }

        queue.register_handler("scrape_job", mock_handler)

        # Create a job via API
        response = client.post(
            "/api/jobs",
            json={
                "name": "Worker Pickup Test",
                "mode": "manual",
                "urls": ["https://example.com"],
            },
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Dequeue and execute the task
        task = asyncio.run(queue.dequeue(timeout=2.0))
        assert task is not None, "Worker should have dequeued the task"
        assert task.payload.get("job_id") == job_id

        # Mark task as running (dequeue already does this), then execute
        from app.worker_queue import TaskStatus
        assert task.status == TaskStatus.RUNNING

        # Execute - simulate worker
        repo = get_job_repository()
        jobs_store, recycle_bin_store, _ = repo.load_all()
        assert job_id in jobs_store, f"Job {job_id} should be in the store"

        # Complete the task
        asyncio.run(queue.complete(task.id, {"result": "ok"}))

        # Verify task is gone from active queue
        status = queue.get_status()
        assert status["pending"] == 0
        assert status["running"] == 0

    def test_worker_fails_fast_without_job_id(self, tmp_queue_db, monkeypatch):
        """Worker --once mode should fail fast if DATAFORGE_JOB_ID is missing."""
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
        monkeypatch.delenv("DATAFORGE_JOB_ID", raising=False)

        # In --once mode, the worker checks for DATAFORGE_JOB_ID
        job_id = os.getenv("DATAFORGE_JOB_ID")
        assert job_id is None, "DATAFORGE_JOB_ID should not be set for this test"


class TestRealWorkerHandler:
    """Tests using the actual scripts.run_worker.scrape_job_handler."""

    def test_real_worker_handler_executes_via_api(
        self, tmp_path, monkeypatch
    ):
        """
        End-to-end test using the real scrape_job_handler from scripts/run_worker.

        Flow:
        1. Import the real scrape_job_handler from scripts.run_worker
        2. Mock scrape_url_with_recovery to return sample records
        3. Create job through API
        4. Dequeue task from WorkerQueue
        5. Execute real scrape_job_handler(task)
        6. Assert repository job reaches terminal status
        """
        # ── Ensure project root is on path for scripts.run_worker import ─
        import sys
        project_root = str(Path(__file__).resolve().parents[2])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from scripts.run_worker import scrape_job_handler

        # ── Mock scraped records ─────────────────────────────────────────
        async def mock_scrape_url_with_recovery(
            url, schema_fields, min_record_score=0.35,
            user_intent="", world_state=None, max_recovery_attempts=3,
            selectors_map=None, search_params=None,
        ):
            sample_records = [
                {
                    "name": "RealHandler Widget A",
                    "price": 9.99,
                    "source_url": url,
                    "source_type": "direct",
                    "source_trust_score": 0.95,
                },
            ]
            recovery_stats = {"recovery_attempts": 0, "recovery_actions_taken": [], "acquisition_lineage": {}}
            return sample_records, recovery_stats

        monkeypatch.setattr(
            "app.scraper_recovery_integration.scrape_url_with_recovery",
            mock_scrape_url_with_recovery,
        )
        monkeypatch.setattr(
            "app.services.job_runner.scrape_url_with_recovery",
            mock_scrape_url_with_recovery,
        )

        async def mock_generate_data_insight(results):
            return "Mock insight for worker integration test."

        monkeypatch.setattr("app.scraper.generate_data_insight", mock_generate_data_insight)

        # ── Setup: enable worker queue, point SQLite at temp path ───────
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

        from app.job_store import reset_job_store_for_tests
        from app.config import settings

        db_file = tmp_path / "test_real_handler_jobs.db"
        state_file = db_file.with_suffix(".json")
        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
        reset_job_store_for_tests()

        from app.main import jobs_store, recycle_bin_store
        jobs_store.clear()
        recycle_bin_store.clear()

        from app.worker_queue import reset_worker_queue, get_worker_queue
        reset_worker_queue()
        queue = get_worker_queue(db_path=tmp_path / "test_real_handler_queue.db")
        queue.register_handler("scrape_job", scrape_job_handler)

        from app.main import app as main_app
        client = LocalASGIClient(main_app)

        # ── Step 1: Create job via API ──────────────────────────────────
        response = client.post(
            "/api/jobs",
            json={
                "name": "Real Handler E2E",
                "mode": "manual",
                "urls": ["https://example.com/products"],
            },
        )
        assert response.status_code == 200, f"API returned {response.status_code}: {response.text}"
        job_id = response.json()["job_id"]
        assert job_id is not None

        # ── Step 2: Verify enqueued ─────────────────────────────────────
        status = queue.get_status()
        assert status["pending"] >= 1, f"Expected pending tasks, got {status}"

        # ── Step 3: Dequeue the task ────────────────────────────────────
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None, "Worker should dequeue the task"
        assert task.payload.get("job_id") == job_id

        # ── Step 4: Execute real scrape_job_handler ─────────────────────
        result = asyncio.run(scrape_job_handler(task))
        assert result is not None
        assert result["job_id"] == job_id
        assert result["status"] in ("completed", "degraded"), (
            f"Expected terminal status, got {result['status']}"
        )

        # ── Step 5: Verify repository has updated job ───────────────────
        from app.storage_interface import get_job_repository
        repo = get_job_repository()
        loaded_jobs, loaded_recycle, _ = repo.load_all()
        assert job_id in loaded_jobs, f"Job {job_id} should be in repository"
        assert loaded_jobs[job_id].status in (
            JobStatus.COMPLETED, JobStatus.DEGRADED
        ), f"Expected terminal status, got {loaded_jobs[job_id].status}"

        # Cleanup
        reset_worker_queue()
        reset_job_store_for_tests()
        jobs_store.clear()
        recycle_bin_store.clear()

    def test_real_worker_handler_missing_job_id_raises_error(self):
        """When task has no job_id, the real handler should raise ValueError."""
        import sys
        project_root = str(Path(__file__).resolve().parents[2])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from scripts.run_worker import scrape_job_handler
        from app.worker_queue import QueueTask

        # Create a task-like object without job_id
        task = QueueTask(
            task_type="scrape_job",
            payload={},
            task_id="no-job-id-task",
        )

        with pytest.raises(ValueError, match="No job_id"):
            asyncio.run(scrape_job_handler(task))


class TestWorkerPreservesRecycleBin:
    """Verify that worker full-state persistence preserves recycle_bin contents."""

    def test_worker_save_all_preserves_recycle_bin(self, tmp_path, monkeypatch):
        """save_all should preserve recycle_bin entries during full state writes."""
        from app.job_store import reset_job_store_for_tests

        # Point job store at a temp DB
        db_file = tmp_path / "test_jobs.db"
        state_file = db_file.with_suffix(".json")
        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
        from app.config import settings
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
        reset_job_store_for_tests()

        repo = SQLiteJobRepository()

        # Seed a recycle bin entry
        recycled_job = Job(
            id="recycled-job-1",
            name="Recycled Job",
            urls=["https://example.com"],
            status=JobStatus.COMPLETED,
        )
        # Add it to the recycle bin via repository
        repo.save_all({}, {recycled_job.id: recycled_job})

        # Now simulate worker saving both jobs and recycle bin
        active_job = Job(
            id="active-job-1",
            name="Active Job",
            urls=["https://example.com"],
            status=JobStatus.RUNNING,
        )
        repo.save_all({active_job.id: active_job}, {recycled_job.id: recycled_job})

        # Load back and verify both are preserved
        loaded_jobs, loaded_recycle, _ = repo.load_all()
        assert "active-job-1" in loaded_jobs
        assert "recycled-job-1" in loaded_recycle
        assert loaded_recycle["recycled-job-1"].name == "Recycled Job"

        # Now do another full save (simulating periodic worker persistence)
        repo.save_all(loaded_jobs, loaded_recycle)

        # Verify recycle bin is still intact
        _, loaded_recycle2, _ = repo.load_all()
        assert "recycled-job-1" in loaded_recycle2
        assert len(loaded_recycle2) >= 1

        reset_job_store_for_tests()

    def test_recycle_bin_survives_multiple_save_cycles(self, tmp_path, monkeypatch):
        """Multiple save_all cycles should not lose recycle_bin entries."""
        from app.job_store import reset_job_store_for_tests
        from app.config import settings

        db_file = tmp_path / "test_jobs2.db"
        state_file = db_file.with_suffix(".json")
        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
        reset_job_store_for_tests()

        repo = SQLiteJobRepository()

        # Seed recycle bin entries — accumulate in a dict to avoid
        # overwriting on each save_all call (which does DELETE + INSERT)
        recycle_store = {}
        for i in range(3):
            job = Job(
                id=f"recycled-{i}",
                name=f"Recycled {i}",
                urls=["https://example.com"],
                status=JobStatus.COMPLETED,
            )
            recycle_store[job.id] = job
        repo.save_all({}, recycle_store)

        # Three save cycles
        for cycle in range(3):
            active = Job(
                id=f"active-{cycle}",
                name=f"Active {cycle}",
                urls=["https://example.com"],
                status=JobStatus.RUNNING,
            )
            loaded_jobs, loaded_recycle, _ = repo.load_all()
            loaded_jobs[active.id] = active
            repo.save_all(loaded_jobs, loaded_recycle)

        # Verify all recycle bin entries survive
        _, final_recycle, _ = repo.load_all()
        for i in range(3):
            assert f"recycled-{i}" in final_recycle, (
                f"recycled-{i} missing after {cycle} save cycles"
            )

        reset_job_store_for_tests()
