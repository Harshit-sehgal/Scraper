"""Job/API-level E2E integration test.

Submits a session-bound URL to the public jobs REST API, executes it with the real
worker flow, and verifies the final results utilize the network_payload source
with safe, token-free provenance.
"""

import sys
from pathlib import Path

# Ensure backend and scripts are in sys.path BEFORE any project imports
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _PROJECT_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import http.server
import json
import threading
import urllib.parse

import pytest
from app.main import app as main_app
from app.models import JobStatus
from app.storage_interface import get_job_repository, reset_repository
from app.worker_queue import get_worker_queue, reset_worker_queue

from scripts.run_worker import scrape_job_handler

pytest.importorskip("playwright")


# ── Mock HTTP Server for E2E ─────────────────────────────────────────

PIPELINE_HTML = """<!DOCTYPE html>
<html><head><title>E2E pipeline Search Results</title></head><body>
<div id="results">Loading...</div>
<script>
  fetch('/api/pipeline_results')
    .then(r => r.json())
    .then(data => {
       console.log("Fetched api results");
    });
</script>
</body></html>"""

PIPELINE_JSON = json.dumps(
    {
        "results": [
            {"carrier": "E2E Pipeline Airways", "fare": 999},
            {"carrier": "E2E Route Jet", "fare": 1200},
        ],
        "session_secret_token": "highly_sensitive_browser_token_should_not_leak",
    },
)


class _E2EBrowserTestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/search/id/e2e_pipeline_token_xyz":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PIPELINE_HTML.encode())
        elif parsed.path == "/api/pipeline_results":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(PIPELINE_JSON.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def e2e_browser_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _E2EBrowserTestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ── ASGI Client Wrapper ────────────────────────────────────────────────


class LocalASGIClient:
    def __init__(self, app):
        self.app = app

    async def post(self, url: str, **kwargs):
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.request("POST", url, **kwargs)


# ── E2E Test Flow ──────────────────────────────────────────────────────


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_job_api_network_payload_extraction(e2e_browser_server, tmp_path, monkeypatch) -> None:
    """
    Submits a mock session-bound URL to the public jobs REST API,
    runs the worker, and asserts the results have correct provenance and no leaked secrets.
    """
    # 1. Bypass local loopback URL validation for E2E testing
    from app import html_utils, url_safety

    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "true")
    monkeypatch.setattr(url_safety, "validate_public_http_url", lambda url: None)
    monkeypatch.setattr(html_utils, "_validate_url_safe", lambda url: None)
    from app.config import settings

    monkeypatch.setattr(settings, "ALLOWED_INTERNAL_HOSTS", "127.0.0.1,localhost")

    # Mock LLM insights to avoid external API calls
    async def mock_generate_data_insight(results):
        return "Mock insight for E2E test."

    monkeypatch.setattr("app.scraper.generate_data_insight", mock_generate_data_insight)

    # Enable worker queue
    monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

    # 2. Configure temp state databases
    from app.job_store import reset_job_store_for_tests

    db_file = tmp_path / "test_e2e_jobs.db"
    state_file = db_file.with_suffix(".json")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
    reset_job_store_for_tests()

    reset_repository()
    from app.main import jobs_store, recycle_bin_store

    jobs_store.clear()
    recycle_bin_store.clear()

    # 3. Setup temporary worker queue
    reset_worker_queue()
    queue = get_worker_queue(db_path=tmp_path / "test_e2e_queue.db")
    queue.register_handler("scrape_job", scrape_job_handler)

    client = LocalASGIClient(main_app)

    # 4. Submit Job via REST API
    target_url = f"{e2e_browser_server}/search/id/e2e_pipeline_token_xyz"
    from app.crawl_policy import get_crawl_policy

    crawl_policy = get_crawl_policy()
    crawl_policy.reset_domain(target_url)
    monkeypatch.setattr(crawl_policy, "_default_delay", 0.0)
    monkeypatch.setattr(crawl_policy, "_respect_robots", False)

    schema = [
        {"name": "airline", "field_type": "string", "required": False},
        {"name": "price", "field_type": "currency", "required": False},
    ]

    response = await client.post(
        "/api/jobs",
        json={
            "name": "E2E REST Job Extraction Test",
            "mode": "manual",
            "urls": [target_url],
            "schema_fields": schema,
        },
    )

    assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
    job_id = response.json().get("job_id")
    assert job_id is not None

    # 5. Verify Job enqueued
    status = queue.get_status()
    assert status["pending"] >= 1

    # 6. Dequeue and run worker execution
    task = await queue.dequeue(timeout=5.0)
    assert task is not None
    assert task.payload.get("job_id") == job_id

    # Run the actual scrape job worker handler
    result = await scrape_job_handler(task)
    assert result is not None
    assert result["job_id"] == job_id
    assert result["status"] == "completed"

    # Complete the task
    await queue.complete(task.id, {"result": "ok"})

    # 7. Load results from Repository
    repo = get_job_repository()
    loaded_jobs, _, _ = repo.load_all()
    assert job_id in loaded_jobs
    job = loaded_jobs[job_id]

    assert job.status == JobStatus.COMPLETED
    assert job.total_records == 2

    # Assert record properties and provenance correctness
    records = job.results
    assert len(records) == 2
    assert records[0]["airline"] == "E2E Pipeline Airways"
    assert records[0]["price"] == 999

    # Verify that metadata source is 'network_payload'
    assert records[0]["_extraction_source"] == "network_payload"
    assert records[0]["_extraction_method"] == "network_payload"

    provenance = records[0]["_extraction_provenance"]
    assert "fields" in provenance
    assert provenance["fields"]["airline"] == "$.results[*].carrier"
    assert provenance["fields"]["price"] == "$.results[*].fare"

    # Verify secrets are NOT leaked anywhere in records
    serialized = json.dumps(records).lower()
    for secret in ("highly_sensitive", "should_not_leak", "session_secret_token"):
        assert secret not in serialized, f"Secret leaked in final records: {secret}"

    # Cleanup
    reset_worker_queue()
    reset_job_store_for_tests()
    jobs_store.clear()
    recycle_bin_store.clear()
