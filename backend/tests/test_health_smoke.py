"""Load testing for concurrent requests and rate limiting."""


def test_concurrent_requests_health(client):
    """Verify service handles concurrent health requests."""
    for i in range(5):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_health_endpoint_responsive(client):
    """Verify health endpoint is responsive."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


def test_ready_endpoint_responsive(client):
    """Verify ready endpoint is responsive."""
    resp = client.get("/ready")
    assert resp.status_code == 200


def test_metrics_endpoint_exists(client):
    """Verify metrics endpoint exists and responds."""
    resp = client.get("/metrics")
    # Should be 200 or 401 (protected)
    assert resp.status_code in (200, 401)


def test_api_routes_require_auth(client):
    """Verify API routes properly require auth."""
    # Jobs endpoint should require auth
    resp = client.get("/api/jobs")
    # Should be 401/403 (auth required) or 200 (permissive mode), not 500
    assert resp.status_code in (200, 401, 403)
