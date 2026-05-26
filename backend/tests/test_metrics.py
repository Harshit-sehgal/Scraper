def test_metrics_endpoint_unauthenticated_when_token_set(client, monkeypatch):
    """When METRICS_TOKEN is set, requests without it should get 403."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "test-token-123")
    r = client.get("/metrics")
    assert r.status_code == 403
    assert "metrics token" in r.text.lower()


def test_metrics_endpoint_authenticated_with_bearer(client, monkeypatch):
    """Bearer token auth should work."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "test-token-123")
    r = client.get("/metrics", headers={"Authorization": "Bearer test-token-123"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_authenticated_with_x_api_key(client, monkeypatch):
    """X-API-Key header should also work for metrics auth."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "test-token-123")
    r = client.get("/metrics", headers={"X-API-Key": "test-token-123"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_content(client):
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


def test_metrics_worker_failure_counters(client, monkeypatch):
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


def test_metrics_request_latency_tracking(client, monkeypatch):
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


def test_metrics_health_check_latency(client, monkeypatch):
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


def test_metrics_histograms_disabled(client, monkeypatch):
    """When METRICS_ENABLE_HISTOGRAMS=False, histograms should be absent."""
    monkeypatch.setattr("app.config.settings.METRICS_ENABLE_HISTOGRAMS", False)

    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text

    # Histogram metrics should NOT be present
    assert "dataforge_request_duration_seconds" not in text
    assert "dataforge_backend_health_check_duration_seconds" not in text


def test_metrics_wrong_bearer_token(client, monkeypatch):
    """Wrong Bearer token should return 403."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "correct-token")
    r = client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 403


def test_metrics_invalid_auth_header(client, monkeypatch):
    """A malformed or non-Bearer Authorization header should not bypass auth."""
    monkeypatch.setattr("app.config.settings.METRICS_TOKEN", "secure-token")
    r = client.get("/metrics", headers={"Authorization": "Basic dGVzdDp0ZXN0"})
    assert r.status_code == 403
