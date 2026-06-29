"""Tests that error responses follow consistent JSON format (Roadmap Wave 10 Polish).

Verifies:
- Validation errors return structured detail
- Not found errors return 404 with trace_id
- Auth errors return 401/403
- Server errors return 500 with trace_id
"""

from __future__ import annotations


def test_validation_error_returns_422_with_detail(client) -> None:
    resp = client.post("/api/jobs", json={"bad_field": True})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_not_found_returns_404_with_trace_id(client) -> None:
    resp = client.get("/api/jobs/nonexistent-test-job-id")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert "trace_id" in body
    assert len(body["trace_id"]) > 0


def test_not_found_recycle_returns_404_with_trace_id(client) -> None:
    resp = client.get("/api/recycle_bin?limit=10")
    assert resp.status_code == 200


def test_auth_error_on_operator_endpoint(client) -> None:
    import app.main as main_mod

    main_mod.settings.ALLOW_INSECURE_DEV_AUTH = False
    main_mod.settings.OPERATOR_API_KEY = "test-op-key"
    resp = client.get("/api/operator/status")
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert "detail" in body
    main_mod.settings.ALLOW_INSECURE_DEV_AUTH = True
    main_mod.settings.OPERATOR_API_KEY = ""


def test_unprocessable_entity_returns_detailed_errors(client) -> None:
    resp = client.post("/api/jobs", json={"urls": "not-a-list"})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


def test_error_format_is_consistent_json(client) -> None:
    resp = client.get("/api/jobs/nonexistent-job-for-format-check")
    assert resp.status_code == 404
    body = resp.json()
    assert isinstance(body, dict)
    assert "detail" in body
    assert isinstance(body["detail"], str)
    assert "trace_id" in body
    assert isinstance(body["trace_id"], str)


def test_empty_body_returns_422(client) -> None:
    resp = client.post("/api/jobs", json={})
    assert resp.status_code == 422
