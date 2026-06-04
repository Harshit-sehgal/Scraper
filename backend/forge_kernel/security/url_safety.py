"""
URL safety — SSRF-oriented validation for public HTTP URLs.

Ported from the existing app.url_safety module with minimal changes.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from forge_kernel.config import settings

logger = logging.getLogger(__name__)


def _is_safe_ip(ip_str: str) -> bool:
    """Return True if the IP address is a public, routable IP address."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
        return True
    except ValueError:
        return False


def validate_public_http_url(url: str) -> None:
    """Raise ValueError if the URL is not a safe public HTTP(S) URL."""
    if not url:
        msg = "URL cannot be empty"
        raise ValueError(msg)

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"URL scheme '{parsed.scheme}' is not supported. Only http and https are allowed."
        raise ValueError(msg)

    hostname = parsed.hostname
    if not hostname:
        msg = f"URL '{url}' does not contain a valid hostname."
        raise ValueError(msg)

    hostname_lower = hostname.lower()

    # Allowlist override for integration tests
    sec = settings.security
    if settings.ops.SMOKE_TEST_MODE or sec.ENV.lower() in ("test", "ci"):
        allowed = [h.strip().lower() for h in sec.ALLOWED_INTERNAL_HOSTS.split(",") if h.strip()]
        if hostname_lower in allowed:
            return

    # Reject explicit loopback / internal names
    if hostname_lower in ("localhost", "host.docker.internal", "[::1]", "::1", "0.0.0.0", "127.0.0.1"):
        msg = f"URL hostname '{hostname}' is a restricted local loopback target."
        raise ValueError(msg)

    # Reject cloud metadata endpoints
    if hostname_lower in ("169.254.169.254", "metadata.google.internal", "instance-data"):
        msg = f"URL hostname '{hostname}' is a restricted cloud metadata endpoint."
        raise ValueError(msg)

    # Reject direct IP literals
    try:
        ip_literal = ipaddress.ip_address(hostname_lower.strip("[]"))
    except ValueError:
        ip_literal = None
    if ip_literal is not None:
        if not _is_safe_ip(str(ip_literal)):
            msg = f"URL resolves to restricted IP {ip_literal} — rejected for security."
            raise ValueError(msg)
        return

    # Reject internal TLDs
    for tld in (".local", ".internal", ".lan", ".corp"):
        if hostname_lower.endswith(tld):
            msg = f"URL hostname '{hostname}' uses internal TLD '{tld}' which is restricted."
            raise ValueError(msg)

    # DNS resolution check
    try:
        addrs = socket.getaddrinfo(hostname, None)
        for addr in addrs:
            ip = str(addr[4][0])
            if not _is_safe_ip(ip):
                msg = f"URL hostname '{hostname}' resolves to restricted IP {ip}."
                raise ValueError(msg)
    except (socket.gaierror, OSError) as e:
        if sec.ENV.lower() in ("production", "staging"):
            msg = f"URL hostname '{hostname}' could not be resolved — rejected for security."
            raise ValueError(msg)
        logger.warning("DNS resolution failed for hostname '%s': %s", hostname, e)
