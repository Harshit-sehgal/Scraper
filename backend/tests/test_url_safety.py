import socket
from typing import Never

import httpx
import pytest
from app.config import settings
from app.html_utils import _fetch_with_httpx
from app.url_safety import is_safe_ip, validate_public_http_url


def test_is_safe_ip() -> None:
    # Public IPs should be safe
    assert is_safe_ip("8.8.8.8") is True
    assert is_safe_ip("1.1.1.1") is True
    assert is_safe_ip("207.97.227.239") is True

    # Private IPs should be unsafe
    assert is_safe_ip("10.0.0.1") is False
    assert is_safe_ip("172.16.0.1") is False
    assert is_safe_ip("192.168.1.1") is False

    # Loopback/Reserved/Link-local/Multicast should be unsafe
    assert is_safe_ip("127.0.0.1") is False
    assert is_safe_ip("::1") is False
    assert is_safe_ip("0.0.0.0") is False  # nosec B104 - string literal under test, not actual network bind
    assert is_safe_ip("169.254.169.254") is False
    assert is_safe_ip("224.0.0.1") is False
    assert is_safe_ip("240.0.0.0") is False

    # Documentation / non-globally-routable ranges
    assert is_safe_ip("192.0.2.1") is False  # TEST-NET-1
    assert is_safe_ip("198.51.100.1") is False  # TEST-NET-2
    assert is_safe_ip("203.0.113.1") is False  # TEST-NET-3


def test_validate_public_http_url_basic_safety() -> None:
    # Public domains should pass
    validate_public_http_url("http://google.com")
    validate_public_http_url("https://github.com/trending")

    # Unsafe schemes should fail
    with pytest.raises(ValueError, match="scheme"):
        validate_public_http_url("ftp://google.com")
    with pytest.raises(ValueError, match="scheme"):
        validate_public_http_url("file:///etc/passwd")

    # Unsafe explicit hosts should fail
    for host in ("localhost", "127.0.0.1", "[::1]", "0.0.0.0", "host.docker.internal"):  # nosec B104 - string literal under test, not actual network bind
        with pytest.raises(ValueError, match="restricted local loopback target"):
            validate_public_http_url(f"http://{host}")

    # Metadata endpoints should fail
    for host in ("169.254.169.254", "metadata.google.internal", "instance-data"):
        with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
            validate_public_http_url(f"http://{host}")


def test_validate_public_http_url_port_allowlist(monkeypatch) -> None:
    """Outbound HTTP requests are restricted to standard web ports.

    Prevents SSRF probes from reaching internal services on non-HTTP
    ports (SSH, Redis, Memcached, etc.). The allowlist is bypassed in
    smoke-test mode (where integration endpoints may bind to ephemeral
    ports).
    """
    # Ensure smoke-test mode is off so the port allowlist is enforced.
    monkeypatch.delenv("DATAFORGE_SMOKE_TEST_MODE", raising=False)
    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "false")
    # Allowed ports should pass
    for port in (80, 443, 8080, 8443):
        validate_public_http_url(f"http://google.com:{port}/path")
    # Disallowed ports should be rejected
    for port in (22, 23, 25, 3306, 5432, 6379, 9200, 11211, 27017):
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_public_http_url(f"http://google.com:{port}/path")


def test_validate_public_http_url_dns_resolution(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENV", "production")

    # Mock socket.getaddrinfo to resolve safe-dns.com to 8.8.8.8
    def mock_getaddrinfo_safe(host, port, *args, **kwargs):
        if host == "safe-dns.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_safe)

    # Should pass since it resolves to public IP
    validate_public_http_url("http://safe-dns.com")

    # Mock socket.getaddrinfo to resolve bad-dns.com to 192.168.1.1 (private IP)
    def mock_getaddrinfo_unsafe(host, port, *args, **kwargs):
        if host == "bad-dns.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80))]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_unsafe)

    with pytest.raises(ValueError, match="resolves to restricted IP"):
        validate_public_http_url("http://bad-dns.com")

    # Verify DNS failure fails closed in production
    # Mock socket.getaddrinfo to raise gaierror for unresolvable domain
    def mock_getaddrinfo_fail(host, port, *args, **kwargs) -> Never:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_fail)

    with pytest.raises(ValueError, match="could not be resolved"):
        validate_public_http_url("http://unresolvable-domain.com")


