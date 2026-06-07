def test_metrics_endpoint_unauthenticated_when_token_set(client, monkeypatch) -> None:
    """When METRICS_TOKEN is set, requests without it should get 403."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "test-token-123")
    r = client.get("/metrics")
    assert r.status_code == 403
    assert "metrics token" in r.text.lower()


def test_metrics_endpoint_authenticated_with_bearer(client, monkeypatch) -> None:
    """Bearer token auth should work."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "test-token-123")
    r = client.get("/metrics", headers={"Authorization": "Bearer test-token-123"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_authenticated_with_x_api_key(client, monkeypatch) -> None:
    """X-API-Key header should also work for metrics auth."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "test-token-123")
    r = client.get("/metrics", headers={"X-API-Key": "test-token-123"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_content(client) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")

    text = r.text
    # Core job metrics
    assert "dataforge_jobs_total" in text
    assert "dataforge_recycle_bin_total" in text
    assert "dataforge_backend_collection_ok" in text
    assert "dataforge_queue_collection_ok" in text
    assert "dataforge_metrics_collection_error_total" in text

    # Worker failure counter metric is NOT present if no failures recorded yet
    # (test_metrics_worker_failure_counters tests the actual failure export)

    # Backend health check latency histogram is only present if recorded
    # (test_metrics_health_check_latency tests the actual latency export)


def test_metrics_worker_failure_counters(client, monkeypatch) -> None:
    """Worker failure counters should be exported when failures exist."""
    from app.metrics_collector import record_worker_failure, reset_for_testing

    reset_for_testing()

    # Simulate worker failures
    record_worker_failure("scrape_job")
    record_worker_failure("scrape_job")
    record_worker_failure("export_task")

    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text

    # Check failure counters are present
    assert 'dataforge_worker_failures_total{task_type="scrape_job"} 2' in text
    assert 'dataforge_worker_failures_total{task_type="export_task"} 1' in text

    reset_for_testing()


def test_metrics_request_latency_tracking(client, monkeypatch) -> None:
    """After making an API request, the latency histogram should capture it."""
    from app.metrics_collector import reset_for_testing

    reset_for_testing()

    # Make a request to an API endpoint to trigger latency tracking
    r = client.get("/health")
    assert r.status_code == 200

    # Now check metrics for the histogram
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text

    # The histogram should be present (may have 0 observations if no request latencies)
    assert "dataforge_request_duration_seconds" in text


def test_metrics_health_check_latency(client, monkeypatch) -> None:
    """Health check latency should be recorded when /ready is called."""
    from app.metrics_collector import reset_for_testing

    reset_for_testing()

    r = client.get("/ready")
    assert r.status_code == 200

    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text

    # Health check latency histogram should be present
    assert "dataforge_backend_health_check_duration_seconds" in text


def test_metrics_histograms_disabled(client, monkeypatch) -> None:
    """When METRICS_ENABLE_HISTOGRAMS=False, histograms should be absent."""
    monkeypatch.setattr("app.config.settings.METRICS_ENABLE_HISTOGRAMS", False)

    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text

    # Histogram metrics should NOT be present
    assert "dataforge_request_duration_seconds" not in text
    assert "dataforge_backend_health_check_duration_seconds" not in text


def test_metrics_wrong_bearer_token(client, monkeypatch) -> None:
    """Wrong Bearer token should return 403."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "correct-token")
    r = client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 403


def test_metrics_invalid_auth_header(client, monkeypatch) -> None:
    """A malformed or non-Bearer Authorization header should not bypass auth."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "secure-token")
    r = client.get("/metrics", headers={"Authorization": "Basic dGVzdDp0ZXN0"})
    assert r.status_code == 403


def test_metrics_worker_heartbeat_present(client, monkeypatch) -> None:
    """Worker heartbeat metrics should appear when a heartbeat has been recorded."""
    from app.storage_interface import get_job_repository, reset_repository

    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.delenv("DATAFORGE_DATABASE_URL", raising=False)
    reset_repository()

    repo = get_job_repository()
    import os as _os
    import socket as _socket

    # Record a heartbeat so the metric has data
    repo.record_worker_heartbeat("metrics-test-worker", _socket.gethostname(), _os.getpid())

    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text

    # Heartbeat metric should be present
    assert "dataforge_worker_heartbeat_alive" in text, "Worker heartbeat alive metric must appear in /metrics output"
    assert "dataforge_worker_heartbeat_age_seconds" in text, "Worker heartbeat age metric must appear in /metrics output"
    # The test worker should be marked alive (just wrote heartbeat).
    # prometheus_client sorts label keys alphabetically, so the rendered line
    # is `dataforge_worker_heartbeat_alive{hostname="<host>",worker_id="metrics-test-worker"}`.
    # Use a regex to avoid depending on the label order.
    import re

    # Accept either " 1" or " 1.0" — the integer alive value renders as
    # ``1`` in basic metrics text (no decimal point is added for ints).
    pattern = re.compile(r'dataforge_worker_heartbeat_alive\{[^}]*worker_id="metrics-test-worker"[^}]*\}\s+1(?:\.0)?\b')
    assert pattern.search(text), f"Test worker should appear as alive in heartbeat metrics. Metrics text:\n{text}"


def test_metrics_unset_token_fails_secure_in_any_production_casing(client, monkeypatch) -> None:
    """When ``METRICS_TOKEN`` is unset and ``ENV`` is set to any
    case-variant of ``production`` (``Production``, ``PRODUCTION``,
    ``  production  ``), the ``/metrics`` endpoint must 503. The check
    is intentionally case-insensitive and whitespace-trimmed so a
    copy-paste from a deploy doc doesn't silently fall through to the
    dev open behavior in production.
    """
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "")
    for env_value in ("production", "Production", "PRODUCTION", "  production  "):
        monkeypatch.setattr("app.config.settings.ENV", env_value)
        r = client.get("/metrics")
        assert r.status_code == 503, f"METRICS_TOKEN unset + ENV={env_value!r} should 503, got {r.status_code}"
        # The error message names the env var in its canonical
        # underscore form ("METRICS_TOKEN"). A substring match on the
        # env-var name (case-insensitive) is enough to confirm the
        # fail-secure path fired rather than the dev open path.
        assert "metrics_token" in r.text.lower()
