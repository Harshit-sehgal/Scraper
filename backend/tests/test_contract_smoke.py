"""Contract Smoke Tests — DataForge Scraper.

These tests verify the repository's externally-visible contract BEFORE any
code fixes. They should initially FAIL for the right reasons, providing a
stable target for the remediation sequence.

See docs/PRODUCTION_READINESS.md and the deep-research audit report for
the rationale behind each test.

Key tests:
1. /openapi.json returns 200 in development mode
2. CSP report endpoint behaves according to intended contract (unauthenticated)
3. Production root payload does not advertise unavailable URLs
4. Worker healthcheck command logic is correct
"""

from __future__ import annotations

from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════════════════
# 1. OpenAPI schema test
# ═══════════════════════════════════════════════════════════════════════


def test_openapi_schema_is_valid_in_development(monkeypatch) -> None:
    """In development mode, /openapi.json must return 200.

    This test detects the PydanticUserError described in the deep-research
    audit: when POST /api/scraper/diagnostics uses ``fields: list[SchemaField]``
    directly in the endpoint signature with ``from __future__ import annotations``,
    FastAPI cannot resolve the type and raises a PydanticUserError.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")

    from app.main import create_app

    app = create_app()

    transport = httpx.ASGITransport(app=app)
    import asyncio

    async def _fetch():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.get("/openapi.json")

    response = asyncio.run(_fetch())
    assert response.status_code == 200, (
        f"/openapi.json returned {response.status_code}. "
        f"This usually means a Pydantic model/annotation issue in a route signature. "
        f"Response: {response.text[:500]}"
    )
    # Verify the response is valid JSON with expected top-level keys
    data = response.json()
    assert "openapi" in data, "/openapi.json response missing 'openapi' version field"
    assert "paths" in data, "/openapi.json response missing 'paths' field"
    assert "info" in data, "/openapi.json response missing 'info' field"


def test_openapi_schema_contains_diagnostics_endpoint(monkeypatch) -> None:
    """The diagnostics endpoint must appear in the OpenAPI schema.

    This is a regression test: after replacing the broken inline signature
    with a proper request model, the schema must correctly document
    ``POST /api/scraper/diagnostics`` with its expected parameters.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    import asyncio

    async def _fetch():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.get("/openapi.json")

    response = asyncio.run(_fetch())
    assert response.status_code == 200
    data = response.json()
    paths = data.get("paths", {})
    diag_path = "/api/scraper/diagnostics"
    assert diag_path in paths, (
        f"Missing '{diag_path}' in OpenAPI paths. If a request model was introduced, ensure it is importable and Pydantic-valid."
    )
    # Verify the POST method is documented
    post_spec = paths[diag_path].get("post", {})
    assert post_spec, f"POST operation not found for {diag_path}"
    # Verify request body is defined (not inline params)
    assert "requestBody" in post_spec, (
        f"POST {diag_path} should have a requestBody when using a proper Pydantic model. "
        "Inline parameters (url, fields, min_score) in the function signature would "
        "cause them to appear as query params instead."
    )
    request_body = post_spec["requestBody"]
    content = request_body.get("content", {})
    assert "application/json" in content, "Diagnostics endpoint must accept application/json"


# ═══════════════════════════════════════════════════════════════════════
# 2. CSP report endpoint test
# ═══════════════════════════════════════════════════════════════════════


def test_csp_violations_endpoint_returns_204_without_auth(monkeypatch) -> None:
    """POST /api/system/csp-violations must return 204 even without an API key.

    The endpoint is documented as "unauthenticated on purpose" — browsers
    sending CSP reports cannot carry API keys. If the global /api/* middleware
    blocks it, CSP telemetry is broken.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")
    # Configure API keys so the middleware is active
    monkeypatch.setattr(settings, "API_KEY", "test-key")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "test-operator-key")

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    import asyncio

    async def _post():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # Send a valid CSP report payload WITHOUT any auth header
            return await ac.post(
                "/api/system/csp-violations",
                json={"csp-report": {"violated-directive": "script-src 'self'", "blocked-uri": "http://evil.com"}},
            )

    response = asyncio.run(_post())
    assert response.status_code == 204, (
        f"CSP violations endpoint returned {response.status_code} without auth. "
        "Expected 204 (no content). If the middleware blocks it, add an exception "
        "for this path in api_key_middleware."
    )


def test_csp_violations_endpoint_accepts_malformed_reports(monkeypatch) -> None:
    """The CSP endpoint should be permissive about report format.

    Browsers may send reports in different shapes. The endpoint should
    gracefully handle missing/empty bodies with a 204.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "API_KEY", "test-key")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "test-operator-key")

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    import asyncio

    async def _post():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            # Empty body
            return await ac.post("/api/system/csp-violations", content=b"", headers={"Content-Type": "application/json"})

    response = asyncio.run(_post())
    # Should handle gracefully — 204 is the expected contract
    assert response.status_code == 204, (
        f"CSP endpoint returned {response.status_code} for empty body. It should handle gracefully with 204."
    )