def test_validate_public_http_url_allowlist(monkeypatch) -> None:
    # Set ALLOWED_INTERNAL_HOSTS config override
    monkeypatch.setattr(settings, "ALLOWED_INTERNAL_HOSTS", "nginx,smoke-host")

    # By default, internal hosts should be rejected in production/test unless smoke test mode is active
    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "false")
    # Mock socket.getaddrinfo to simulate unresolvable hosts for internal network names

    def mock_getaddrinfo_fail(host, port, *args, **kwargs) -> Never:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_fail)

    # Let's mock settings.ENV to "production" so it triggers DNS fail-closed for internal hosts
    monkeypatch.setattr(settings, "ENV", "production")

    with pytest.raises(ValueError, match="could not be resolved"):
        validate_public_http_url("http://nginx/smoke/records.html")

    # Set smoke test mode to active
    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "true")

    # Now it should bypass validation and return successfully!
    validate_public_http_url("http://nginx/smoke/records.html")
    validate_public_http_url("https://smoke-host/index.html")


# ── IPv6 private range tests ────────────────────────────────────────────


def test_is_safe_ip_ipv6_ranges() -> None:
    """IPv6 private, link-local, loopback, and multicast ranges are rejected."""
    # Unique Local Address (ULA) — fc00::/7 — considered private by ipaddress
    assert is_safe_ip("fc00::1") is False
    assert is_safe_ip("fd00::dead:beef") is False
    # Link-local — fe80::/10
    assert is_safe_ip("fe80::1") is False
    assert is_safe_ip("fe80::dead:beef") is False
    # Loopback — ::1
    assert is_safe_ip("::1") is False
    # Public IPv6 should be safe
    assert is_safe_ip("2001:4860:4860::8888") is True
    assert is_safe_ip("2606:4700:4700::1111") is True


def test_is_safe_ip_ipv4_mapped_ipv6() -> None:
    """IPv4-mapped IPv6 addresses are correctly classified for unsafe ranges.

    Note: On Python < 3.12, the entire ::ffff:0:0/96 range is considered
    "reserved", so we only assert unsafe addresses are caught.
    """
    # ::ffff:127.0.0.1 is loopback
    assert is_safe_ip("::ffff:127.0.0.1") is False
    # ::ffff:192.168.1.1 is private
    assert is_safe_ip("::ffff:192.168.1.1") is False
    # ::ffff:10.0.0.1 is private
    assert is_safe_ip("::ffff:10.0.0.1") is False
    # ::ffff:169.254.169.254 is link-local
    assert is_safe_ip("::ffff:169.254.169.254") is False


def test_validate_private_ip_explicit_urls() -> None:
    """Private IP ranges blocked when used as explicit URL hosts."""
    for host in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
        with pytest.raises(ValueError, match="restricted IP"):
            validate_public_http_url(f"http://{host}")


def test_validate_internal_tlds() -> None:
    """Internal TLDs .local, .internal, .lan, .corp are rejected."""
    # These should be rejected regardless of DNS resolution (before DNS check)
    for tld_host in ("somehost.local", "internal.host.internal", "server.lan", "company.corp"):
        with pytest.raises(ValueError, match="internal TLD"):
            validate_public_http_url(f"http://{tld_host}/path")

    # Internal TLD with subdomain
    with pytest.raises(ValueError, match="internal TLD"):
        validate_public_http_url("http://mail.server.local")

    # Regular .com, .org, etc. should pass DNS check (or fail closed)
    # We just verify they don't get the internal TLD error
    try:
        validate_public_http_url("http://example.com")
    except ValueError as e:
        assert "internal TLD" not in str(e)


