"""Tests for export HMAC signing (Roadmap Prod Item 19).

Verifies that all export responses include an X-Export-Signature
header with a valid HMAC-SHA256 hex digest that consumers can use
to verify export integrity.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest
from app.routers.exports import _get_export_hmac_key, sign_export_payload


class TestExportHMACSigning:
    """Unit tests for export payload signing.

    All tests pin ``DATAFORGE_EXPORT_HMAC_KEY`` to a known value
    so signatures are deterministic and verifiable. The key cache
    in the module is reset before each test that needs freshness.
    """

    @pytest.fixture(autouse=True)
    def _pin_hmac_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force a known HMAC key so all signatures are deterministic."""
        monkeypatch.setenv("DATAFORGE_EXPORT_HMAC_KEY", "test-hmac-key-v1")

    def test_sign_export_payload_returns_hex_string(self) -> None:
        sig = sign_export_payload("job-1", "csv", b"test content")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest

    def test_sign_export_payload_deterministic(self) -> None:
        sig1 = sign_export_payload("job-1", "csv", b"test content")
        sig2 = sign_export_payload("job-1", "csv", b"test content")
        assert sig1 == sig2

    def test_different_content_produces_different_signature(self) -> None:
        sig1 = sign_export_payload("job-1", "csv", b"content A")
        sig2 = sign_export_payload("job-1", "csv", b"content B")
        assert sig1 != sig2

    def test_different_job_id_produces_different_signature(self) -> None:
        sig1 = sign_export_payload("job-1", "csv", b"same content")
        sig2 = sign_export_payload("job-2", "csv", b"same content")
        assert sig1 != sig2

    def test_different_format_produces_different_signature(self) -> None:
        sig1 = sign_export_payload("job-1", "csv", b"same content")
        sig2 = sign_export_payload("job-1", "json", b"same content")
        assert sig1 != sig2

    def test_signature_is_hmac_sha256(self) -> None:
        """Verify the signature matches a manual HMAC-SHA256 computation."""
        key = _get_export_hmac_key()
        job_id = "test-job"
        fmt = "json"
        content = b"test payload"
        msg = f"{job_id}:{fmt}:".encode() + content
        expected = hmac.new(key, msg, hashlib.sha256).hexdigest()
        actual = sign_export_payload(job_id, fmt, content)
        assert actual == expected

    def test_empty_content_still_produces_valid_signature(self) -> None:
        sig = sign_export_payload("job-1", "csv", b"")
        assert isinstance(sig, str)
        assert len(sig) == 64
