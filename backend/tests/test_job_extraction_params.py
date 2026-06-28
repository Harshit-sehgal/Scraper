"""Unit tests for the per-job extraction-params PATCH endpoint (Feat 4 + Feat 9).

Covers:
- PATCH /api/jobs/{id}/extraction accepts hydration_wait_ms, scroll_attempts,
  max_pages, selectors_map, request_delay_ms, max_concurrent_urls.
- Plugins are optional — only the keys present in the JSON body are applied.
- Setting a key to ``null`` resets to platform default.
- Invalid values (out of range, malformed selectors) raise 422.
- Unknown job returns 404.
"""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "extraction-patch-test") -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def test_patch_extraction_hydration_and_scroll(client: TestClient) -> None:
    """PATCH ``hydration_wait_ms`` and ``scroll_attempts`` on a fresh job."""
    job_id = _create_job(client, "extraction-hydration-scroll")

    patch_payload = {"hydration_wait_ms": 4500, "scroll_attempts": 6}
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json=patch_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["hydration_wait_ms"] == 4500
    assert body["scroll_attempts"] == 6

    job = main_mod.jobs_store[job_id]
    assert job.hydration_wait_ms == 4500
    assert job.scroll_attempts == 6


def test_patch_extraction_rate_limit_fields(client: TestClient) -> None:
    """PATCH ``request_delay_ms`` and ``max_concurrent_urls`` (Feat 9)."""
    job_id = _create_job(client, "extraction-rate-limit")

    patch_payload = {"request_delay_ms": 1500, "max_concurrent_urls": 2}
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json=patch_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["request_delay_ms"] == 1500
    assert body["max_concurrent_urls"] == 2


def test_patch_extraction_partial_update_preserves_other_fields(client: TestClient) -> None:
    """PATCH with one field leaves the others untouched."""
    job_id = _create_job(client, "extraction-partial")

    # First, set hydration_wait_ms
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json={"hydration_wait_ms": 2000})
    assert resp.status_code == 200

    # Now PATCH only scroll_attempts — hydration_wait_ms should still be 2000
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json={"scroll_attempts": 4})
    assert resp.status_code == 200

    job = main_mod.jobs_store[job_id]
    assert job.hydration_wait_ms == 2000
    assert job.scroll_attempts == 4


def test_patch_extraction_null_resets_to_default(client: TestClient) -> None:
    """Setting a field to ``null`` explicitly resets it to the platform default."""
    job_id = _create_job(client, "extraction-null")

    client.patch(f"/api/jobs/{job_id}/extraction", json={"hydration_wait_ms": 3000})
    assert main_mod.jobs_store[job_id].hydration_wait_ms == 3000

    # Reset to None (platform default).
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json={"hydration_wait_ms": None})
    assert resp.status_code == 200
    assert main_mod.jobs_store[job_id].hydration_wait_ms is None


def test_patch_extraction_max_pages_and_selectors(client: TestClient) -> None:
    """PATCH ``max_pages`` and ``selectors_map`` together."""
    job_id = _create_job(client, "extraction-pages-selectors")

    patch_payload = {
        "max_pages": 25,
        "selectors_map": {
            "item_container": "div.product",
            "fields": {"title": "h2.product-title", "price": "span.price"},
        },
    }
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json=patch_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max_pages"] == 25
    assert body["selectors_map"]["item_container"] == "div.product"

    job = main_mod.jobs_store[job_id]
    assert job.max_pages == 25
    assert job.selectors_map["item_container"] == "div.product"


def test_patch_extraction_rejects_negative_scroll_count(client: TestClient) -> None:
    """scroll_attempts must satisfy ge=0; negative values raise 422."""
    job_id = _create_job(client, "extraction-invalid-scroll")
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json={"scroll_attempts": -1})
    assert resp.status_code == 422


def test_patch_extraction_rejects_excessive_max_pages(client: TestClient) -> None:
    """max_pages must satisfy le=100; larger values raise 422."""
    job_id = _create_job(client, "extraction-invalid-pages")
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json={"max_pages": 5000})
    assert resp.status_code == 422


def test_patch_extraction_rejects_oversized_selectors(client: TestClient) -> None:
    """selector value must be a string of at most 500 chars."""
    job_id = _create_job(client, "extraction-large-selector")
    huge_selector = "x" * 501
    patch_payload = {"selectors_map": {"item_container": huge_selector}}
    resp = client.patch(f"/api/jobs/{job_id}/extraction", json=patch_payload)
    assert resp.status_code == 422


def test_patch_extraction_unknown_job_returns_404(client: TestClient) -> None:
    """Patching a non-existent job returns 404."""
    resp = client.patch("/api/jobs/does-not-exist/extraction", json={"hydration_wait_ms": 1000})
    assert resp.status_code == 404


def test_create_job_with_extraction_params(client: TestClient) -> None:
    """JobCreate accepts hydration_wait_ms, scroll_attempts, request_delay_ms,
    max_concurrent_urls at creation time."""
    payload = {
        "name": "create-with-extraction-params",
        "mode": "manual",
        "urls": ["https://example.com/products"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "hydration_wait_ms": 5000,
        "scroll_attempts": 8,
        "request_delay_ms": 1000,
        "max_concurrent_urls": 2,
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    job = main_mod.jobs_store[job_id]
    assert job.hydration_wait_ms == 5000
    assert job.scroll_attempts == 8
    assert job.request_delay_ms == 1000
    assert job.max_concurrent_urls == 2


def test_create_job_rejects_out_of_range_extraction_params(client: TestClient) -> None:
    """Out-of-range params at creation time should return 422."""
    for bad_param in (
        {"hydration_wait_ms": -1},
        {"hydration_wait_ms": 999_999},
        {"scroll_attempts": 50},
        {"request_delay_ms": -100},
        {"max_concurrent_urls": 0},
        {"max_concurrent_urls": 100},
    ):
        payload = {
            "name": "create-bad-extraction",
            "mode": "manual",
            "urls": ["https://example.com/products"],
            "schema_fields": [{"name": "title", "field_type": "string"}],
            **bad_param,
        }
        resp = client.post("/api/jobs", json=payload)
        assert resp.status_code == 422, f"{bad_param} should be rejected but got {resp.status_code}"
