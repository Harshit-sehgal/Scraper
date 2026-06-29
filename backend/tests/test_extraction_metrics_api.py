"""API tests for the extraction metrics / stats endpoint (Feat 22)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_scraper_stats_endpoint_returns_expected_shape(client: TestClient) -> None:
    """GET /api/scraper/stats returns ScraperStatsResponse shape."""
    resp = client.get("/api/scraper/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "confidence_histogram" in body
    assert "recent_latency_avg" in body
    assert "recent_success_rate" in body
    assert isinstance(body["confidence_histogram"], list)
    assert isinstance(body["recent_latency_avg"], float)
    assert isinstance(body["recent_success_rate"], float)


def test_scraper_stats_confidence_histogram_structure(client: TestClient) -> None:
    """Each entry in confidence_histogram should be a 2-element list."""
    resp = client.get("/api/scraper/stats")
    assert resp.status_code == 200
    for entry in resp.json()["confidence_histogram"]:
        assert isinstance(entry, list)
        assert len(entry) == 2


def test_scraper_stats_latency_avg_is_non_negative(client: TestClient) -> None:
    resp = client.get("/api/scraper/stats")
    assert resp.json()["recent_latency_avg"] >= 0


def test_scraper_stats_success_rate_in_range(client: TestClient) -> None:
    resp = client.get("/api/scraper/stats")
    rate = resp.json()["recent_success_rate"]
    assert 0.0 <= rate <= 1.0


def test_scraper_stats_default_success_rate_when_no_data(client: TestClient) -> None:
    """When no telemetry data, success rate defaults to 1.0."""
    from app.scrape_telemetry import get_scrape_telemetry

    get_scrape_telemetry().clear()
    resp = client.get("/api/scraper/stats")
    assert resp.json()["recent_success_rate"] == 1.0


def test_scraper_stats_default_latency_when_no_data(client: TestClient) -> None:
    from app.scrape_telemetry import get_scrape_telemetry

    get_scrape_telemetry().clear()
    resp = client.get("/api/scraper/stats")
    assert resp.json()["recent_latency_avg"] == 0


def test_scraper_config_endpoint_returns_config(client: TestClient) -> None:
    resp = client.get("/api/scraper/config")
    assert resp.status_code == 200
    assert "playwright_timeout" in resp.json()
    assert "request_timeout" in resp.json()


def test_scraper_browser_endpoint_returns_metrics(client: TestClient) -> None:
    resp = client.get("/api/scraper/browser")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_scraper_telemetry_endpoint_returns_list(client: TestClient) -> None:
    resp = client.get("/api/scraper/telemetry?n=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_clear_telemetry_endpoint(client: TestClient) -> None:
    resp = client.delete("/api/scraper/telemetry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
