"""Tests for extraction templates CRUD (Feat 12)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_template(client: TestClient, name: str = "test-template") -> str:
    resp = client.post(
        "/api/templates",
        json={
            "name": name,
            "config": {"hydration_wait_ms": 2000},
            "schema_fields": [{"name": "title", "field_type": "string"}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_create_template(client: TestClient) -> None:
    resp = client.post(
        "/api/templates",
        json={
            "name": "my-template",
            "config": {"hydration_wait_ms": 3000, "scroll_attempts": 5},
            "schema_fields": [{"name": "price", "field_type": "float"}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-template"
    assert body["config"]["hydration_wait_ms"] == 3000


def test_create_duplicate_template_returns_409(client: TestClient) -> None:
    resp = client.post(
        "/api/templates",
        json={"id": "dup-id-409", "name": "dup", "config": {}},
    )
    assert resp.status_code == 201
    resp2 = client.post(
        "/api/templates",
        json={"id": "dup-id-409", "name": "dup", "config": {}},
    )
    assert resp2.status_code == 409


def test_list_templates(client: TestClient) -> None:
    _create_template(client, "t1")
    _create_template(client, "t2")
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_template(client: TestClient) -> None:
    tid = _create_template(client, "get-me")
    resp = client.get(f"/api/templates/{tid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-me"


def test_get_template_not_found(client: TestClient) -> None:
    resp = client.get("/api/templates/non-existent")
    assert resp.status_code == 404


def test_patch_template(client: TestClient) -> None:
    tid = _create_template(client, "patch-me")
    resp = client.patch(f"/api/templates/{tid}", json={"name": "patched-name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "patched-name"


def test_patch_template_not_found(client: TestClient) -> None:
    resp = client.patch("/api/templates/non-existent", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_template(client: TestClient) -> None:
    tid = _create_template(client, "delete-me")
    resp = client.delete(f"/api/templates/{tid}")
    assert resp.status_code == 204


def test_delete_template_not_found(client: TestClient) -> None:
    resp = client.delete("/api/templates/ghost")
    assert resp.status_code == 404
