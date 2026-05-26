import pytest
import socket
from app.url_safety import validate_public_http_url, is_safe_ip
from app.config import settings

def test_is_safe_ip():
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
    assert is_safe_ip("0.0.0.0") is False
    assert is_safe_ip("169.254.169.254") is False
    assert is_safe_ip("224.0.0.1") is False
    assert is_safe_ip("240.0.0.0") is False

def test_validate_public_http_url_basic_safety():
    # Public domains should pass
    validate_public_http_url("http://google.com")
    validate_public_http_url("https://github.com/trending")
    
    # Unsafe schemes should fail
    with pytest.raises(ValueError, match="scheme"):
        validate_public_http_url("ftp://google.com")
    with pytest.raises(ValueError, match="scheme"):
        validate_public_http_url("file:///etc/passwd")
        
    # Unsafe explicit hosts should fail
    for host in ("localhost", "127.0.0.1", "[::1]", "0.0.0.0", "host.docker.internal"):
        with pytest.raises(ValueError, match="restricted local loopback target"):
            validate_public_http_url(f"http://{host}")
            
    # Metadata endpoints should fail
    for host in ("169.254.169.254", "metadata.google.internal", "instance-data"):
        with pytest.raises(ValueError, match="restricted cloud metadata endpoint"):
            validate_public_http_url(f"http://{host}")

def test_validate_public_http_url_dns_resolution(monkeypatch):
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

def test_validate_public_http_url_allowlist(monkeypatch):
    # Set ALLOWED_INTERNAL_HOSTS config override
    monkeypatch.setattr(settings, "ALLOWED_INTERNAL_HOSTS", "nginx,smoke-host")
    
    # These internal domains should now pass despite not resolving to a public IP
    validate_public_http_url("http://nginx/smoke/records.html")
    validate_public_http_url("https://smoke-host/index.html")
    
    # Other internal targets should still fail
    with pytest.raises(ValueError, match="restricted local loopback target"):
        validate_public_http_url("http://localhost")
