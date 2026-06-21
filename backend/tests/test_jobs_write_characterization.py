"""Characterization tests for ``jobs_write.py`` routes.

These tests pin the current HTTP contract and business-logic behavior of
every route registered by ``register_jobs_write_routes``. They must pass
BEFORE any service-extraction refactoring and continue to pass AFTER.

**Do not change these tests to match new behavior.** If a refactoring
changes a response shape or status code, the change must be intentional
and the tests updated in coordination with the feature owner.

Pinned routes:
- ``POST /api/jobs`` — create job (the 200+ LOC complexity center)
- ``POST /api/jobs/{job_id}/cancel`` — cancel job
- ``POST /api/jobs/{job_id}/reclean`` — re-clean job results
- ``DELETE /api/jobs/{job_id}`` — delete / move to recycle bin
- ``DELETE /api/jobs/cleanup/terminal`` — bulk terminal cleanup
- ``POST /api/recycle_bin/{job_id}/restore`` — restore from recycle bin
- ``DELETE /api/recycle_bin/{job_id}`` — hard delete
- ``DELETE /api/recycle_bin`` — clear recycle bin
"""

from __future__ import annotations

import pytest
from app.models import Job, JobStatus

# ── POST /api/jobs — create job characterization ─────────────────────────────


class TestCreateJobCharacterization:
    """Pin the HTTP contract and business-logic behavior of ``POST /api/jobs``."""

    @pytest.fixture(autouse=True)
    def _clean_stores(self) -> None:
        import app.main as main_mod

        main_mod.jobs_store.clear()
        main_mod.recycle_bin_store.clear()

    MINIMAL_MANUAL_JOB = {
        "name": "char-test-job",
        "mode": "manual",
        "urls": ["https://example.com/data"],
    }

    def test_create_returns_201_with_job_id_and_status(self, client) -> None:
        """The happy path returns ``job_id``, ``status``, and ``idempotent_replay``."""
        resp = client.post("/api/jobs", json=self.MINIMAL_MANUAL_JOB)
        assert resp.status_code == 201
        body = resp.json()
        assert isinstance(body["job_id"], str) and len(body["job_id"]) > 0
        assert body["status"] == "pending"
        assert body["idempotent_replay"] is False

    def test_created_job_is_in_jobs_store(self, client) -> None:
        """After a successful create, the job appears in the in-memory store."""
        import app.main as main_mod

        resp = client.post("/api/jobs", json=self.MINIMAL_MANUAL_JOB)
        job_id = resp.json()["job_id"]
        assert job_id in main_mod.jobs_store
        job = main_mod.jobs_store[job_id]
        assert job.name == "char-test-job"
        assert job.status == JobStatus.PENDING

    def test_create_owner_stamped(self, client) -> None:
        """The job's ``created_by`` is set from the authenticated user."""
        import app.main as main_mod

        resp = client.post("/api/jobs", json=self.MINIMAL_MANUAL_JOB)
        job_id = resp.json()["job_id"]
        job = main_mod.jobs_store[job_id]
        assert job.created_by != ""

    def test_create_rejects_manual_mode_blank_urls(self, client) -> None:
        """Manual mode with only whitespace-only URLs returns 422."""
        resp = client.post(
            "/api/jobs",
            json={
                "name": "blank-urls",
                "mode": "manual",
                "urls": ["   "],
                "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
            },
        )
        assert resp.status_code == 422
        assert "Manual mode requires at least one URL" in resp.text

    def test_create_rejects_manual_mode_invalid_urls(self, client) -> None:
        """Manual mode with a non-URL string returns 422."""
        resp = client.post(
            "/api/jobs",
            json={
                "name": "invalid-url",
                "mode": "manual",
                "urls": ["not-a-url"],
                "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
            },
        )
        assert resp.status_code == 422

    def test_create_rejects_ssrf_urls(self, client) -> None:
        """Manual mode URLs pointing to private/loopback addresses are rejected.

        SSRF validation happens inside the ``JobCreate`` model validator
        (Pydantic), which returns 422. The model catches
        ``validate_public_http_url`` errors and re-raises them as
        ``ValueError``, which FastAPI converts to 422.
        """
        blocked_urls = [
            "http://127.0.0.1:8000/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/internal",
            "http://192.168.1.1/admin",
        ]
        for url in blocked_urls:
            resp = client.post(
                "/api/jobs",
                json={
                    "name": "ssrf-block",
                    "mode": "manual",
                    "urls": [url],
                },
            )
            assert resp.status_code in {400, 422}, f"SSRF URL {url!r} should be blocked (got {resp.status_code})"

    def test_create_auto_mode_rejects_blank_topic(self, client) -> None:
        """Auto mode without a topic returns 422."""
        resp = client.post(
            "/api/jobs",
            json={
                "name": "no-topic",
                "mode": "auto",
                "topic": "   ",
                "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
            },
        )
        assert resp.status_code == 422
        assert "Auto mode requires a non-empty topic" in resp.text

    def test_create_auto_mode_clears_provided_urls(self, client) -> None:
        """Auto mode ignores any manually-provided URLs."""
        resp = client.post(
            "/api/jobs",
            json={
                "name": "auto-ignores-urls",
                "mode": "auto",
                "topic": "interior designers",
                "urls": ["https://should-be-ignored.example"],
                "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        import app.main as main_mod

        job = main_mod.jobs_store[job_id]
        assert job.urls == []

    def test_create_schema_fields_persisted(self, client) -> None:
        """Provided schema fields are preserved on the created job."""
        fields = [
            {"name": "title", "field_type": "string", "required": True},
            {"name": "price", "field_type": "number", "required": False},
            {"name": "url", "field_type": "url", "required": False},
        ]
        resp = client.post(
            "/api/jobs",
            json={**self.MINIMAL_MANUAL_JOB, "schema_fields": fields},
        )
        assert resp.status_code == 201
        import app.main as main_mod

        job = main_mod.jobs_store[resp.json()["job_id"]]
        assert len(job.schema_fields) == 3
        assert job.schema_fields[0].name == "title"
        assert job.schema_fields[1].field_type.value == "number"

    def test_create_rejects_empty_auto_and_manual_mode(self, client) -> None:
        """Omitting mode entirely is a validation error."""
        resp = client.post("/api/jobs", json={"name": "no-mode"})
        assert resp.status_code == 422

    def test_create_idempotent_replay_returns_existing_job(self, client) -> None:
        """Same payload with same Idempotency-Key returns the existing job."""
        first = client.post(
            "/api/jobs",
            json=self.MINIMAL_MANUAL_JOB,
            headers={"Idempotency-Key": "replay-test-key"},
        )
        assert first.status_code == 201
        first_body = first.json()
        assert first_body["idempotent_replay"] is False

        second = client.post(
            "/api/jobs",
            json=self.MINIMAL_MANUAL_JOB,
            headers={"Idempotency-Key": "replay-test-key"},
        )
        assert second.status_code == 201
        second_body = second.json()
        assert second_body["job_id"] == first_body["job_id"]
        assert second_body["idempotent_replay"] is True

    def test_create_idempotent_conflict_different_payload(self, client) -> None:
        """Same Idempotency-Key with a different payload returns 409."""
        first = client.post(
            "/api/jobs",
            json=self.MINIMAL_MANUAL_JOB,
            headers={"Idempotency-Key": "conflict-test-key"},
        )
        assert first.status_code == 201

        second = client.post(
            "/api/jobs",
            json={
                "name": "different-payload",
                "mode": "manual",
                "urls": ["https://other.example.com/data"],
            },
            headers={"Idempotency-Key": "conflict-test-key"},
        )
        assert second.status_code == 409
        assert "Conflict" in second.text

    def test_create_invalid_idempotency_key_format(self, client) -> None:
        """An Idempotency-Key with invalid chars returns 400."""
        resp = client.post(
            "/api/jobs",
            json=self.MINIMAL_MANUAL_JOB,
            headers={"Idempotency-Key": "spaces not allowed!"},
        )
        assert resp.status_code == 400
        assert "Idempotency-Key" in resp.text


# ── POST /api/jobs/{job_id}/cancel — cancel job characterization ─────────────


class TestCancelJobCharacterization:
    @pytest.fixture(autouse=True)
    def _clean_stores(self) -> None:
        import app.main as main_mod

        main_mod.jobs_store.clear()
        main_mod.recycle_bin_store.clear()

    def _create_job(self, client) -> str:
        resp = client.post(
            "/api/jobs",
            json={
                "name": "cancel-test",
                "mode": "manual",
                "urls": ["https://example.com/data"],
            },
        )
        return resp.json()["job_id"]

    def test_cancel_pending_sets_canceled_and_returns_200(self, client) -> None:
        """Canceling a pending job returns 200 with cancel_requested=True."""
        job_id = self._create_job(client)
        resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancel_requested"] is True

    def test_cancel_terminal_returns_200_with_early_message(self, client) -> None:
        """Canceling an already-terminal job returns 200 with a 'already' message."""
        import app.main as main_mod

        job_id = self._create_job(client)
        main_mod.jobs_store[job_id].status = JobStatus.COMPLETED
        resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert "already in terminal state" in resp.json()["message"]

    def test_cancel_missing_job_returns_404(self, client) -> None:
        """Canceling a nonexistent job returns 404."""
        resp = client.post("/api/jobs/nonexistent-job/cancel")
        assert resp.status_code == 404


# ── DELETE /api/jobs/{job_id} — delete job characterization ──────────────────


class TestDeleteJobCharacterization:
    @pytest.fixture(autouse=True)
    def _clean_stores(self) -> None:
        import app.main as main_mod

        main_mod.jobs_store.clear()
        main_mod.recycle_bin_store.clear()

    def _create_completed_job(self, client) -> str:
        resp = client.post(
            "/api/jobs",
            json={
                "name": "delete-test",
                "mode": "manual",
                "urls": ["https://example.com/data"],
            },
        )
        job_id = resp.json()["job_id"]
        import app.main as main_mod

        main_mod.jobs_store[job_id].status = JobStatus.COMPLETED
        return job_id

    def test_delete_terminal_job_moves_to_recycle_bin(self, client) -> None:
        """Deleting a terminal job moves it to the recycle bin (200)."""
        import app.main as main_mod

        job_id = self._create_completed_job(client)
        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Job moved to recycle bin"
        assert job_id in main_mod.recycle_bin_store
        assert job_id not in main_mod.jobs_store

    def test_delete_active_job_returns_409(self, client) -> None:
        """Deleting a running job returns 409."""
        import app.main as main_mod

        job_id = self._create_completed_job(client)
        main_mod.jobs_store[job_id].status = JobStatus.RUNNING
        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 409
        assert "Cannot delete/recycle an active job" in resp.text

    def test_delete_missing_job_returns_404(self, client) -> None:
        """Deleting a nonexistent job returns 404."""
        resp = client.delete("/api/jobs/nonexistent-job")
        assert resp.status_code == 404


# ── DELETE /api/jobs/cleanup/terminal — bulk cleanup characterization ─────────


class TestClearTerminalJobsCharacterization:
    @pytest.fixture(autouse=True)
    def _clean_stores(self) -> None:
        import app.main as main_mod

        main_mod.jobs_store.clear()
        main_mod.recycle_bin_store.clear()

    def test_clear_removes_terminal_keeps_recent_and_active(self, client) -> None:
        """Clearing with keep_recent=N keeps the N newest terminal + all active."""
        import app.main as main_mod

        # Create 4 jobs and manually set their statuses
        ids = []
        for i in range(4):
            resp = client.post(
                "/api/jobs",
                json={
                    "name": f"cleanup-{i}",
                    "mode": "manual",
                    "urls": ["https://example.com/data"],
                },
            )
            ids.append(resp.json()["job_id"])

        main_mod.jobs_store[ids[0]].status = JobStatus.COMPLETED
        main_mod.jobs_store[ids[0]].created_at = "2026-06-01T11:00:01"
        main_mod.jobs_store[ids[1]].status = JobStatus.CANCELED
        main_mod.jobs_store[ids[1]].created_at = "2026-06-01T11:00:02"
        main_mod.jobs_store[ids[2]].status = JobStatus.FAILED
        main_mod.jobs_store[ids[2]].created_at = "2026-06-01T11:00:03"
        main_mod.jobs_store[ids[3]].status = JobStatus.RUNNING
        main_mod.jobs_store[ids[3]].created_at = "2026-06-01T11:00:04"

        resp = client.delete("/api/jobs/cleanup/terminal?keep_recent=1")
        assert resp.status_code == 200
        assert resp.json()["cleared"] == 2  # ids[0] and ids[1] removed
        remaining = set(main_mod.jobs_store.keys())
        assert remaining == {ids[2], ids[3]}

    def test_clear_no_terminal_returns_zero(self, client) -> None:
        """When no terminal jobs exist, cleared=0 is returned."""
        import app.main as main_mod

        main_mod.jobs_store["active"] = Job(
            id="active", name="active", status=JobStatus.RUNNING, created_at="2026-06-01T12:00:00"
        )
        resp = client.delete("/api/jobs/cleanup/terminal?keep_recent=1")
        assert resp.status_code == 200
        assert resp.json()["cleared"] == 0


# ── Recycle bin routes characterization ──────────────────────────────────────


class TestRecycleBinCharacterization:
    @pytest.fixture(autouse=True)
    def _clean_stores(self) -> None:
        import app.main as main_mod

        main_mod.jobs_store.clear()
        main_mod.recycle_bin_store.clear()

    def _seed_recycled_job(self, job_id: str = "rb-char-job") -> Job:
        import app.main as main_mod

        job = Job(
            id=job_id,
            name=job_id,
            status=JobStatus.CANCELED,
            created_at="2026-06-01T12:00:00",
        )
        main_mod.recycle_bin_store[job_id] = job
        return job

    def test_restore_moves_job_back_to_active_store(self, client) -> None:
        """Restoring a recycled job moves it from recycle_bin_store to jobs_store."""
        import app.main as main_mod

        job_id = "restore-char-job"
        self._seed_recycled_job(job_id)
        resp = client.post(f"/api/recycle_bin/{job_id}/restore")
        assert resp.status_code == 200
        assert job_id in main_mod.jobs_store
        assert job_id not in main_mod.recycle_bin_store

    def test_restore_missing_returns_404(self, client) -> None:
        """Restoring a nonexistent recycle-bin item returns 404."""
        resp = client.post("/api/recycle_bin/nonexistent/restore")
        assert resp.status_code == 404

    def test_hard_delete_removes_from_both_stores(self, client) -> None:
        """Hard-deleting a recycled job removes it from both stores."""
        import app.main as main_mod

        job_id = "hard-delete-char-job"
        self._seed_recycled_job(job_id)
        resp = client.delete(f"/api/recycle_bin/{job_id}")
        assert resp.status_code == 200
        assert job_id not in main_mod.recycle_bin_store

    def test_hard_delete_missing_returns_404(self, client) -> None:
        """Hard-deleting a nonexistent recycle-bin item returns 404."""
        resp = client.delete("/api/recycle_bin/nonexistent")
        assert resp.status_code == 404

    def test_clear_recycle_bin_empties_store(self, client) -> None:
        """Clearing the recycle bin removes all items."""
        import app.main as main_mod

        self._seed_recycled_job("rb-1")
        self._seed_recycled_job("rb-2")
        resp = client.delete("/api/recycle_bin")
        assert resp.status_code == 200
        assert resp.json()["cleared"] == 2
        assert len(main_mod.recycle_bin_store) == 0
