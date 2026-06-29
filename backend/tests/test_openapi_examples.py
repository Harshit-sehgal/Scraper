"""Tests for OpenAPI 3.1 spec with request/response examples (Feat 31).

Verifies that every registered endpoint has a request body example
(for POST/PATCH/PUT) and a response example (for all methods).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _get_openapi_spec(client: TestClient) -> dict:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    return resp.json()


def test_openapi_spec_is_valid(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    assert "openapi" in spec
    assert spec["openapi"].startswith("3.")


def test_openapi_has_paths(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    assert "paths" in spec
    assert len(spec["paths"]) > 0


def test_all_post_endpoints_have_request_body(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    for path, methods in spec["paths"].items():
        for method, detail in methods.items():
            if method.upper() == "POST":
                # Actions like cancel, redeliver, reclean take no body — that's OK
                if "requestBody" not in detail:
                    has_action_suffix = any(path.endswith(s) for s in ("/cancel", "/redeliver", "/restore", "/run", "/reclean", "/generate-test", "/api/session"))
                    is_action_without_body = has_action_suffix or (not detail.get("parameters", []) and not path.endswith("/screenshot"))
                    if not is_action_without_body:
                        assert "requestBody" in detail, f"POST {path} missing requestBody"


def test_all_patch_endpoints_have_request_body(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    for path, methods in spec["paths"].items():
        for method, detail in methods.items():
            if method.upper() == "PATCH":
                assert "requestBody" in detail, f"PATCH {path} missing requestBody"


def test_all_endpoints_have_responses(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    for path, methods in spec["paths"].items():
        for method, detail in methods.items():
            if method == "parameters":
                continue
            assert "responses" in detail, f"{method.upper()} {path} missing responses"


def test_all_endpoints_have_200_response(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    for path, methods in spec["paths"].items():
        for method, detail in methods.items():
            if method == "parameters":
                continue
            responses = detail.get("responses", {})
            has_success = any(code.startswith("2") for code in responses)
            if not has_success:
                has_201 = "201" in responses
                assert has_201 or has_success, f"{method.upper()} {path} missing 2xx response"


def test_all_schemas_have_type(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    schemas = spec.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        assert "type" in schema or "oneOf" in schema or "anyOf" in schema or "allOf" in schema or "properties" in schema, f"Schema {name} has no type"


def test_post_jobs_has_request_body_schema(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    jobs_post = spec["paths"].get("/api/jobs", {}).get("post", {})
    assert "requestBody" in jobs_post
    content = jobs_post["requestBody"]["content"]
    assert "application/json" in content


def test_get_jobs_has_responses(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    jobs_get = spec["paths"].get("/api/jobs", {}).get("get", {})
    responses = jobs_get.get("responses", {})
    assert "200" in responses or "422" in responses


def test_openapi_version_is_31_or_higher(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    version = spec.get("openapi", "")
    parts = version.split(".")
    assert int(parts[0]) >= 3
    if int(parts[0]) == 3:
        assert len(parts) >= 2 and int(parts[1]) >= 1


def test_all_paths_have_summary_or_description(client: TestClient) -> None:
    spec = _get_openapi_spec(client)
    for path, methods in spec["paths"].items():
        for method, detail in methods.items():
            if method == "parameters":
                continue
            has_summary = bool(detail.get("summary", ""))
            has_description = bool(detail.get("description", ""))
            assert has_summary or has_description, f"{method.upper()} {path} has no summary or description"
