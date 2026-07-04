"""Tests for webhook delivery retry with exponential backoff (Feat 10).

Covers:
- Success on first attempt
- Success on retry (second attempt)
- All retries exhausted
- Transient network errors (ConnectError, TimeoutException, TimeoutError)
- HMAC signature verification
- Exponential backoff delays (1 s, 5 s, 25 s envelope)
- Tenant isolation guard
"""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services.webhook_delivery import (
    _BACKOFF_MULTIPLIER,
    _INITIAL_BACKOFF_SECONDS,
    BACKOFF_SEQUENCE_SECONDS,
    MAX_RETRIES,
    _build_payload,
    _sign_payload,
    _tenant_matches,
    deliver_webhook,
)

# ---------------------------------------------------------------------------
# Fake job stand-in
# ---------------------------------------------------------------------------


class _FakeJob:
    """Minimal stand-in for a Job object used by webhook delivery."""

    def __init__(
        self,
        webhook_url: str | None = "https://example.com/hook",
        webhook_secret: str | None = None,
        job_id: str = "feat10-job",
        status: str = "completed",
        total_records: int = 5,
        created_by: str = "user-1",
        org_id: str = "",
        project_id: str = "",
    ) -> None:
        self.id = job_id
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.status = status
        self.name = "Feat10 Test Job"
        self.total_records = total_records
        self.filtered_records = total_records
        self.error = None
        self.created_at = "2026-01-01T00:00:00+00:00"
        self.completed_at = "2026-01-01T00:01:00+00:00"
        self.estimated_cost_usd = 0.0
        self.webhook_delivered = False
        self.webhook_delivered_at = None
        self.created_by = created_by
        self.org_id = org_id
        self.project_id = project_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ok_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    # Round-11 fix: ``_deliver_webhook`` now calls ``await resp.aclose()``
    # to release the httpx Response connection-pool slot. The mock must
    # provide an awaitable aclose.
    resp.aclose = AsyncMock(return_value=None)
    return resp


def _mock_client_context(post_return: object) -> tuple[MagicMock, MagicMock]:
    """Return (mock_client, mock_ctx) where mock_ctx is a context manager."""
    mock_client = MagicMock()
    mock_client.post = (
        AsyncMock(return_value=post_return) if not isinstance(post_return, list) else AsyncMock(side_effect=post_return)
    )
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return mock_client, mock_ctx


# ---------------------------------------------------------------------------
# 1. Success on first attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_attempt_success_no_retry() -> None:
    """A 200 response on the first POST should return True with exactly 1 call."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is True
    assert job.webhook_delivered is True
    assert job.webhook_delivered_at is not None


# ---------------------------------------------------------------------------
# 2. Success on retry (second attempt)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_succeeds_on_second_attempt_after_500() -> None:
    """A 500 then 200: second attempt succeeds, returns True, exactly 2 calls."""
    responses = [_mock_ok_response(500), _mock_ok_response(200)]
    mock_client, mock_ctx = _mock_client_context(responses)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is True
    assert job.webhook_delivered is True
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_succeeds_on_third_attempt_after_two_failures() -> None:
    """Two 500 responses followed by a 200: third attempt succeeds."""
    responses = [_mock_ok_response(500), _mock_ok_response(502), _mock_ok_response(200)]
    mock_client, mock_ctx = _mock_client_context(responses)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is True
    assert job.webhook_delivered is True
    assert mock_client.post.call_count == 3


# ---------------------------------------------------------------------------
# 3. All retries exhausted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_retries_exhausted_returns_false() -> None:
    """3 attempts, all returning 500: returns False, exactly MAX_RETRIES calls."""
    mock_client, mock_ctx = _mock_client_context(_mock_ok_response(500))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is False
    assert job.webhook_delivered is False
    assert job.webhook_delivered_at is None
    assert mock_client.post.call_count == MAX_RETRIES


# ---------------------------------------------------------------------------
# 4. Transient network errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_connect_error() -> None:
    """ConnectError is a transient error; should retry up to MAX_RETRIES."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is False
    assert mock_client.post.call_count == MAX_RETRIES


@pytest.mark.asyncio
async def test_retry_on_timeout_exception() -> None:
    """httpx.TimeoutException is a transient error; should retry."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Read timeout"))
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is False
    assert mock_client.post.call_count == MAX_RETRIES


@pytest.mark.asyncio
async def test_retry_on_stdlib_timeout_error() -> None:
    """stdlib TimeoutError is a transient error; should retry."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=TimeoutError("asyncio timeout"))
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is False
    assert mock_client.post.call_count == MAX_RETRIES


@pytest.mark.asyncio
async def test_succeeds_after_transient_connect_error() -> None:
    """First attempt ConnectError, second 200: delivery succeeds on retry."""
    responses = [httpx.ConnectError("refused"), _mock_ok_response(200)]
    mock_client = MagicMock()

    async def _side_effect(*args: object, **kwargs: object) -> object:
        item = responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    mock_client.post = AsyncMock(side_effect=_side_effect)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob()
        result = await deliver_webhook(job)

    assert result is True
    assert job.webhook_delivered is True
    assert mock_client.post.call_count == 2


