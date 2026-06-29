"""Additional tests for recycle bin operations (Roadmap Wave 10 Polish).

Covers:
- Restore from recycle bin
- Permanent delete
- List pagination
- Empty bin
- 404s for missing jobs
"""

from __future__ import annotations

from app.models import JobStatus


def _create_job_in_store(client, name: str = "recycle-test") -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "company_name", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def _move_to_recycle(client, job_id: str) -> None:
    import app.main as main_mod

    main_mod.jobs_store[job_id].status = JobStatus.COMPLETED
    resp = client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert job_id in main_mod.recycle_bin_store


class TestRecycleBinRestore:
    def test_restore_job_from_recycle(self, client) -> None:
        import app.main as main_mod

        job_id = _create_job_in_store(client)
        _move_to_recycle(client, job_id)

        resp = client.post(f"/api/recycle_bin/{job_id}/restore")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Job restored"
        assert job_id not in main_mod.recycle_bin_store
        assert job_id in main_mod.jobs_store

    def test_restore_nonexistent_returns_404(self, client) -> None:
        resp = client.post("/api/recycle_bin/nonexistent/restore")
        assert resp.status_code == 404

    def test_restore_twice_returns_404(self, client) -> None:
        job_id = _create_job_in_store(client)
        _move_to_recycle(client, job_id)
        client.post(f"/api/recycle_bin/{job_id}/restore")
        resp = client.post(f"/api/recycle_bin/{job_id}/restore")
        assert resp.status_code == 404


class TestRecycleBinPermanentDelete:
    def test_permanent_delete(self, client) -> None:
        import app.main as main_mod

        job_id = _create_job_in_store(client)
        _move_to_recycle(client, job_id)

        resp = client.delete(f"/api/recycle_bin/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Job permanently deleted"
        assert job_id not in main_mod.recycle_bin_store
        assert job_id not in main_mod.jobs_store

    def test_permanent_delete_nonexistent_returns_404(self, client) -> None:
        resp = client.delete("/api/recycle_bin/nonexistent")
        assert resp.status_code == 404

    def test_get_deleted_job_returns_404(self, client) -> None:
        job_id = _create_job_in_store(client)
        _move_to_recycle(client, job_id)
        client.delete(f"/api/recycle_bin/{job_id}")
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 404


class TestRecycleBinList:
    def test_list_empty_recycle_bin(self, client) -> None:
        resp = client.get("/api/recycle_bin")
        assert resp.status_code == 200
        body = resp.json()
        assert "jobs" in body
        assert len(body["jobs"]) == 0

    def test_list_recycle_bin_with_jobs(self, client) -> None:
        job_ids = []
        for i in range(3):
            jid = _create_job_in_store(client, f"recycle-{i}")
            _move_to_recycle(client, jid)
            job_ids.append(jid)

        resp = client.get("/api/recycle_bin")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["jobs"]) == 3
        returned_ids = {j["id"] for j in body["jobs"]}
        assert returned_ids == set(job_ids)

    def test_list_recycle_bin_returns_all_with_less_than_limit(self, client) -> None:
        for i in range(3):
            jid = _create_job_in_store(client, f"pag-recycle-{i}")
            _move_to_recycle(client, jid)

        resp = client.get("/api/recycle_bin")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["jobs"]) == 3


class TestRecycleBinClear:
    def test_clear_empty_recycle_bin(self, client) -> None:
        resp = client.delete("/api/recycle_bin")
        assert resp.status_code == 200
        body = resp.json()
        assert "cleared" in body

    def test_clear_recycle_bin_removes_all(self, client) -> None:
        import app.main as main_mod

        for i in range(3):
            jid = _create_job_in_store(client, f"clear-{i}")
            _move_to_recycle(client, jid)

        assert len(main_mod.recycle_bin_store) == 3
        resp = client.delete("/api/recycle_bin")
        assert resp.status_code == 200
        assert len(main_mod.recycle_bin_store) == 0
        body = resp.json()
        assert body["cleared"] >= 3
