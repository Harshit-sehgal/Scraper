"""SSRF prevention with DNS-rebinding attack mitigation."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFDefense:
    """Prevent SSRF and DNS-rebinding attacks."""

    # Blocked IP ranges
    BLOCKED_RANGES = [
        ipaddress.ip_network("127.0.0.0/8"),  # Localhost
        ipaddress.ip_network("10.0.0.0/8"),  # Private
        ipaddress.ip_network("172.16.0.0/12"),  # Private
        ipaddress.ip_network("192.168.0.0/16"),  # Private
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local
        ipaddress.ip_network("224.0.0.0/4"),  # Multicast
        ipaddress.ip_network("240.0.0.0/4"),  # Reserved
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fc00::/7"),  # IPv6 private
        ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ]

    @classmethod
    def is_blocked_ip(cls, ip_str: str) -> bool:
        """Check if IP is in blocked ranges."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in blocked_range for blocked_range in cls.BLOCKED_RANGES)
        except (ValueError, TypeError):
            return False

    @classmethod
    def resolve_and_check(cls, hostname: str) -> str | None:
        """Resolve hostname and verify it's not in blocked range (DNS-rebinding mitigation)."""
        try:
            # Resolve hostname
            result = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)

            if not result:
                logger.warning(f"DNS resolution failed for {hostname}")
                return None

            # Check each resolved IP
            resolved_ips = []
            for family, socktype, proto, canonname, sockaddr in result:
                ip = sockaddr[0]

                if cls.is_blocked_ip(ip):
                    logger.warning(f"SSRF blocked: hostname {hostname} resolved to blocked IP {ip}")
                    return None

                resolved_ips.append(ip)

            # Return first non-blocked IP
            return resolved_ips[0] if resolved_ips else None

        except socket.gaierror as e:
            logger.warning(f"DNS resolution error for {hostname}: {e}")
            return None

    @classmethod
    def validate_url(cls, url: str) -> tuple[bool, str | None]:
        """Validate URL for SSRF safety."""
        try:
            parsed = urlparse(url)

            if not parsed.hostname:
                return False, "No hostname in URL"

            # Block certain schemes
            if parsed.scheme.lower() not in ("http", "https"):
                return False, f"Blocked scheme: {parsed.scheme}"

            # Resolve and check hostname
            ip = cls.resolve_and_check(parsed.hostname)
            if ip is None:
                return False, f"Hostname {parsed.hostname} resolved to blocked IP or failed DNS"

            return True, ip

        except Exception as e:
            logger.exception(f"URL validation error: {e}")
            return False, str(e)


class DNSRebindingDefense:
    """Detect and prevent DNS-rebinding attacks."""

    def __init__(self, ttl_cache_seconds: int = 300):
        """Initialize with cache TTL."""
        self.ttl_cache_seconds = ttl_cache_seconds
        self._dns_cache: dict[str, tuple[float, list[str]]] = {}

    def check_dns_rebinding(self, hostname: str) -> bool:
        """Check if hostname shows signs of DNS rebinding."""
        import time

        try:
            current_time = time.time()

            # Get cached result if fresh
            if hostname in self._dns_cache:
                cache_time, cached_ips = self._dns_cache[hostname]
                if current_time - cache_time < self.ttl_cache_seconds:
                    # Compare with current resolution
                    try:
                        result = socket.getaddrinfo(hostname, None)
                        current_ips = {addr[4][0] for addr in result}

                        if current_ips != set(cached_ips):
                            logger.warning(f"DNS_REBINDING detected: {hostname} changed from {cached_ips} to {current_ips}")
                            return True
                    except socket.gaierror:
                        pass

            # Cache current resolution
            result = socket.getaddrinfo(hostname, None)
            ips = [addr[4][0] for addr in result]
            self._dns_cache[hostname] = (current_time, ips)

            return False

        except Exception as e:
            logger.exception(f"DNS rebinding check error: {e}")
            return False
