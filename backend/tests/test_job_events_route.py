"""Contract tests for ``GET /api/jobs/{job_id}/events``.

The events route is a thin projection over ``Job.logs`` plus a synthetic
status event. We seed an in-memory job directly to avoid the API-key
+ scheduler paths in the shared ``client`` fixture.
"""

from app.models import Job, JobStatus, LogEntry, ScrapeMode


def _seed_job(jobs_store, job_id: str = "evt-test-1") -> Job:
    job = Job(
        id=job_id,
        name="events-test",
        mode=ScrapeMode.MANUAL,
        urls=["https://example.com"],
        topic="test",
        status=JobStatus.RUNNING,
    )
    # Add some lifecycle entries.
    job.logs.append(
        LogEntry(
            timestamp="2026-01-01T00:00:00+00:00",
            message="started",
            level="info",
        )
    )
    jobs_store[job_id] = job
    return job


def test_unknown_job_returns_404(client) -> None:
    resp = client.get("/api/jobs/no-such-job/events")
    assert resp.status_code == 404


def test_event_payload_shape(client) -> None:
    from app.main import jobs_store

    _seed_job(jobs_store)
    resp = client.get("/api/jobs/evt-test-1/events")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("job_id", "events", "total", "limit", "offset"):
        assert key in body
    assert body["job_id"] == "evt-test-1"
    assert isinstance(body["events"], list)
    # At least the synthetic status event should be present.
    statuses = [e["message"] for e in body["events"] if e["message"].startswith("status:")]
    assert any("running" in s for s in statuses)


def test_level_filter(client) -> None:
    from app.main import jobs_store
    from app.models import LogEntry

    job = _seed_job(jobs_store, "evt-test-2")
    job.logs.append(LogEntry(timestamp="2026-01-01T00:00:01+00:00", message="oops", level="error"))
    resp = client.get("/api/jobs/evt-test-2/events?level=err")
    assert resp.status_code == 200
    body = resp.json()
    for ev in body["events"]:
        assert ev["level"].lower().startswith("err")


def test_pagination(client) -> None:
    from app.main import jobs_store

    _seed_job(jobs_store, "evt-test-3")
    resp = client.get("/api/jobs/evt-test-3/events?limit=1&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["events"]) <= 1