# ═══════════════════════════════════════════════════════════════════════
# 3. Production root payload test
# ═══════════════════════════════════════════════════════════════════════


def test_root_payload_does_not_advertise_unavailable_urls_in_production(monkeypatch) -> None:
    """In production mode, the root endpoint must not advertise /docs or /app
    if those routes are disabled/unmounted.

    Currently, ``/`` unconditionally returns ``{"docs": "/docs", "dashboard": "/app"}``
    while ``configure_static()`` skips mounting /app in production and
    ``create_app()`` sets docs_url=None, redoc_url=None, openapi_url=None.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")

    from app.main import create_app

    app = create_app()

    # Verify docs and app are disabled
    transport = httpx.ASGITransport(app=app)
    import asyncio

    async def _check():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            root_resp = await ac.get("/")
            docs_resp = await ac.get("/docs")
            app_resp = await ac.get("/app")
            return root_resp, docs_resp, app_resp

    root_resp, docs_resp, app_resp = asyncio.run(_check())

    # Root response must NOT advertise docs/dashboard in production
    root_json = root_resp.json()
    assert "docs" not in root_json or root_json["docs"] is None, (
        f"Production root payload advertises /docs but it returns {docs_resp.status_code}. Root payload: {root_json}"
    )
    assert "dashboard" not in root_json or root_json["dashboard"] is None, (
        f"Production root payload advertises /app but it returns {app_resp.status_code}. Root payload: {root_json}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4. Worker heartbeat healthcheck tests
# ═══════════════════════════════════════════════════════════════════════


def test_worker_healthcheck_script_exists() -> None:
    """The worker healthcheck script must exist at the expected path.

    Replaces the PID-based ``os.kill(pid, 0)`` approach with a DB-backed
    heartbeat check (``scripts/worker_healthcheck.py``).
    """
    hc_path = REPO_ROOT / "scripts" / "worker_healthcheck.py"
    assert hc_path.exists(), f"Worker healthcheck script not found at {hc_path}"
    content = hc_path.read_text()
    # Must import from app.storage_interface to check the DB
    assert "get_job_repository" in content, "Healthcheck script must import get_job_repository"
    assert "get_worker_health" in content, "Healthcheck script must call get_worker_health"
    # Must NOT use os.kill anymore
    assert "os.kill" not in content, "Healthcheck should not use os.kill (replaced by DB-backed heartbeat)"


def test_worker_healthcheck_docker_compose_reference() -> None:
    """Parse docker-compose.prod.yml and validate the worker healthcheck command.

    The healthcheck must reference ``scripts/worker_healthcheck.py`` (the
    DB-backed heartbeat check) rather than an inline ``os.kill`` expression.
    """
    import yaml

    compose_path = REPO_ROOT / "docker-compose.prod.yml"
    assert compose_path.exists(), f"docker-compose.prod.yml not found at {compose_path}"

    with open(compose_path) as f:
        config = yaml.safe_load(f)

    worker = config.get("services", {}).get("worker", {})
    healthcheck = worker.get("healthcheck", {})
    test_cmd = healthcheck.get("test", [])

    assert isinstance(test_cmd, list), "Healthcheck test must be a list (CMD form)"
    assert len(test_cmd) >= 3, f"Healthcheck test too short: {test_cmd}"

    # Must reference the DB-backed healthcheck script
    script_path = test_cmd[-1] if test_cmd else ""
    assert "worker_healthcheck.py" in script_path, f"Healthcheck must reference scripts/worker_healthcheck.py, got: {test_cmd}"
    # Must NOT contain os.kill
    assert "os.kill" not in " ".join(test_cmd), (
        "Healthcheck must not use os.kill. It has been replaced by a DB-backed heartbeat check via scripts/worker_healthcheck.py."
    )


def test_worker_heartbeat_manager_initializes_worker_id() -> None:
    """HeartbeatManager must produce a valid worker_id and start/stop cleanly."""
    import socket

    from app.worker_heartbeat import HeartbeatManager

    mgr = HeartbeatManager(interval=60.0, ttl=120.0)
    assert mgr.worker_id, "HeartbeatManager must have a non-empty worker_id"
    assert mgr.worker_id == socket.gethostname(), (
        f"worker_id should match hostname ({socket.gethostname()!r}), "
        f"got {mgr.worker_id!r}. "
        "HeartbeatManager resolves worker_id via resolve_worker_id() which "
        "returns the hostname (not hostname-PID) so the Docker healthcheck "
        "(a separate process with a different PID) can look up the same row."
    )
    assert mgr.interval == 60.0

    # Start and stop should not raise
    import asyncio

    asyncio.run(mgr.start())
    asyncio.run(mgr.stop())


def test_worker_heartbeat_can_record_and_check(monkeypatch) -> None:
    """record_worker_heartbeat and get_worker_health work end-to-end."""
    from app.storage_interface import get_job_repository, reset_repository

    # Force SQLite backend for this test
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.delenv("DATAFORGE_DATABASE_URL", raising=False)
    reset_repository()

    repo = get_job_repository()
    worker_id = "test-worker-123"

    # Wipe any stale heartbeat row that may persist in the shared on-disk
    # SQLite database from a prior test (reset_repository() only clears the
    # Python-level repo singleton, not the database file itself).
    from app.job_store import _DB_LOCK, _get_connection

    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "DELETE FROM worker_heartbeats WHERE worker_id = ?",
                (worker_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # Initially, no heartbeat → not alive
    health = repo.get_worker_health(worker_id, ttl_seconds=60)
    assert not health["alive"], "Worker with no heartbeat should not be alive"
    assert health["last_heartbeat"] is None

    # Record a heartbeat
    import os as _os
    import socket as _socket

    repo.record_worker_heartbeat(worker_id, _socket.gethostname(), _os.getpid())

    # Now should be alive
    health = repo.get_worker_health(worker_id, ttl_seconds=60)
    assert health["alive"], "Worker with recent heartbeat should be alive"
    assert health["last_heartbeat"] is not None
    assert health["hostname"] == _socket.gethostname()
    assert health["pid"] == _os.getpid()

    # get_all_worker_healths should include this worker
    all_healths = repo.get_all_worker_healths(ttl_seconds=60)
    assert any(h["worker_id"] == worker_id for h in all_healths), "get_all_worker_healths must include the recorded worker"

    reset_repository()


def test_worker_heartbeat_expires_after_ttl(monkeypatch) -> None:
    """A heartbeat older than ttl_seconds should report alive=False.

    Uses a tiny TTL and manually-sets an old heartbeat timestamp to
    avoid actually waiting for expiry.
    """
    from app.storage_interface import get_job_repository, reset_repository

    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.delenv("DATAFORGE_DATABASE_URL", raising=False)
    reset_repository()

    repo = get_job_repository()
    worker_id = "expired-worker"

    # Record a normal heartbeat first
    import os as _os
    import socket as _socket

    repo.record_worker_heartbeat(worker_id, _socket.gethostname(), _os.getpid())

    # Check with very short TTL — should be alive
    health = repo.get_worker_health(worker_id, ttl_seconds=0)
    # TTL of 0 means the heartbeat must be *now*; our heartbeat was just
    # written so it should be alive. But if any time has passed, it may
    # not be. We just verify it works without error.
    assert "alive" in health

    # Manually write an old heartbeat to simulate expiry
    import datetime

    old_time = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
    # Direct DB manipulation
    if getattr(repo, "backend", "") == "sqlite":
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute(
                    "UPDATE worker_heartbeats SET last_heartbeat = ? WHERE worker_id = ?",
                    (old_time, worker_id),
                )
                conn.commit()
            finally:
                conn.close()

    # Now check with a reasonable TTL — should be expired
    health = repo.get_worker_health(worker_id, ttl_seconds=30)
    assert not health["alive"], "Old heartbeat should report not alive"

    reset_repository()


# ═══════════════════════════════════════════════════════════════════════
# 5. FastAPI metadata consistency
# ═══════════════════════════════════════════════════════════════════════


def test_fastapi_metadata_license_is_mit(monkeypatch) -> None:
    """The FastAPI license metadata must be MIT, matching the actual LICENSE file.

    The LICENSE file on disk says MIT. The FastAPI metadata must match.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")

    # Verify LICENSE file content
    license_path = REPO_ROOT / "LICENSE"
    assert license_path.exists()
    license_text = license_path.read_text()
    assert "MIT" in license_text or "Permission is hereby granted" in license_text, "LICENSE file does not appear to be MIT"

    import asyncio

    import httpx
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async def _fetch():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.get("/openapi.json")

    response = asyncio.run(_fetch())
    assert response.status_code == 200
    data = response.json()
    info = data.get("info", {})
    license_info = info.get("license", {})

    assert license_info.get("name") == "MIT", (
        f"FastAPI license is '{license_info.get('name')}', expected 'MIT'. "
        "The LICENSE file is MIT, so the FastAPI metadata must match."
    )


def test_fastapi_metadata_version_consistent_with_pyproject(monkeypatch) -> None:
    """The FastAPI version metadata should be consistent with pyproject.toml.

    pyproject.toml says version = "0.1.0", but FastAPI metadata says "2.0.0".
    For a pre-production project, these should align.
    """
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.exists()

    # Parse pyproject.toml for version
    import tomllib

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    pyproject_version = pyproject.get("project", {}).get("version", "")

    from app.config import settings

    monkeypatch.setattr(settings, "ENV", "development")

    import asyncio

    import httpx
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async def _fetch():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.get("/openapi.json")

    response = asyncio.run(_fetch())
    assert response.status_code == 200
    data = response.json()
    api_version = data.get("info", {}).get("version", "")

    assert api_version == pyproject_version, (
        f"FastAPI version '{api_version}' does not match pyproject.toml version '{pyproject_version}'. "
        "These should be consistent."
    )
