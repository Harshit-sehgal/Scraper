"""API tests for result search/filter/sort (Feat 25)."""

from __future__ import annotations

import app.main as main_mod
from fastapi.testclient import TestClient


def _create_job(client: TestClient, name: str = "search-test", results: list | None = None) -> str:
    payload = {
        "name": name,
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    if results is not None:
        main_mod.jobs_store[job_id].results = results
    return job_id


def test_results_pagination_defaults(client: TestClient) -> None:
    job_id = _create_job(client, "search-pag-defaults", results=[{"id": str(i)} for i in range(10)])
    resp = client.get(f"/api/jobs/{job_id}/results")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert "next_offset" in body


def test_results_search_by_keyword(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-keyword",
        results=[
            {"title": "Apple iPhone", "price": 999},
            {"title": "Samsung Galaxy", "price": 899},
            {"title": "Google Pixel", "price": 699},
        ],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?q=iphone")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert "Apple" in str(body["results"])


def test_results_search_no_match(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-nomatch",
        results=[{"title": "Alpha"}, {"title": "Beta"}],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?q=zzzznonexistent")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_results_field_filter(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-field",
        results=[
            {"name": "A", "price": 10},
            {"name": "B", "rating": 4.5},
            {"name": "C", "price": 20},
        ],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?field=price")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_results_sort_asc(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-sort-asc",
        results=[
            {"name": "Charlie", "score": 30},
            {"name": "Alpha", "score": 10},
            {"name": "Bravo", "score": 20},
        ],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?sort_by=name&sort_order=asc")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["results"]]
    assert names == ["Alpha", "Bravo", "Charlie"]


def test_results_sort_desc(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-sort-desc",
        results=[
            {"name": "Charlie", "score": 30},
            {"name": "Alpha", "score": 10},
            {"name": "Bravo", "score": 20},
        ],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?sort_by=name&sort_order=desc")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["results"]]
    assert names == ["Charlie", "Bravo", "Alpha"]


def test_results_search_and_sort(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-mixed",
        results=[
            {"name": "Delta", "group": "A"},
            {"name": "Charlie", "group": "A"},
            {"name": "Bravo", "group": "B"},
            {"name": "Alpha", "group": "A"},
        ],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?q=lta&sort_by=name&sort_order=asc")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()["results"]]
    assert names == ["Delta"]


def test_results_search_case_insensitive(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-case",
        results=[{"title": "Hello World"}, {"title": "Goodbye"}],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?q=hello")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_results_not_found(client: TestClient) -> None:
    resp = client.get("/api/jobs/does-not-exist/results")
    assert resp.status_code == 404


def test_results_limit_offset(client: TestClient) -> None:
    job_id = _create_job(
        client,
        "search-limit",
        results=[{"id": str(i)} for i in range(20)],
    )
    resp = client.get(f"/api/jobs/{job_id}/results?limit=5&offset=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 5
    assert body["offset"] == 10
    assert len(body["results"]) <= 5


def test_results_returns_structure(client: TestClient) -> None:
    job_id = _create_job(client, "search-struct", results=[{"x": 1}])
    resp = client.get(f"/api/jobs/{job_id}/results")
    body = resp.json()
    assert "job_id" in body
    assert "results" in body
    assert "total" in body
    assert "returned" in body
