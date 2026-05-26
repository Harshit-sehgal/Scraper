from pathlib import Path
from app import main as main_mod
from app.models import Job, JobStatus, ScrapeMode

def test_nginx_blocks_metrics_and_docs():
    """Verify that operational metrics and FastAPI docs are explicitly returned as 404 in public Nginx."""
    nginx_path = Path(__file__).resolve().parents[2] / "nginx.conf"
    assert nginx_path.exists()
    content = nginx_path.read_text()
    
    # Check that location blocks for docs/metrics return 404
    assert "location /metrics" in content
    assert "location /docs" in content
    assert "location /redoc" in content
    assert "location /openapi.json" in content
    assert "return 404;" in content

def test_clear_terminal_jobs_preserves_result_files(client, tmp_path, monkeypatch):
    """Verify that moving terminal jobs to the recycle bin does NOT delete their result files."""
    # Mock results directory to use tmp_path
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Write a dummy result file
    job_id = "test_job_preservation"
    result_file = results_dir / f"results_{job_id}.jsonl.gz"
    result_file.write_text("dummy results data")
    
    # Mock get_job_results_path to return our temp file path
    monkeypatch.setattr("app.utils.job_results_store.get_job_results_path", lambda jid: results_dir / f"results_{jid}.jsonl.gz")
    
    # Create the job and add to store
    job = Job(
        id=job_id,
        name="Test Preservation Job",
        mode=ScrapeMode.MANUAL,
        urls=["https://example.com"],
        status=JobStatus.COMPLETED,
        results_on_disk=True,
        results_file_path=str(result_file),
    )
    main_mod.jobs_store[job_id] = job
    
    # Verify file exists initially
    assert result_file.exists()
    
    # Call clear terminal jobs endpoint
    resp = client.delete("/api/jobs/cleanup/terminal?keep_recent=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared"] == 1
    
    # Verify metadata is moved to recycle bin
    assert job_id not in main_mod.jobs_store
    assert job_id in main_mod.recycle_bin_store
    
    # Crucially, the result file MUST still exist!
    assert result_file.exists(), "The result file was deleted, but it should have been preserved!"

def test_backfill_metadata_only_saves_single_job(client, monkeypatch):
    """Verify that backfill-metadata endpoint only saves the single job updated and doesn't call a global save."""
    saved_jobs = []
    
    # Mock _save_job to track what gets saved
    monkeypatch.setattr("app.routers.jobs._save_job", lambda job: saved_jobs.append(job))
    
    # Track if persist_state gets called
    persist_called = False
    def mock_persist_state(**kwargs):
        nonlocal persist_called
        persist_called = True
    monkeypatch.setattr("app.services.state.persist_state", mock_persist_state)
    
    # Mock infer_source_metadata to return a mock inferred dict
    from app import discovery
    monkeypatch.setattr(discovery, "infer_source_metadata", lambda url: {"source_type": "inferred_type", "source_trust_score": 0.85})
    
    # Seed a job with unknown source_type
    job_id = "test_backfill_job"
    job = Job(
        id=job_id,
        name="Test Backfill Job",
        mode=ScrapeMode.MANUAL,
        urls=["https://example.com"],
        status=JobStatus.COMPLETED,
        results=[{"source_url": "https://example.com/item", "source_type": "unknown"}],
    )
    main_mod.jobs_store[job_id] = job
    
    # Call backfill-metadata endpoint
    resp = client.post(f"/api/jobs/{job_id}/backfill-metadata")
    assert resp.status_code == 200
    assert resp.json()["updated"] is True
    
    # Verify that the single job was saved
    assert len(saved_jobs) == 1
    assert saved_jobs[0].id == job_id
    assert saved_jobs[0].results[0]["source_type"] == "inferred_type"
    
    # Verify that a global save or persist_state was NOT triggered to prevent concurrency risk
    assert not persist_called, "Global persist_state was called, bringing back concurrency risk!"
