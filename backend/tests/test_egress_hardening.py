"""G3 — Network-level egress hardening tests.

Validates the full SSRF protection stack: IP classification, URL
validation, port allowlist, DNS rebinding defence, and IPv6 private
ranges.  All DNS calls are mocked via ``monkeypatch`` on
``socket.getaddrinfo`` to avoid real network I/O.
"""

import socket

import httpcore
import pytest
from app.url_safety import (
    SafeAsyncNetworkBackend,
    SafeNetworkBackend,
    is_safe_ip,
    validate_public_http_url,
)

# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=False)
def _no_smoke_mode(monkeypatch) -> None:
    """Ensure smoke-test mode is OFF so port allowlist is enforced."""
    monkeypatch.delenv("DATAFORGE_SMOKE_TEST_MODE", raising=False)
    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "false")


def _fake_getaddrinfo(resolved_ip: str):
    """Return a monkeypatchable getaddrinfo that resolves everything to *resolved_ip*."""

    def _resolver(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ip, port or 0))]

    return _resolver


# ── 1. RFC 1918 private ranges ───────────────────────────────────────


class TestRfc1918PrivateRanges:
    """All RFC 1918 private IPv4 blocks are rejected by is_safe_ip."""

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "10.255.255.255",
            "10.1.2.3",
        ],
        ids=["10-low", "10-high", "10-mid"],
    )
    def test_10_block(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    @pytest.mark.parametrize(
        "ip",
        [
            "172.16.0.1",
            "172.31.255.255",
            "172.20.10.5",
        ],
        ids=["172.16-low", "172.31-high", "172.20-mid"],
    )
    def test_172_16_block(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    @pytest.mark.parametrize(
        "ip",
        [
            "192.168.0.1",
            "192.168.255.255",
            "192.168.1.100",
        ],
        ids=["192.168-low", "192.168-high", "192.168-mid"],
    )
    def test_192_168_block(self, ip: str) -> None:
        assert is_safe_ip(ip) is False


class TestRfc1918ViaUrlValidation:
    """RFC 1918 IPs used as explicit URL hosts are rejected."""

    @pytest.mark.parametrize(
        "host",
        ["10.0.0.1", "172.16.0.1", "192.168.1.1"],
        ids=["10", "172.16", "192.168"],
    )
    def test_private_ip_as_host(self, host: str) -> None:
        with pytest.raises(ValueError, match="restricted IP"):
            validate_public_http_url(f"http://{host}/path")


# ── 2. Loopback ──────────────────────────────────────────────────────


class TestLoopbackBlocking:
    """Loopback addresses (IPv4 and IPv6) and 0.0.0.0 are rejected."""

    @pytest.mark.parametrize(
        "ip",
        ["127.0.0.1", "127.0.0.2", "127.255.255.255"],
        ids=["127.0.0.1", "127.0.0.2", "127.255.255.255"],
    )
    def test_ipv4_loopback(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    def test_ipv6_loopback(self) -> None:
        assert is_safe_ip("::1") is False

    def test_unspecified_ipv4(self) -> None:
        assert is_safe_ip("0.0.0.0") is False  # nosec B104

    def test_unspecified_ipv6(self) -> None:
        assert is_safe_ip("::") is False

    @pytest.mark.parametrize(
        "host",
        ["localhost", "127.0.0.1", "[::1]", "0.0.0.0"],
        ids=["localhost", "127.0.0.1", "ipv6-bracket", "0.0.0.0"],
    )
    def test_loopback_via_url(self, host: str) -> None:
        with pytest.raises(ValueError, match="restricted local loopback target"):
            validate_public_http_url(f"http://{host}/")


# ── 3. Link-local ────────────────────────────────────────────────────


class TestLinkLocalBlocking:
    """Link-local addresses (IPv4 169.254.x.x and IPv6 fe80::) are rejected."""

    @pytest.mark.parametrize(
        "ip",
        ["169.254.0.1", "169.254.169.254", "169.254.255.255"],
        ids=["169.254.0.1", "169.254.169.254", "169.254.255.255"],
    )
    def test_ipv4_link_local(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    @pytest.mark.parametrize(
        "ip",
        ["fe80::1", "fe80::dead:beef"],
        ids=["fe80::1", "fe80::dead:beef"],
    )
    def test_ipv6_link_local(self, ip: str) -> None:
        assert is_safe_ip(ip) is False


# ── 4. Multicast ─────────────────────────────────────────────────────


class TestMulticastBlocking:
    """Multicast addresses are rejected."""

    @pytest.mark.parametrize(
        "ip",
        [
            "224.0.0.1",
            "224.0.0.0",
            "239.255.255.255",
            "224.1.2.3",
        ],
        ids=["224.0.0.1", "224.0.0.0", "239.255.255.255", "224.1.2.3"],
    )
    def test_ipv4_multicast(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    def test_ipv6_multicast(self) -> None:
        assert is_safe_ip("ff02::1") is False

    def test_multicast_via_url(self) -> None:
        with pytest.raises(ValueError, match="restricted IP"):
            validate_public_http_url("http://224.0.0.1/")


# ── 5. Cloud metadata endpoints ──────────────────────────────────────


class TestCloudMetadataBlocking:
    """Cloud metadata endpoints are rejected at the URL level."""

    @pytest.mark.parametrize(
        "host",
        ["169.254.169.254", "metadata.google.internal", "instance-data"],
        ids=["aws-metadata", "gcp-metadata", "instance-data"],
    )
    def test_metadata_endpoints(self, host: str) -> None:
        with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
            validate_public_http_url(f"http://{host}/latest/meta-data/")

    def test_aws_metadata_with_path(self) -> None:
        with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
            validate_public_http_url(
                "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            )

    def test_gcp_metadata_token(self) -> None:
        with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
            validate_public_http_url(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            )


# ── 6. Internal TLDs ────────────────────────────────────────────────


class TestInternalTlds:
    """Internal TLDs (.local, .internal, .lan, .corp) are rejected."""

    @pytest.mark.parametrize(
        "host",
        [
            "myserver.local",
            "api.internal",
            "printer.lan",
            "ad.corp",
            "sub.domain.local",
            "deep.nested.internal",
        ],
        ids=[".local", ".internal", ".lan", ".corp", "sub.local", "deep.internal"],
    )
    def test_internal_tld_rejected(self, host: str) -> None:
        with pytest.raises(ValueError, match="internal TLD"):
            validate_public_http_url(f"http://{host}/")

    def test_safe_tlds_not_rejected(self) -> None:
        """Normal TLDs do not trigger the internal-TLD check."""
        for host in ("example.com", "google.org", "company.io", "api.dev"):
            try:
                validate_public_http_url(f"http://{host}")
            except ValueError as e:
                assert "internal TLD" not in str(e)


# ── 7. Non-standard ports blocked ────────────────────────────────────


class TestNonStandardPortsBlocked:
    """Non-HTTP ports are rejected when smoke-test mode is OFF."""

    @pytest.mark.usefixtures("_no_smoke_mode")
    @pytest.mark.parametrize(
        "port",
        [22, 23, 25, 53, 110, 143, 3306, 5432, 6379, 9200, 11211, 27017],
        ids=[
            "ssh",
            "telnet",
            "smtp",
            "dns",
            "pop3",
            "imap",
            "mysql",
            "postgres",
            "redis",
            "elasticsearch",
            "memcached",
            "mongodb",
        ],
    )
    def test_disallowed_ports(self, port: int) -> None:
        with pytest.raises(ValueError, match="not in the allowed list"):
            validate_public_http_url(f"http://example.com:{port}/")


# ── 8. Standard ports allowed ────────────────────────────────────────


class TestStandardPortsAllowed:
    """Standard HTTP/HTTPS ports are allowed."""

    @pytest.mark.usefixtures("_no_smoke_mode")
    @pytest.mark.parametrize(
        "port",
        [80, 443, 8080, 8443],
        ids=["http", "https", "alt-http", "alt-https"],
    )
    def test_allowed_ports(self, port: int) -> None:
        validate_public_http_url(f"http://example.com:{port}/path")


# ── 9. DNS rebinding protection ──────────────────────────────────────


class TestDnsRebindingProtection:
    """Hostnames resolving to private IPs are blocked by the transport layer."""

    def test_dns_rebinding_to_private_ip(self, monkeypatch) -> None:
        """A hostname that resolves to a private IP is caught by SafeNetworkBackend."""
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("192.168.1.100"))
        backend = SafeNetworkBackend.__new__(SafeNetworkBackend)
        with pytest.raises(ValueError, match="unsafe IP"):
            # SafeNetworkBackend.connect_tcp resolves then validates
            backend.connect_tcp("evil-rebind.example.com", 80)

    def test_dns_rebinding_to_loopback(self, monkeypatch) -> None:
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
        backend = SafeNetworkBackend.__new__(SafeNetworkBackend)
        with pytest.raises(ValueError, match="unsafe IP"):
            backend.connect_tcp("rebind-loopback.example.com", 443)

    def test_dns_rebinding_to_link_local(self, monkeypatch) -> None:
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
        backend = SafeNetworkBackend.__new__(SafeNetworkBackend)
        with pytest.raises(ValueError, match="unsafe IP"):
            backend.connect_tcp("rebind-metadata.example.com", 80)

    @pytest.mark.asyncio
    async def test_dns_rebinding_to_private_via_async_backend(self, monkeypatch) -> None:
        """Async variant: SafeAsyncNetworkBackend also blocks rebinding."""

        async def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.99", port or 0))]

        async def fake_sleep(self, seconds) -> None:
            pass

        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.99"))

        class FakeAsyncBackend(httpcore.AsyncNetworkBackend):
            async def connect_tcp(self, host, port, **kwargs) -> None:  # type: ignore[override]
                return None

            async def connect_unix_socket(self, path, **kwargs):  # type: ignore[override]
                raise NotImplementedError

            async def sleep(self, seconds) -> None:
                pass

        backend = SafeAsyncNetworkBackend(FakeAsyncBackend())
        with pytest.raises(ValueError, match="unsafe IP"):
            await backend.connect_tcp("rebind-async.example.com", 80)

    def test_dns_rebinding_to_172_16(self, monkeypatch) -> None:
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("172.16.0.1"))
        backend = SafeNetworkBackend.__new__(SafeNetworkBackend)
        with pytest.raises(ValueError, match="unsafe IP"):
            backend.connect_tcp("rebind-172.example.com", 80)

    def test_safe_public_ip_passes(self, monkeypatch) -> None:
        """A hostname resolving to a public IP should not be rejected."""
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("8.8.8.8"))
        # is_safe_ip should return True for public IPs
        assert is_safe_ip("8.8.8.8") is True


# ── 10. IPv6 private ranges ──────────────────────────────────────────


class TestIPv6PrivateRanges:
    """IPv6 private, ULA, and link-local ranges are rejected."""

    @pytest.mark.parametrize(
        "ip",
        [
            "fc00::1",
            "fd00::dead:beef",
            "fd00::1",
        ],
        ids=["fc00", "fd00-dead-beef", "fd00-min"],
    )
    def test_ula_rejected(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    @pytest.mark.parametrize(
        "ip",
        [
            "fe80::1",
            "fe80::dead:beef",
        ],
        ids=["fe80-1", "fe80-dead-beef"],
    )
    def test_ipv6_link_local_rejected(self, ip: str) -> None:
        assert is_safe_ip(ip) is False

    def test_ipv6_loopback(self) -> None:
        assert is_safe_ip("::1") is False

    def test_ipv6_multicast(self) -> None:
        assert is_safe_ip("ff02::1") is False

    def test_ipv6_public_safe(self) -> None:
        """Public IPv6 addresses (Google, Cloudflare) are allowed."""
        assert is_safe_ip("2001:4860:4860::8888") is True
        assert is_safe_ip("2606:4700:4700::1111") is True

    def test_ipv6_v4_mapped_private(self) -> None:
        """IPv4-mapped IPv6 wrapping private IPs are rejected."""
        assert is_safe_ip("::ffff:192.168.1.1") is False
        assert is_safe_ip("::ffff:10.0.0.1") is False
        assert is_safe_ip("::ffff:127.0.0.1") is False
        assert is_safe_ip("::ffff:169.254.169.254") is False


# ── Additional edge-case hardening ───────────────────────────────────


class TestEdgeCases:
    """Boundary and edge-case coverage for egress hardening."""

    def test_reserved_range_class_c(self) -> None:
        assert is_safe_ip("240.0.0.0") is False

    def test_documentation_range(self) -> None:
        assert is_safe_ip("192.0.2.1") is False  # TEST-NET-1
        assert is_safe_ip("198.51.100.1") is False  # TEST-NET-2
        assert is_safe_ip("203.0.113.1") is False  # TEST-NET-3

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_public_http_url("")

    def test_bad_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            validate_public_http_url("ftp://example.com")
        with pytest.raises(ValueError, match="scheme"):
            validate_public_http_url("file:///etc/passwd")

    def test_no_hostname_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not contain a valid hostname"):
            validate_public_http_url("http://")

    def test_host_docker_internal_rejected(self) -> None:
        with pytest.raises(ValueError, match="restricted local loopback target"):
            validate_public_http_url("http://host.docker.internal/")

    def test_ipv6_loopback_in_url(self) -> None:
        with pytest.raises(ValueError, match="restricted local loopback target"):
            validate_public_http_url("http://[::1]/")

    @pytest.mark.asyncio
    async def test_safe_async_client_blocks_private_ip(self, monkeypatch) -> None:
        from app.url_safety import get_safe_async_client

        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.1"))

        async with get_safe_async_client() as client:
            with pytest.raises(ValueError, match="(Transport rejected|Rejected connection)"):
                await client.get("http://10.0.0.1:8000")

    @pytest.mark.asyncio
    async def test_safe_async_client_blocks_loopback(self, monkeypatch) -> None:
        from app.url_safety import get_safe_async_client

        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))

        async with get_safe_async_client() as client:
            with pytest.raises(ValueError, match="(Transport rejected|Rejected connection)"):
                await client.get("http://127.0.0.1:9090")

    @pytest.mark.asyncio
    async def test_unix_socket_blocked(self) -> None:
        backend = SafeAsyncNetworkBackend.__new__(SafeAsyncNetworkBackend)
        with pytest.raises(ValueError, match="UNIX socket connections are disabled"):
            await backend.connect_unix_socket("/tmp/some.sock")  # nosec B108
