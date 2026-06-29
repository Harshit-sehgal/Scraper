"""Tests for OpenAPI spec generation (Roadmap Dev 4).

Validates that the auto-generated OpenAPI schema is well-formed,
covers required routes, and includes proper parameter documentation.
"""

from __future__ import annotations

from typing import Any


def _load_openapi_spec() -> dict[str, Any]:
    """Load the OpenAPI spec by importing the app.

    We call ``app.openapi()`` which lazily generates the schema
    from the registered routes.  This is the same mechanism
    used by ``/openapi.json`` at runtime.
    """
    from app.main import create_app

    app = create_app()
    return app.openapi()


class TestOpenApiSpecStructure:
    """Top-level OpenAPI document structure."""

    def test_spec_is_dict(self) -> None:
        spec = _load_openapi_spec()
        assert isinstance(spec, dict)

    def test_has_openapi_version(self) -> None:
        spec = _load_openapi_spec()
        assert "openapi" in spec
        assert spec["openapi"].startswith("3.")

    def test_has_info(self) -> None:
        spec = _load_openapi_spec()
        info = spec.get("info", {})
        assert "title" in info
        assert "version" in info

    def test_has_paths(self) -> None:
        spec = _load_openapi_spec()
        assert "paths" in spec
        assert isinstance(spec["paths"], dict)


class TestRequiredRoutes:
    """Essential API routes must appear in the spec."""

    def test_jobs_list_route_present(self) -> None:
        spec = _load_openapi_spec()
        assert "/api/jobs" in spec["paths"]

    def test_jobs_create_route_present(self) -> None:
        spec = _load_openapi_spec()
        assert "/api/jobs" in spec["paths"]
        assert "post" in spec["paths"]["/api/jobs"]

    def test_jobs_get_route_present(self) -> None:
        spec = _load_openapi_spec()
        assert "/api/jobs/{job_id}" in spec["paths"]

    def test_jobs_cancel_route_present(self) -> None:
        spec = _load_openapi_spec()
        matches = [p for p in spec["paths"] if "cancel" in p.lower()]
        assert len(matches) >= 1

    def test_jobs_results_route_present(self) -> None:
        spec = _load_openapi_spec()
        matches = [p for p in spec["paths"] if "results" in p.lower()]
        assert len(matches) >= 1

    def test_usage_route_present(self) -> None:
        spec = _load_openapi_spec()
        usage_paths = [p for p in spec["paths"] if "usage" in p.lower()]
        assert len(usage_paths) >= 1

    def test_health_route_present(self) -> None:
        spec = _load_openapi_spec()
        assert "/health" in spec["paths"]

    def test_preview_route_present(self) -> None:
        spec = _load_openapi_spec()
        assert "/api/scraper/preview" in spec["paths"]

    def test_debug_route_present(self) -> None:
        spec = _load_openapi_spec()
        debug_paths = [p for p in spec["paths"] if "debug" in p.lower()]
        assert len(debug_paths) >= 1


class TestRouteMethods:
    """HTTP methods for routes are correct."""

    def test_jobs_list_is_get(self) -> None:
        spec = _load_openapi_spec()
        assert "get" in spec["paths"]["/api/jobs"]

    def test_jobs_create_is_post(self) -> None:
        spec = _load_openapi_spec()
        assert "post" in spec["paths"]["/api/jobs"]

    def test_jobs_get_is_get(self) -> None:
        spec = _load_openapi_spec()
        assert "get" in spec["paths"]["/api/jobs/{job_id}"]


class TestParameterDocumentation:
    """Route parameters are documented in the spec."""

    def test_job_id_parameter_documented(self) -> None:
        spec = _load_openapi_spec()
        path_item = spec["paths"].get("/api/jobs/{job_id}", {})
        params = path_item.get("get", {}).get("parameters", [])
        param_names = [p.get("name") for p in params]
        assert "job_id" in param_names

    def test_include_results_parameter_documented(self) -> None:
        spec = _load_openapi_spec()
        path_item = spec["paths"].get("/api/jobs/{job_id}", {})
        params = path_item.get("get", {}).get("parameters", [])
        param_names = [p.get("name") for p in params]
        assert "include_results" in param_names

    def test_list_jobs_limit_parameter(self) -> None:
        spec = _load_openapi_spec()
        path_item = spec["paths"].get("/api/jobs", {})
        params = path_item.get("get", {}).get("parameters", [])
        param_names = [p.get("name") for p in params]
        assert any("limit" in n for n in param_names)


class TestSchemaComponents:
    """OpenAPI schema components are generated."""

    def test_has_schemas(self) -> None:
        spec = _load_openapi_spec()
        components = spec.get("components", {})
        assert "schemas" in components

    def test_has_job_schema(self) -> None:
        spec = _load_openapi_spec()
        schemas = spec.get("components", {}).get("schemas", {})
        job_schemas = [k for k in schemas if "job" in k.lower()]
        assert len(job_schemas) >= 1

    def test_schemas_are_dicts(self) -> None:
        spec = _load_openapi_spec()
        schemas = spec.get("components", {}).get("schemas", {})
        for name, schema in schemas.items():
            assert isinstance(schema, dict), f"Schema {name} is not a dict"
