"""Tests for SSRF protocol rejection.

Roadmap: Rel 25 — URLs with file://, ftp://, dict://, gopher:// schemes,
verify SSRF guard rejects them before any network call.
"""

from __future__ import annotations

import pytest
from app.url_safety import validate_public_http_url


class TestSsrfProtocolRejection:
    def test_file_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            validate_public_http_url("file:///etc/passwd")

    def test_ftp_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            validate_public_http_url("ftp://example.com/file")

    def test_dict_scheme_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_public_http_url("dict://example.com")

    def test_gopher_scheme_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_public_http_url("gopher://example.com:7070/1")

    def test_http_scheme_allowed(self) -> None:
        validate_public_http_url("http://example.com")
        validate_public_http_url("https://example.com")

    def test_malicious_file_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_public_http_url("file://localhost/etc/shadow")

    def test_private_ip_over_http_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_public_http_url("http://192.168.1.1/admin")

    def test_localhost_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_public_http_url("http://localhost:8080/")

    def test_ssrf_precedes_network_call(self) -> None:
        from unittest.mock import patch

        with patch("app.url_safety.httpx.Client") as mock_client:
            with pytest.raises(ValueError):
                validate_public_http_url("ftp://attack.com/file")
            mock_client.assert_not_called()
