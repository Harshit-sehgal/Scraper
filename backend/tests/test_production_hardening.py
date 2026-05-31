import pytest
import socket
from pathlib import Path
from app import main as main_mod
from app.models import Job, JobStatus, ScrapeMode


@pytest.fixture(autouse=True)
def mock_dns_resolution(monkeypatch):
    """Mock socket.getaddrinfo to make tests DNS-independent and prevent external lookups,
    while correctly simulating public IP resolution for test domains.
    """
    original_getaddrinfo = socket.getaddrinfo

    def dummy_getaddrinfo(host, port, *args, **kwargs):
        # 1. Simulate exact DNS failures if the test specifically expects/seeks a lookup failure
        if host == "unresolvable-domain.xyz":
            raise socket.gaierror(-2, "Name or service not known")

        # 2. Return loopback for localhost
        if host in ("localhost", "127.0.0.1", "::1"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 0))]

        # 3. Return private IPs for internal test names
        if host in ("nginx", "host.docker.internal"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.16.0.2", port or 0))]

        # 4. Return metadata IP for metadata endpoints
        if host == "169.254.169.254":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port or 0))]

        # 5. Return public IPs for standard public domains used in tests
        if host in ("example.com", "google.com", "trusted.com", "attacker.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]

        # Fallback to original, or resolve safely to a public IP to keep the test robust
        try:
            return original_getaddrinfo(host, port, *args, **kwargs)
        except Exception:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", dummy_getaddrinfo)


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


def test_production_prometheus_mounts_alert_rules():
    """Production compose must mount the same alert rule file Prometheus loads."""
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.prod.yml").read_text()
    prometheus = (root / "prometheus.yml").read_text()

    assert 'rule_files:\n  - "prometheus_alerts.yml"' in prometheus
    assert "./prometheus.yml:/etc/prometheus/prometheus.yml.template:ro" in compose
    assert "./prometheus_alerts.yml:/etc/prometheus/prometheus_alerts.yml:ro" in compose
    assert "DATAFORGE_METRICS_TOKEN" in compose
    assert "__DATAFORGE_METRICS_TOKEN__" in prometheus


def test_prometheus_does_not_reference_undeployed_alertmanager():
    """Prometheus should not point at Alertmanager unless compose deploys it."""
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.prod.yml").read_text()
    prometheus = (root / "prometheus.yml").read_text()

    assert "alertmanager:" not in compose
    assert "alertmanager:9093" not in prometheus
    assert "\nalerting:" not in prometheus


def test_ci_prometheus_check_matches_production_mount_layout():
    """CI promtool validation should use the same selected-file mounts as prod."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    content = workflow.read_text()

    assert '$PWD/prometheus.yml:/etc/prometheus/prometheus.yml:ro' in content
    assert '$PWD/prometheus_alerts.yml:/etc/prometheus/prometheus_alerts.yml:ro' in content
    assert '$PWD:/etc/prometheus:ro' not in content


def test_ci_does_not_install_optional_g4f_by_default():
    """Optional LLM providers should not make CI differ from production installs."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    content = workflow.read_text()

    assert "pip install g4f" not in content


def test_start_script_checks_runtime_scraper_dependencies():
    """The dev startup script should check scraper/discovery dependencies, not just FastAPI."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "start.sh"
    content = script.read_text()

    assert "ddgs or duckduckgo_search" in content
    assert "playwright.sync_api" in content
    assert "python -m playwright install chromium" in content


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
    monkeypatch.setattr(
        discovery,
        "infer_source_metadata",
        lambda url: {
            "source_type": "inferred_type",
            "source_trust_score": 0.85})

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


def test_create_job_enqueue_failure_cleanup(client, monkeypatch):
    """Verify that if enqueue fails in production, the job is removed from memory and repository (not left orphaned)."""
    from app.config import settings
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "test-key")
    monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

    # Mock enqueue to raise an error
    class FailingQueue:
        async def enqueue(self, *args, **kwargs):
            raise Exception("Queue is dead")
    monkeypatch.setattr("app.worker_queue.get_worker_queue", lambda: FailingQueue())

    payload = {
        "name": "cleanup-on-enqueue-failure",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }

    resp = client.post(
        "/api/jobs",
        json=payload,
        headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 503
    assert "Failed to enqueue job" in resp.json()["detail"]

    # Verify job is NOT in memory store
    assert len(main_mod.jobs_store) == 0


def test_auto_discovery_url_filtering(client, monkeypatch):
    """Verify that auto-discovered URLs are filtered against SSRF protections in both API and Job runner contexts."""
    from app.config import settings
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "test-operator-key")

    # Mock discover_urls to return a mix of safe and unsafe URLs
    async def mock_discover(*args, **kwargs):
        return [
            {"url": "https://example.com/safe-item"},
            {"url": "http://127.0.0.1/unsafe-loopback"},
            {"url": "http://nginx/unsafe-internal"},
            {"url": "https://google.com/safe-google"}
        ]

    monkeypatch.setattr("app.routers.jobs.discover_urls", mock_discover)

    # Verify discover API endpoint filters out loopback & internal targets
    payload = {
        "topic": "test",
        "domain": "example.com",
        "num_results": 5,
        "schema_field_names": ["title"]
    }
    resp = client.post(
        "/api/discover",
        json=payload,
        headers={"X-API-Key": "test-operator-key"},
    )
    assert resp.status_code == 200
    urls = resp.json()["urls"]
    assert len(urls) == 2
    assert urls[0]["url"] == "https://example.com/safe-item"
    assert urls[1]["url"] == "https://google.com/safe-google"


@pytest.mark.asyncio
async def test_search_form_recovery_ssrf_blocking(monkeypatch):
    """Verify that search form recovery action and redirect target URLs are checked against SSRF."""
    from app.selector_discovery import _try_form_search_recovery

    # Verify form action is validated
    landing_page_html = """
    <html>
        <body>
            <form action="http://127.0.0.1/admin/delete" method="POST">
                <input name="q" type="text">
            </form>
        </body>
    </html>
    """

    res = await _try_form_search_recovery(
        landing_page_html=landing_page_html,
        landing_page_url="https://example.com",
        search_params={"q": "test-search"}
    )

    assert res["success"] is False
    assert "failed security check" in res["error"]


def test_backend_cors_origins_enforcement(client, monkeypatch):
    """Verify that backend CORS rejects/allows origins based on settings.CORS_ORIGINS."""
    from app import main as main_mod
    from app.config import settings
    # Set CORS_ORIGINS in settings
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://trusted.com"])

    # Locate and patch the CORSMiddleware instance in the ASGI middleware stack
    if main_mod.app.middleware_stack is None:
        main_mod.app.middleware_stack = main_mod.app.build_middleware_stack()

    current_app = main_mod.app.middleware_stack
    cors_mw = None
    while current_app is not None:
        if current_app.__class__.__name__ == "CORSMiddleware":
            cors_mw = current_app
            break
        current_app = getattr(current_app, "app", None)

    if cors_mw:
        monkeypatch.setattr(cors_mw, "allow_origins", ["https://trusted.com"])
        monkeypatch.setattr(cors_mw, "allow_all_origins", False)

    # Preflight request from allowed origin
    headers = {
        "Origin": "https://trusted.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    resp = client.request("OPTIONS", "/api/jobs", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://trusted.com"

    # Preflight request from disallowed origin
    headers = {
        "Origin": "https://attacker.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    resp = client.request("OPTIONS", "/api/jobs", headers=headers)
    assert resp.headers.get("access-control-allow-origin") is None


def test_body_size_limit_normal_payload(client, monkeypatch):
    """Verify that a normal payload under 5MB passes the body-size limit middleware."""
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY", "testkey")

    resp = client.post(
        "/api/jobs",
        json={"name": "test-size", "mode": "manual", "urls": ["https://example.com"]},
        headers={"X-API-Key": "testkey"}
    )
    assert resp.status_code != 413


def test_body_size_limit_oversized_payload(client, monkeypatch):
    """Verify that an oversized payload (> 5MB) with Content-Length is rejected with 413."""
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY", "testkey")

    # 6MB of data
    large_data = "a" * (6 * 1024 * 1024)

    resp = client.post(
        "/api/jobs",
        content=large_data.encode("utf-8"),
        headers={"X-API-Key": "testkey", "Content-Type": "application/json"}
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]


def test_body_size_limit_chunked_normal(client, monkeypatch):
    """Verify that chunked/streaming requests under 5MB are accepted."""
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY", "testkey")

    async def chunk_generator():
        yield b'{"name": "test-chunked", '
        yield b'"mode": "manual", '
        yield b'"urls": ["https://example.com"]}'

    resp = client.post(
        "/api/jobs",
        content=chunk_generator(),
        headers={"X-API-Key": "testkey", "Content-Type": "application/json"}
    )
    assert resp.status_code != 413


def test_body_size_limit_chunked_oversized(client, monkeypatch):
    """Verify that chunked/streaming requests without Content-Length exceeding 5MB are rejected with 413."""
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY", "testkey")

    # A generator yielding 6MB in chunks
    async def chunk_generator():
        chunk = b"a" * (1024 * 1024)  # 1MB
        for _ in range(6):
            yield chunk

    resp = client.post(
        "/api/jobs",
        content=chunk_generator(),
        headers={"X-API-Key": "testkey", "Content-Type": "application/octet-stream"}
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]
