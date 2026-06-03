import pytest
from app.models import Job, JobStatus


@pytest.fixture
def seed_job_with_results():
    from app.main import jobs_store

    job = Job(
        name="test-paginated-job",
        mode="manual",
        urls=["http://example.com/item"],
        schema_fields=[{"name": "title", "field_type": "string"}],
    )
    job.results = [{"title": f"Result {i}", "source_url": "http://example.com/item", "source_type": "unknown"} for i in range(15)]
    job.status = JobStatus.COMPLETED
    jobs_store[job.id] = job

    yield job

    if job.id in jobs_store:
        del jobs_store[job.id]


def test_get_job_no_results_by_default(client, seed_job_with_results) -> None:
    job = seed_job_with_results
    r = client.get(f"/api/jobs/{job.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == []


def test_get_job_include_results_parameter(client, seed_job_with_results) -> None:
    job = seed_job_with_results
    r = client.get(f"/api/jobs/{job.id}?include_results=true")
    assert r.status_code == 200
    data = r.json()
    assert len(data["results"]) == 15
    assert data["results"][0]["title"] == "Result 0"


def test_get_job_results_pagination(client, seed_job_with_results) -> None:
    job = seed_job_with_results
    # Fetch with limit=5
    r = client.get(f"/api/jobs/{job.id}/results?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 15
    assert len(data["results"]) == 5
    assert data["limit"] == 5
    assert data["offset"] == 0
    assert data["results"][0]["title"] == "Result 0"

    # Fetch with offset=5, limit=5
    r2 = client.get(f"/api/jobs/{job.id}/results?limit=5&offset=5")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["total"] == 15
    assert len(data2["results"]) == 5
    assert data2["offset"] == 5
    assert data2["results"][0]["title"] == "Result 5"


def test_get_job_results_next_offset(client, seed_job_with_results) -> None:
    """The next_offset cursor should be present when more results exist, None on last page."""
    job = seed_job_with_results

    # Page 1: offset=0, limit=10 — next_offset should be 10
    r = client.get(f"/api/jobs/{job.id}/results?limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["next_offset"] == 10

    # Page 2: offset=10, limit=10 — next_offset should be None (last page)
    r2 = client.get(f"/api/jobs/{job.id}/results?limit=10&offset=10")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["next_offset"] is None

    # Exact boundary: offset=10, limit=5 — next_offset should be None (10+5 >= 15 total)
    r3 = client.get(f"/api/jobs/{job.id}/results?limit=5&offset=10")
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["next_offset"] is None


def test_backfill_metadata_endpoint(client, seed_job_with_results) -> None:
    job = seed_job_with_results
    r = client.post(f"/api/jobs/{job.id}/backfill-metadata")
    assert r.status_code == 200
    data = r.json()
    assert "Metadata backfilled successfully" in data["message"]
    assert data["updated"] is True

    # Fetch the job and check updated source metadata
    r_job = client.get(f"/api/jobs/{job.id}?include_results=true")
    data_job = r_job.json()
    assert data_job["results"][0]["source_type"] != "unknown"
    assert "source_trust_score" in data_job["results"][0]
