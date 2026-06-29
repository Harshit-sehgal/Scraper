"""Tests for Swagger UI playground (Roadmap Dev 6).

Verifies that /docs, /redoc, and /openapi.json endpoints
respond correctly.
"""

from __future__ import annotations


def test_docs_returns_200(client) -> None:
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_redoc_returns_200(client) -> None:
    resp = client.get("/redoc")
    assert resp.status_code == 200


def test_openapi_json_returns_valid_json(client) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert isinstance(spec, dict)
    assert "openapi" in spec
    assert "info" in spec
    assert "paths" in spec


def test_openapi_json_has_title(client) -> None:
    resp = client.get("/openapi.json")
    spec = resp.json()
    assert "DataForge" in spec["info"]["title"]


def test_openapi_json_has_version(client) -> None:
    resp = client.get("/openapi.json")
    spec = resp.json()
    assert "version" in spec["info"]


def test_openapi_json_has_api_paths(client) -> None:
    resp = client.get("/openapi.json")
    spec = resp.json()
    paths = spec.get("paths", {})
    api_paths = [p for p in paths if p.startswith("/api/")]
    assert len(api_paths) > 0


def test_openapi_json_info_is_valid(client) -> None:
    resp = client.get("/openapi.json")
    spec = resp.json()
    info = spec.get("info", {})
    assert isinstance(info.get("title"), str)
    assert isinstance(info.get("version"), str)


def test_docs_html_contains_swagger(client) -> None:
    resp = client.get("/docs")
    html = resp.text.lower()
    assert "swagger" in html or "openapi" in html or "redoc" in html
