from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest


def _check_curl_cffi_available() -> bool:
    """Check if curl_cffi is available (used by TLS fingerprint layer)."""
    try:
        importlib.import_module("curl_cffi")
        return True
    except ImportError:
        return False


def _validate_tls_config(
    min_tls_version: str = "1.2",
    max_tls_version: str = "1.3",
    cipher_filter: str = "ECDHE",
    disable_ocsp: bool = False,
) -> dict[str, bool]:
    """Validate TLS fingerprint configuration parameters."""
    errors: dict[str, bool] = {}
    valid_versions = {"1.0", "1.1", "1.2", "1.3"}
    if min_tls_version not in valid_versions:
        errors["min_tls_version"] = True
    if max_tls_version not in valid_versions:
        errors["max_tls_version"] = True
    if min_tls_version and max_tls_version and min_tls_version > max_tls_version:
        errors["version_order"] = True
    valid_ciphers = {"ECDHE", "AES", "CHACHA20", "DEFAULT"}
    if cipher_filter and cipher_filter not in valid_ciphers:
        errors["cipher_filter"] = True
    return errors


class TestTLSAvailabilityDetection:
    """Anti 4: Detect when TLS fingerprint libraries are available."""

    def test_curl_cffi_not_available_by_default(self) -> None:
        result = _check_curl_cffi_available()
        assert result is False

    def test_curl_cffi_detection_no_error(self) -> None:
        try:
            _check_curl_cffi_available()
        except ImportError:
            pytest.fail("_check_curl_cffi_available raised ImportError")

    def test_availability_after_mock_import(self) -> None:
        fake_module = type(sys)("curl_cffi")
        fake_module.Curl = "fake"
        with patch.dict(sys.modules, {"curl_cffi": fake_module}):
            assert _check_curl_cffi_available() is True


class TestTLSConfigValidation:
    """Anti 4: Validate TLS fingerprint configuration."""

    def test_valid_config_returns_no_errors(self) -> None:
        errors = _validate_tls_config("1.2", "1.3", "ECDHE", False)
        assert errors == {}

    def test_invalid_min_version_returns_error(self) -> None:
        errors = _validate_tls_config("0.5", "1.3")
        assert "min_tls_version" in errors

    def test_invalid_max_version_returns_error(self) -> None:
        errors = _validate_tls_config("1.2", "9.9")
        assert "max_tls_version" in errors

    def test_version_order_inversion_returns_error(self) -> None:
        errors = _validate_tls_config("1.3", "1.2")
        assert "version_order" in errors

    def test_invalid_cipher_filter_returns_error(self) -> None:
        errors = _validate_tls_config(cipher_filter="INVALID_CIPHER")
        assert "cipher_filter" in errors

    def test_minimal_config_is_valid(self) -> None:
        errors = _validate_tls_config("1.2", "1.3")
        assert errors == {}

    def test_all_defaults_are_valid(self) -> None:
        errors = _validate_tls_config()
        assert errors == {}
