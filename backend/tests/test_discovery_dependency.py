import builtins

import pytest

from app.discovery import DiscoveryDependencyError, get_ddgs_class


def test_get_ddgs_class_reports_missing_optional_dependency(monkeypatch):
    """Missing search packages should fail discovery, not app import."""
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name in {"ddgs", "duckduckgo_search"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(DiscoveryDependencyError) as excinfo:
        get_ddgs_class()

    assert "Discovery requires ddgs or duckduckgo_search" in str(excinfo.value)


def test_discover_endpoint_returns_503_when_discovery_dependency_missing(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "API_KEY", "")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "")

    async def missing_discovery(**kwargs):
        raise DiscoveryDependencyError("Discovery requires ddgs or duckduckgo_search.")

    monkeypatch.setattr("app.routers.jobs.discover_urls", missing_discovery)

    response = client.post(
        "/api/discover",
        json={"topic": "test topic", "num_results": 1, "schema_field_names": ["title"]},
    )

    assert response.status_code == 503
    assert "Discovery requires ddgs or duckduckgo_search" in response.json()["detail"]