def test_validate_credentials_in_url() -> None:
    """Credentials embedded in URLs are rejected when host is unsafe."""
    # user@127.0.0.1 — the @ is parsed as username, host remains 127.0.0.1
    with pytest.raises(ValueError, match="restricted local loopback target"):
        validate_public_http_url("http://user@127.0.0.1/")

    # user:pass@127.0.0.1
    with pytest.raises(ValueError, match="restricted local loopback target"):
        validate_public_http_url("http://user:pass@127.0.0.1/")

    # user@localhost
    with pytest.raises(ValueError, match="restricted local loopback target"):
        validate_public_http_url("http://user@localhost/")

    # user@public.com@127.0.0.1 — urlparse treats as user=user@public.com, host=127.0.0.1
    with pytest.raises(ValueError, match="restricted local loopback target"):
        validate_public_http_url("http://user@public.com@127.0.0.1/")


def test_validate_unresolved_host_in_dev(monkeypatch) -> None:
    """Unresolvable hostnames pass through in development mode."""
    monkeypatch.setattr(settings, "ENV", "development")

    def mock_getaddrinfo_fail(host, port, *args, **kwargs) -> Never:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_fail)

    # Should not raise in development
    validate_public_http_url("http://some-nonexistent-host-xyz.com/path")


def test_validate_resolved_private_ip_via_dns_ipv6(monkeypatch) -> None:
    """Hostname resolving to IPv6 private address is rejected."""
    monkeypatch.setattr(settings, "ENV", "production")

    # Use a non-internal-TLD hostname so DNS resolution kicks in
    def mock_getaddrinfo_v6(host, port, *args, **kwargs):
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fc00::1", 80, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_v6)

    with pytest.raises(ValueError, match="resolves to restricted IP"):
        validate_public_http_url("http://ula-host.example.com")

    def mock_getaddrinfo_v6_linklocal(host, port, *args, **kwargs):
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 80, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_v6_linklocal)

    with pytest.raises(ValueError, match="resolves to restricted IP"):
        validate_public_http_url("http://link-local-host.example.com")


def test_validate_resolved_private_ip_via_dns_decimal_ip(monkeypatch) -> None:
    """Hostname that resolves to a decimal/hex IP representation via DNS is rejected.

    On Linux, decimal IPs like 2130706433 resolve to 127.0.0.1 via DNS.
    We test this by monkeypatching getaddrinfo to simulate the resolution.
    """
    monkeypatch.setattr(settings, "ENV", "production")

    # Simulate decimal IP resolution (2130706433 = 127.0.0.1)
    def mock_getaddrinfo_decimal(host, port, *args, **kwargs):
        if host == "2130706433":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_decimal)

    with pytest.raises(ValueError, match="restricted IP"):
        validate_public_http_url("http://2130706433/")

    # Simulate hex IP resolution (0x7f000001 = 127.0.0.1)
    def mock_getaddrinfo_hex(host, port, *args, **kwargs):
        if host == "0x7f000001":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_hex)

    with pytest.raises(ValueError, match="restricted IP"):
        validate_public_http_url("http://0x7f000001/")


def test_validate_redirect_to_private_ranges(monkeypatch) -> None:
    """Ensure redirects to various private ranges are caught via the final URL validation."""
    # 10.0.0.0/8
    with pytest.raises(ValueError, match="restricted IP"):
        validate_public_http_url("http://10.0.0.1/path")
    # 169.254.169.254 (cloud metadata)
    with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
        validate_public_http_url("http://169.254.169.254/latest/meta-data")
    # 0.0.0.0
    with pytest.raises(ValueError, match="restricted local loopback target"):
        validate_public_http_url("http://0.0.0.0/something")


