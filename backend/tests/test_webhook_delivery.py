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
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
            patch("asyncio.sleep", AsyncMock()),
        ):
            job = _FakeJob(webhook_url="https://example.com/hook")
            success = await deliver_webhook(job)

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


# ═══════════════════════════════════════════════════════════════════════
# Additional Coverage — Timeout, malformed payload, concurrent, auth
# ═══════════════════════════════════════════════════════════════════════


class TestExtendedWebhookDelivery:
    @pytest.mark.asyncio
    async def test_timeout_on_single_attempt_triggers_retry(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("connect timed out"))
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
            patch("asyncio.sleep", AsyncMock()),
        ):
            job = _FakeJob(webhook_url="https://example.com/hook")
            result = await deliver_webhook(job)

        assert result is False
        assert job.webhook_delivered is False
        assert mock_client.post.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_malformed_payload_does_not_crash(self) -> None:
        """Ensure deliver_webhook handles jobs with missing attributes gracefully."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.url_safety.get_safe_async_client", return_value=mock_ctx):
            job = MagicMock()
            job.webhook_url = "https://example.com/hook"
            job.webhook_secret = None
            job.id = "minimal-job"
            job.status = "completed"
            job.name = None
            job.total_records = 0
            job.filtered_records = None
            job.error = None
            job.created_at = None
            job.completed_at = None
            job.estimated_cost_usd = None
            job.webhook_delivered = False
            job.webhook_delivered_at = None

            result = await deliver_webhook(job)
            assert result is True

    @pytest.mark.asyncio
    async def test_timeout_then_success(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        ok_response = MagicMock()
        ok_response.status_code = 200
        call_count = 0

        async def _side(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                _msg = "first timeout"
                raise httpx.TimeoutException(_msg)
            return ok_response

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=_side)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
            patch("asyncio.sleep", AsyncMock()),
        ):
            job = _FakeJob(webhook_url="https://example.com/hook")
            result = await deliver_webhook(job)

        assert result is True
        assert job.webhook_delivered is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_deliveries_isolated(self) -> None:
        """Two webhook deliveries running concurrently should not interfere."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def _make_delivery(job_id: str, url: str) -> bool:
            mclient = MagicMock()
            mclient.post = AsyncMock(return_value=mock_response)
            mctx = MagicMock()
            mctx.__aenter__ = AsyncMock(return_value=mclient)
            mctx.__aexit__ = AsyncMock(return_value=None)

            with patch("app.url_safety.get_safe_async_client", return_value=mctx):
                job = _FakeJob(webhook_url=url, job_id=job_id, webhook_secret="sec")
                return await deliver_webhook(job)

        results = await asyncio.gather(
            _make_delivery("job-a", "https://hook-a.example.com"),
            _make_delivery("job-b", "https://hook-b.example.com"),
            _make_delivery("job-c", "https://hook-c.example.com"),
        )
        assert results == [True, True, True]

    @pytest.mark.asyncio
    async def test_no_secret_still_sends_content_type(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.url_safety.get_safe_async_client", return_value=mock_ctx):
            job = _FakeJob(webhook_url="https://example.com/hook", webhook_secret=None)
            await deliver_webhook(job)

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Content-Type"] == "application/json"
        assert "X-DataForge-Signature" not in headers

    @pytest.mark.asyncio
    async def test_success_with_auth_header_via_secret(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.url_safety.get_safe_async_client", return_value=mock_ctx):
            job = _FakeJob(webhook_url="https://example.com/hook", webhook_secret="my-secret-key")
            result = await deliver_webhook(job)

        assert result is True
        call_kwargs = mock_client.post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert "X-DataForge-Signature" in headers
        assert headers["X-DataForge-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_delivery_sends_user_agent(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.url_safety.get_safe_async_client", return_value=mock_ctx):
            job = _FakeJob(webhook_url="https://example.com/hook")
            await deliver_webhook(job)

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["User-Agent"] == "DataForge-Webhook/1.0"

    @pytest.mark.asyncio
    async def test_3xx_response_treated_as_success(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
            patch("asyncio.sleep", AsyncMock()),
        ):
            job = _FakeJob(webhook_url="https://example.com/hook")
            result = await deliver_webhook(job)

        assert result is True  # < 400 is treated as success
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_4xx_response_retried(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
            patch("asyncio.sleep", AsyncMock()),
        ):
            job = _FakeJob(webhook_url="https://example.com/hook")
            result = await deliver_webhook(job)

        assert result is False
        assert mock_client.post.call_count == MAX_RETRIES
