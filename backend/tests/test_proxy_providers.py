"""Tests for the proxy provider plug-in system.

Validates:
1. StaticListProvider returns fixed list
2. JsonFileProvider reads + re-reads a JSON array file
3. HttpUrlProvider raises on empty URL
4. create_provider() resolves from settings
5. ProxyManager delegates to a JsonFileProvider
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.proxy_providers import (
    BrightDataProvider,
    HttpUrlProvider,
    JsonFileProvider,
    OxylabsProvider,
    SmartproxyProvider,
    StaticListProvider,
    create_provider,
)

# ---------------------------------------------------------------------------
# StaticListProvider
# ---------------------------------------------------------------------------


class TestStaticListProvider:
    def test_returns_fixed_list(self) -> None:
        provider = StaticListProvider(["http://a:8080", "http://b:8080"])
        assert provider.fetch_proxies() == ["http://a:8080", "http://b:8080"]

    def test_refresh_returns_same_list(self) -> None:
        provider = StaticListProvider(["http://a:8080"])
        assert provider.refresh() == ["http://a:8080"]

    def test_empty_proxies(self) -> None:
        provider = StaticListProvider([])
        assert provider.fetch_proxies() == []

    def test_returns_copy(self) -> None:
        original = ["http://a:8080"]
        provider = StaticListProvider(original)
        result = provider.fetch_proxies()
        result.append("http://extra:8080")
        assert provider.fetch_proxies() == ["http://a:8080"]


# ---------------------------------------------------------------------------
# JsonFileProvider
# ---------------------------------------------------------------------------


class TestJsonFileProvider:
    def test_reads_json_array(self, tmp_path: Path) -> None:
        f = tmp_path / "proxies.json"
        f.write_text(json.dumps(["http://a:8080", "socks5://b:1080"]))
        provider = JsonFileProvider(f)
        assert provider.fetch_proxies() == ["http://a:8080", "socks5://b:1080"]

    def test_refresh_picks_up_changes(self, tmp_path: Path) -> None:
        f = tmp_path / "proxies.json"
        f.write_text(json.dumps(["http://a:8080"]))
        provider = JsonFileProvider(f)
        assert provider.fetch_proxies() == ["http://a:8080"]

        # Modify the file
        f.write_text(json.dumps(["http://a:8080", "http://c:9090"]))
        refreshed = provider.refresh()
        assert refreshed == ["http://a:8080", "http://c:9090"]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.json"
        provider = JsonFileProvider(missing)
        assert provider.fetch_proxies() == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{invalid json")
        provider = JsonFileProvider(f)
        assert provider.fetch_proxies() == []

    def test_non_array_json_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "obj.json"
        f.write_text(json.dumps({"proxy": "http://a:8080"}))
        provider = JsonFileProvider(f)
        assert provider.fetch_proxies() == []

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        f = tmp_path / "ws.json"
        f.write_text(json.dumps(["  http://a:8080  ", ""]))
        provider = JsonFileProvider(f)
        assert provider.fetch_proxies() == ["http://a:8080"]


# ---------------------------------------------------------------------------
# HttpUrlProvider
# ---------------------------------------------------------------------------


class TestHttpUrlProvider:
    def test_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            HttpUrlProvider("")

    def test_constructs_with_url(self) -> None:
        provider = HttpUrlProvider("https://api.example.com/proxies")
        assert provider._url == "https://api.example.com/proxies"

    def test_auth_header_preserved(self) -> None:
        provider = HttpUrlProvider("https://x", auth_header="Bearer secret")
        assert provider._auth_header == "Bearer secret"

    def test_ssrf_blocks_internal_url(self) -> None:
        """Provider URL pointing to internal/metadata addresses must be blocked."""
        internal_urls = [
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8080/proxies",
            "http://127.0.0.1:8080/proxies",
            "http://10.0.0.1/proxies",
        ]
        for url in internal_urls:
            provider = HttpUrlProvider(url)
            result = provider.fetch_proxies()
            assert result == [], f"SSRF: {url} must be blocked but fetched proxies"


# ---------------------------------------------------------------------------
# Provider-specific aliases
# ---------------------------------------------------------------------------


class TestProviderAliases:
    def test_brightdata_sets_bearer_auth(self) -> None:
        provider = BrightDataProvider("https://x", api_key="mykey")
        assert provider._auth_header == "Bearer mykey"

    def test_oxylabs_sets_token_auth(self) -> None:
        provider = OxylabsProvider("https://x", api_key="mykey")
        assert provider._auth_header == "Token mykey"

    def test_smartproxy_sets_basic_auth(self) -> None:
        provider = SmartproxyProvider("https://x", api_key="user:pass")
        assert provider._auth_header.startswith("Basic ")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateProvider:
    def test_returns_static_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "PROXY_PROVIDER_TYPE", "static")
        monkeypatch.setattr(settings, "PROXY_LIST", "http://a:8080,http://b:8080")
        provider = create_provider()
        assert isinstance(provider, StaticListProvider)
        assert provider.fetch_proxies() == ["http://a:8080", "http://b:8080"]

    def test_file_type_returns_json_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        f = tmp_path / "p.json"
        f.write_text(json.dumps(["http://c:9090"]))
        from app.config import settings

        monkeypatch.setattr(settings, "PROXY_PROVIDER_TYPE", "file")
        monkeypatch.setattr(settings, "PROXY_PROVIDER_FILE", str(f))
        provider = create_provider()
        assert isinstance(provider, JsonFileProvider)
        assert provider.fetch_proxies() == ["http://c:9090"]

    def test_url_type_with_empty_url_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "PROXY_PROVIDER_TYPE", "url")
        monkeypatch.setattr(settings, "PROXY_PROVIDER_URL", "")
        provider = create_provider()
        # Should fall back to static with empty list
        assert isinstance(provider, StaticListProvider)

    def test_unknown_type_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "PROXY_PROVIDER_TYPE", "unknown_provider")
        monkeypatch.setattr(settings, "PROXY_LIST", "http://a:8080")
        provider = create_provider()
        assert isinstance(provider, StaticListProvider)


# ---------------------------------------------------------------------------
# Integration: ProxyManager + provider
# ---------------------------------------------------------------------------


class TestProxyManagerWithProvider:
    def test_delegates_to_json_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        f = tmp_path / "proxies.json"
        f.write_text(json.dumps(["http://p1:8080", "http://p2:8080"]))

        from app.config import settings
        from app.proxy_manager import ProxyManager

        monkeypatch.setattr(settings, "PROXY_ROTATION_ENABLED", True)
        monkeypatch.setattr(settings, "PROXY_PROVIDER_TYPE", "file")
        monkeypatch.setattr(settings, "PROXY_PROVIDER_FILE", str(f))

        mgr = ProxyManager()
        assert mgr.enabled
        assert mgr._proxy_list == ["http://p1:8080", "http://p2:8080"]

    def test_refresh_from_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        f = tmp_path / "proxies.json"
        f.write_text(json.dumps(["http://p1:8080"]))

        from app.config import settings
        from app.proxy_manager import ProxyManager

        monkeypatch.setattr(settings, "PROXY_ROTATION_ENABLED", True)
        monkeypatch.setattr(settings, "PROXY_PROVIDER_TYPE", "file")
        monkeypatch.setattr(settings, "PROXY_PROVIDER_FILE", str(f))

        mgr = ProxyManager()

        # Update file
        f.write_text(json.dumps(["http://p1:8080", "http://p3:9090"]))
        count = mgr.refresh_from_provider()
        assert count == 2
        assert "http://p3:9090" in mgr._proxy_list

    def test_set_provider_for_testing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings
        from app.proxy_manager import ProxyManager

        monkeypatch.setattr(settings, "PROXY_ROTATION_ENABLED", True)
        monkeypatch.setattr(settings, "PROXY_LIST", "http://initial:8080")

        mgr = ProxyManager()
        assert mgr._proxy_list == ["http://initial:8080"]

        # Inject a mock provider
        mock_provider = StaticListProvider(["http://mocked:1234"])
        mgr.set_provider(mock_provider)
        count = mgr.refresh_from_provider()
        assert count == 1
        assert mgr._proxy_list == ["http://mocked:1234"]