# ── HTTPX redirect integration tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_redirect_to_private_ip(monkeypatch) -> None:
    class MockResponse:
        def __init__(self, url, status_code, headers, is_redirect=False) -> None:
            self.url = httpx.URL(url)
            self.status_code = status_code
            self.headers = headers
            self.is_redirect = is_redirect

        def raise_for_status(self) -> None:
            pass

    async def mock_get(self, url, *args, **kwargs):
        # First call: redirect to private IP
        if "start-url" in str(url):
            return MockResponse(
                url="http://public-site.com/start-url",
                status_code=302,
                headers={"location": "http://127.0.0.1"},
                is_redirect=True,
            )
        return MockResponse(url="http://127.0.0.1", status_code=200, headers={}, is_redirect=False)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(ValueError, match="restricted local loopback target"):
        await _fetch_with_httpx("http://public-site.com/start-url")


@pytest.mark.asyncio
async def test_fetch_redirect_to_cloud_metadata(monkeypatch) -> None:
    """Redirect to 169.254.169.254 (cloud metadata) is caught."""

    class MockResponse:
        def __init__(self, url, status_code, headers, is_redirect=False) -> None:
            self.url = httpx.URL(url)
            self.status_code = status_code
            self.headers = headers
            self.is_redirect = is_redirect

        def raise_for_status(self) -> None:
            pass

    async def mock_get(self, url, *args, **kwargs):
        if "public-site" in str(url):
            return MockResponse(
                url="http://public-site.com/start",
                status_code=302,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
                is_redirect=True,
            )
        return MockResponse(url="http://169.254.169.254/latest/meta-data/", status_code=200, headers={}, is_redirect=False)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
        await _fetch_with_httpx("http://public-site.com/start")


# ── Smoke mode allowlist extras ─────────────────────────────────────────


def test_smoke_mode_internal_tld_allowed(monkeypatch) -> None:
    """Internal TLDs are still rejected even in smoke mode (separate from ALLOWED_INTERNAL_HOSTS)."""
    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "true")
    monkeypatch.setattr(settings, "ALLOWED_INTERNAL_HOSTS", "nginx,smoke-host")
    monkeypatch.setattr(settings, "ENV", "production")

    # Internal TLD .local should still be rejected even in smoke mode
    with pytest.raises(ValueError, match="internal TLD"):
        validate_public_http_url("http://something.local/path")

    # But explicit allowlist hosts still work
    def mock_getaddrinfo_nginx(host, port, *args, **kwargs):
        if host == "nginx":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.10", 80))]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_nginx)

    # nginx is in allowed_internal_hosts, so it passes in smoke mode
    validate_public_http_url("http://nginx/smoke/records.html")


def test_validate_resolved_private_ip_in_dev(monkeypatch) -> None:
    """Hosts resolving to private IPs via DNS are rejected even in development mode."""
    monkeypatch.setattr(settings, "ENV", "development")

    def mock_getaddrinfo_unsafe(host, port, *args, **kwargs):
        if host == "bad-dev-dns.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", 80))]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo_unsafe)

    with pytest.raises(ValueError, match="resolves to restricted IP"):
        validate_public_http_url("http://bad-dev-dns.com")


@pytest.mark.asyncio
async def test_get_safe_async_client_blocks_private_ip() -> None:
    from app.url_safety import get_safe_async_client

    async with get_safe_async_client() as client:
        # The PUBLIC-API transport wrapper is the primary SSRF layer
        # and short-circuits the request before the network backend is
        # consulted. The wrapper raises with a "Transport rejected"
        # message; the network backend's "Rejected connection" message
        # is only reached if the wrapper is bypassed.
        with pytest.raises(ValueError, match="(Transport rejected|Rejected connection)"):
            await client.get("http://127.0.0.1:8000")


@pytest.mark.asyncio
async def test_get_safe_async_client_blocks_unix_socket() -> None:
    from app.url_safety import SafeAsyncNetworkBackend
    from httpcore._backends.auto import AutoBackend

    backend = SafeAsyncNetworkBackend(AutoBackend())
    with pytest.raises(ValueError, match="UNIX socket connections are disabled"):
        await backend.connect_unix_socket("/tmp/some.sock")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code
