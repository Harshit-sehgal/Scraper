import socket
import ipaddress
from urllib.parse import urlparse
from app.config import settings

def is_safe_ip(ip_str: str) -> bool:
    """Return True if the IP address is a public, routable IP address.
    
    Rejects loopback, private, link-local, multicast, reserved, etc.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check standard unsafe ranges:
        if (ip.is_private or 
            ip.is_loopback or 
            ip.is_link_local or 
            ip.is_multicast or 
            ip.is_reserved or 
            ip.is_unspecified):
            return False
        return True
    except ValueError:
        return False

def validate_public_http_url(url: str) -> None:
    """Raise ValueError if the URL resolves to or points to a private/internal network target.
    
    Allows configured internal hosts via settings.ALLOWED_INTERNAL_HOSTS (e.g. 'nginx' for compose tests).
    """
    if not url:
        raise ValueError("URL cannot be empty")
        
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not supported. Only http and https are allowed.")
        
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL '{url}' does not contain a valid hostname.")
        
    # Lowercase for safe comparison
    hostname_lower = hostname.lower()
    
    # 1. Allowlist override check (for local integration / Docker smoke test)
    import os
    is_smoke = os.getenv("DATAFORGE_SMOKE_TEST_MODE", "").lower() in ("true", "1", "yes")
    if is_smoke:
        allowed_hosts = [h.strip().lower() for h in settings.ALLOWED_INTERNAL_HOSTS.split(",") if h.strip()]
        if hostname_lower in allowed_hosts:
            return
        
    # 2. Reject explicit loopback/internal names
    if hostname_lower in ("localhost", "host.docker.internal", "[::1]", "::1", "0.0.0.0", "127.0.0.1"):
        raise ValueError(f"URL hostname '{hostname}' is a restricted local loopback target.")
        
    # 3. Reject cloud metadata endpoints specifically
    if hostname_lower in ("169.254.169.254", "metadata.google.internal", "instance-data"):
        raise ValueError(f"URL hostname '{hostname}' is a restricted cloud metadata endpoint.")
        
    # 4. Try DNS resolution to check resolved IPs
    try:
        addrs = socket.getaddrinfo(hostname, None)
        for addr in addrs:
            ip = addr[4][0]
            if not is_safe_ip(ip):
                raise ValueError(
                    f"URL hostname '{hostname}' resolves to restricted IP {ip} — rejected for security (SSRF protection)."
                )
    except (socket.gaierror, OSError):
        is_production = settings.ENV.lower() in ("production", "staging")
        if is_production and not is_smoke:
            raise ValueError(
                f"URL hostname '{hostname}' could not be resolved (DNS failure) — rejected in production for security."
            )
        pass