# ---------------------------------------------------------------------------
# 5. HMAC signature verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hmac_signature_header_present_and_correct() -> None:
    """When webhook_secret is set, the X-DataForge-Signature header matches."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob(webhook_secret="test-secret")
        result = await deliver_webhook(job)

    assert result is True
    call_kwargs = mock_ctx.__aenter__.return_value.post.call_args.kwargs
    headers = call_kwargs["headers"]
    body = call_kwargs["content"]

    assert "X-DataForge-Signature" in headers
    sig_value = headers["X-DataForge-Signature"]
    assert sig_value.startswith("sha256=")

    # Verify the HMAC is correct by recomputing
    expected_digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    actual_digest = sig_value.split("=", 1)[1]
    assert hmac.compare_digest(actual_digest, expected_digest)


@pytest.mark.asyncio
async def test_no_signature_header_when_secret_absent() -> None:
    """Without a webhook_secret, no X-DataForge-Signature header is sent."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob(webhook_secret=None)
        await deliver_webhook(job)

    call_kwargs = mock_ctx.__aenter__.return_value.post.call_args.kwargs
    headers = call_kwargs["headers"]
    assert "X-DataForge-Signature" not in headers
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_sign_payload_utility_correct() -> None:
    """_sign_payload matches a manual HMAC-SHA256 computation."""
    body = b'{"event": "job.completed"}'
    secret = "my-secret"
    sig = _sign_payload(body, secret)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, expected)


# ---------------------------------------------------------------------------
# 6. Exponential backoff delays (1 s, 5 s, 25 s envelope)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backoff_sequence_matches_spec() -> None:
    """BACKOFF_SEQUENCE_SECONDS should be (1.0, 5.0, 25.0)."""
    assert BACKOFF_SEQUENCE_SECONDS[0] == 1.0
    assert BACKOFF_SEQUENCE_SECONDS[1] == 5.0
    assert BACKOFF_SEQUENCE_SECONDS[2] == 25.0


@pytest.mark.asyncio
async def test_backoff_multiplier_is_five() -> None:
    """_BACKOFF_MULTIPLIER must be 5.0 for the 1/5/25 envelope."""
    assert _BACKOFF_MULTIPLIER == 5.0


@pytest.mark.asyncio
async def test_exponential_sleep_delays_increase() -> None:
    """Between retries, the sleep delays must increase exponentially."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(500))

    sleep_delays: list[float] = []

    async def tracking_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", tracking_sleep),
    ):
        job = _FakeJob()
        await deliver_webhook(job)

    # With MAX_RETRIES=3, there are 2 sleeps: 1.0 and 5.0
    assert len(sleep_delays) == MAX_RETRIES - 1
    if len(sleep_delays) >= 1:
        assert sleep_delays[0] == _INITIAL_BACKOFF_SECONDS
    if len(sleep_delays) >= 2:
        assert sleep_delays[1] == _INITIAL_BACKOFF_SECONDS * _BACKOFF_MULTIPLIER


# ---------------------------------------------------------------------------
# 7. Tenant isolation guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_mismatch_refuses_delivery() -> None:
    """When caller_identity doesn't match the job owner, delivery is refused."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob(created_by="user-A", org_id="org-X")
        result = await deliver_webhook(job, caller_identity=("user-B", "org-Y", ""))

    assert result is False
    assert job.webhook_delivered is False
    # No POST should have been made
    mock_ctx.__aenter__.return_value.post.assert_not_called()


@pytest.mark.asyncio
async def test_tenant_match_allows_delivery() -> None:
    """When caller_identity matches the job owner, delivery proceeds."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob(created_by="user-A", org_id="org-X")
        result = await deliver_webhook(job, caller_identity=("user-A", "org-X", ""))

    assert result is True
    assert job.webhook_delivered is True


@pytest.mark.asyncio
async def test_tenant_org_match_allows_delivery() -> None:
    """When caller org_id matches the job org_id, delivery proceeds."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob(created_by="user-A", org_id="org-X")
        # Different user_id but same org_id
        result = await deliver_webhook(job, caller_identity=("user-B", "org-X", ""))

    assert result is True


@pytest.mark.asyncio
async def test_no_caller_identity_allows_delivery() -> None:
    """Without caller_identity (None), delivery proceeds (backward compat)."""
    _, mock_ctx = _mock_client_context(_mock_ok_response(200))

    with (
        patch("app.url_safety.get_safe_async_client", return_value=mock_ctx),
        patch("asyncio.sleep", AsyncMock()),
    ):
        job = _FakeJob(created_by="user-A", org_id="org-X")
        result = await deliver_webhook(job)

    assert result is True


def test_tenant_matches_utility() -> None:
    """_tenant_matches correctly evaluates identity tuples."""
    # user_id match
    assert _tenant_matches("user-A", "", "", "user-A", "", "") is True
    # org_id match
    assert _tenant_matches("", "org-X", "", "", "org-X", "") is True
    # project_id match
    assert _tenant_matches("", "", "proj-1", "", "", "proj-1") is True
    # no match
    assert _tenant_matches("user-A", "org-X", "", "user-B", "org-Y", "") is False
    # empty caller rejected
    assert _tenant_matches("", "", "", "user-A", "org-X", "") is False


# ---------------------------------------------------------------------------
# 8. Payload structure
# ---------------------------------------------------------------------------


def test_build_payload_contains_required_fields() -> None:
    """_build_payload must include event, job_id, status, total_records."""
    job = _FakeJob(job_id="abc", status="completed", total_records=42)
    payload = _build_payload(job)
    assert payload["event"] == "job.completed"
    assert payload["job_id"] == "abc"
    assert payload["status"] == "completed"
    assert payload["total_records"] == 42
    assert "timestamp" in payload
