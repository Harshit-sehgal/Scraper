"""F-NGINX-HEADERS-001 + F-NGINX-TLS-001.

Verifies nginx production config:
1. ``X-XSS-Protection`` header is present in ``security_headers.conf``
2. TLS cipher suites are Mozilla Intermediate (no 3DES, RC4, etc.)
3. TLS protocols enforce TLSv1.2 minimum
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_HEADERS = REPO_ROOT / "nginx" / "security_headers.conf"
NGINX_CONF = REPO_ROOT / "nginx.conf"


# Mozilla Intermediate cipher list (sorted, trimmed for verification)
MOZILLA_INTERMEDIATE_CIPHERS = {
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-CHACHA20-POLY1305",
    "DHE-RSA-AES128-GCM-SHA256",
    "DHE-RSA-AES256-GCM-SHA384",
}

# Forbidden ciphers (HIGH:!aNULL:!MD5 allowed these)
FORBIDDEN_CIPHERS = {
    "AES128-SHA",  # uses CBC
    "AES256-SHA",  # uses CBC
    "DES-CBC3-SHA",  # 3DES
    "RC4-SHA",  # RC4
    "RC4-MD5",  # RC4
}


class TestSecurityHeaders:
    def test_file_exists(self) -> None:
        assert SECURITY_HEADERS.is_file(), f"missing {SECURITY_HEADERS}"

    def test_xss_protection_header_present(self) -> None:
        text = SECURITY_HEADERS.read_text(encoding="utf-8")
        assert "X-XSS-Protection" in text, "X-XSS-Protection header must be in security_headers.conf"
        assert "mode=block" in text, "X-XSS-Protection must use mode=block"

    def test_x_frame_options_present(self) -> None:
        text = SECURITY_HEADERS.read_text(encoding="utf-8")
        assert "X-Frame-Options" in text

    def test_content_type_options_present(self) -> None:
        text = SECURITY_HEADERS.read_text(encoding="utf-8")
        assert "X-Content-Type-Options" in text
        assert "nosniff" in text


class TestTlsCiphers:
    def test_nginx_conf_exists(self) -> None:
        assert NGINX_CONF.is_file(), f"missing {NGINX_CONF}"

    def test_no_high_cipher_alias(self) -> None:
        """The old ``HIGH:!aNULL:!MD5`` alias must not appear anywhere."""
        text = NGINX_CONF.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "ssl_ciphers" in line:
                assert "HIGH:!aNULL" not in line, f"ssl_ciphers still uses HIGH alias: {line.strip()}"

    def test_forbidden_ciphers_absent(self) -> None:
        text = NGINX_CONF.read_text(encoding="utf-8")
        for cipher in FORBIDDEN_CIPHERS:
            assert cipher not in text, f"forbidden cipher {cipher} still in nginx.conf"

    def test_mozilla_intermediate_present(self) -> None:
        """At least one Mozilla-Intermediate cipher must appear."""
        text = NGINX_CONF.read_text(encoding="utf-8")
        assert any(cipher in text for cipher in MOZILLA_INTERMEDIATE_CIPHERS), (
            f"no Mozilla Intermediate cipher found. Expected at least one of: {sorted(MOZILLA_INTERMEDIATE_CIPHERS)}"
        )

    def test_tls_protocol_minimum_tlsv12(self) -> None:
        text = NGINX_CONF.read_text(encoding="utf-8")
        # Find ssl_protocols lines and ensure TLSv1.2 is included
        protocol_lines = [line for line in text.splitlines() if "ssl_protocols" in line]
        assert protocol_lines, "no ssl_protocols directives found"
        for line in protocol_lines:
            assert "TLSv1.2" in line, f"ssl_protocols must include TLSv1.2: {line.strip()}"
            # Verify that TLSv1.0 and TLSv1.1 are not re-enabled
            assert "TLSv1.0" not in line, "TLSv1.0 must not be re-enabled"
            assert "TLSv1.1" not in line, "TLSv1.1 must not be re-enabled"
