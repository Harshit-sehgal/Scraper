"""Tests for app.services.webhook_delivery — HMAC signing, retry, payload shape, and SSRF blocking."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from app.services.webhook_delivery import (
    MAX_RETRIES,
    _build_payload,
    _sign_payload,
    deliver_webhook,
)


class _FakeJob:
    """Minimal stand-in for a Job object used by webhook delivery."""

    def __init__(
        self,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        job_id: str = "job-1",
        status: str = "completed",
        total_records: int = 5,
    ) -> None:
        self.id = job_id
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.status = status
        self.name = "Test Job"
        self.total_records = total_records
        self.filtered_records = 5
        self.error = None
        self.created_at = "2026-01-01T00:00:00+00:00"
        self.completed_at = "2026-01-01T00:01:00+00:00"
        self.estimated_cost_usd = 0.0
        self.webhook_delivered = False
        self.webhook_delivered_at = None


class TestSignPayload:
    def test_sign_payload_returns_hmac_sha256_digest(self) -> None:
        payload = b'{"event": "test"}'
        secret = "secret-1"
        sig = _sign_payload(payload, secret)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == expected
        assert len(sig) == 64  # sha256 hex digest

    def test_sign_payload_different_secret_different_signature(self) -> None:
        payload = b'{"event": "test"}'
        sig1 = _sign_payload(payload, "secret-A")
        sig2 = _sign_payload(payload, "secret-B")
        assert sig1 != sig2


class TestBuildPayload:
    def test_payload_includes_event_job_id_status(self) -> None:
        job = _FakeJob(job_id="test-id", status="completed", total_records=10)
        payload = _build_payload(job)
        assert payload["event"] == "job.completed"
        assert payload["job_id"] == "test-id"
        assert payload["status"] == "completed"
        assert payload["total_records"] == 10
        assert "timestamp" in payload


class TestDeliverWebhook:
    @pytest.mark.asyncio
    async def test_no_webhook_url_returns_false(self) -> None:
        job = _FakeJob(webhook_url=None)
        assert await deliver_webhook(job) is False

    @pytest.mark.asyncio
    async def test_ssrf_blocked_url_returns_false(self) -> None:
        """Private IP URLs are rejected by validate_public_http_url before any HTTP call."""
        # 169.254.169.254 is the AWS metadata endpoint — a classic SSRF target.
        job = _FakeJob(webhook_url="http://169.254.169.254/latest/meta-data/")
        success = await deliver_webhook(job)
        assert success is False
        assert job.webhook_delivered is False

    @pytest.mark.asyncio
    async def test_ssrf_loopback_rejected(self) -> None:
        """Loopback addresses should be blocked."""
        job = _FakeJob(webhook_url="http://127.0.0.1:8080/callback")
        success = await deliver_webhook(job)
        assert success is False
        assert job.webhook_delivered is False

    @pytest.mark.asyncio
    async def test_ssrf_localhost_hostname_rejected(self) -> None:
        """'localhost' hostname should also be blocked."""
        job = _FakeJob(webhook_url="http://localhost:6379/")
        success = await deliver_webhook(job)
        assert success is False

    @pytest.mark.asyncio
    async def test_successful_delivery_updates_state(self) -> None:
        """Mocked successful POST via get_safe_async_client."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        # Patch the SSRF-safe client factory inside webhook_delivery
        with patch(
            "app.url_safety.get_safe_async_client",
            return_value=mock_ctx,
        ):
            job = _FakeJob(webhook_url="https://example.com/hook", webhook_secret="abc")
            success = await deliver_webhook(job)

        assert success is True
        assert job.webhook_delivered is True
        assert job.webhook_delivered_at is not None

        # Verify the request was made with correct body and signature
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "https://example.com/hook"
        body = call_args.kwargs["content"]
        assert b"job.completed" in body

        # Verify HMAC signature header is present and correct
        headers = call_args.kwargs["headers"]
        assert "X-DataForge-Signature" in headers
        sig_header = headers["X-DataForge-Signature"]
        assert sig_header.startswith("sha256=")
        expected_sig = hmac.new(b"abc", body, hashlib.sha256).hexdigest()
        assert sig_header.split("=")[1] == expected_sig

    @pytest.mark.asyncio
    async def test_failed_delivery_retries_then_returns_false(self) -> None:
        """A 500 response on every attempt should exhaust retries and return False."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.url_safety.get_safe_async_client",
            return_value=mock_ctx,
        ):
            original_sleep = asyncio.sleep
            asyncio.sleep = AsyncMock()  # type: ignore[assignment]
            try:
                job = _FakeJob(webhook_url="https://example.com/hook")
                success = await deliver_webhook(job)
            finally:
                asyncio.sleep = original_sleep  # type: ignore[assignment]

        assert success is False
        assert job.webhook_delivered is False

    @pytest.mark.asyncio
    async def test_no_signature_header_when_secret_absent(self) -> None:
        """Without a webhook_secret, no X-DataForge-Signature header is sent."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.url_safety.get_safe_async_client",
            return_value=mock_ctx,
        ):
            job = _FakeJob(webhook_url="https://example.com/hook", webhook_secret=None)
            await deliver_webhook(job)

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert "X-DataForge-Signature" not in headers
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_max_retries_constant_is_positive(self) -> None:
        assert MAX_RETRIES > 0
