"""Tests for the new PATCH endpoint request body models:

- ``JobWebhookUpdate``: validation of webhook_url format
- ``JobStrategyUpdate``: validation of fetch_strategy values
- ``JobCreate``: validation of new fields (webhook_url, webhook_secret, fetch_strategy)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import JobCreate, JobStrategyUpdate, JobWebhookUpdate


class TestJobWebhookUpdate:
    def test_valid_https_url(self) -> None:
        body = JobWebhookUpdate(webhook_url="https://example.com/hook")
        assert body.webhook_url == "https://example.com/hook"

    def test_valid_http_url(self) -> None:
        body = JobWebhookUpdate(webhook_url="http://example.com/hook")
        assert body.webhook_url == "http://example.com/hook"

    def test_url_is_stripped(self) -> None:
        body = JobWebhookUpdate(webhook_url="  https://example.com/hook  ")
        assert body.webhook_url == "https://example.com/hook"

    def test_none_url_accepted(self) -> None:
        body = JobWebhookUpdate(webhook_url=None)
        assert body.webhook_url is None

    def test_invalid_scheme_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            JobWebhookUpdate(webhook_url="ftp://example.com/hook")
        assert "webhook_url" in str(exc_info.value)

    def test_garbage_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JobWebhookUpdate(webhook_url="not-a-url")

    def test_secret_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JobWebhookUpdate(webhook_url="https://example.com", webhook_secret="x" * 200)


class TestJobStrategyUpdate:
    @pytest.mark.parametrize(
        "strategy",
        [
            "playwright_full",
            "playwright_stealth",
            "playwright_lightweight",
            "httpx_basic",
            "httpx_with_ua",
            "httpx_smart",
            "hybrid",
            "cached",
        ],
    )
    def test_valid_strategies_accepted(self, strategy: str) -> None:
        body = JobStrategyUpdate(fetch_strategy=strategy)
        assert body.fetch_strategy == strategy

    def test_empty_string_accepted_for_reset(self) -> None:
        body = JobStrategyUpdate(fetch_strategy="")
        assert body.fetch_strategy == ""

    def test_invalid_strategy_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            JobStrategyUpdate(fetch_strategy="not_a_strategy")
        assert "fetch_strategy" in str(exc_info.value)

    def test_strategy_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JobStrategyUpdate(fetch_strategy="x" * 100)


class TestJobCreateNewFields:
    def test_webhook_url_validation(self) -> None:
        # Valid URL works
        job = JobCreate(
            name="test",
            urls=["https://example.com"],
            webhook_url="https://example.com/hook",
        )
        assert job.webhook_url == "https://example.com/hook"

        # Invalid scheme rejected
        with pytest.raises(ValidationError):
            JobCreate(
                name="test",
                urls=["https://example.com"],
                webhook_url="file:///etc/passwd",
            )

    def test_fetch_strategy_validation(self) -> None:
        # Valid strategy works
        job = JobCreate(
            name="test",
            urls=["https://example.com"],
            fetch_strategy="playwright_full",
        )
        assert job.fetch_strategy == "playwright_full"

        # Empty strategy is auto-select, allowed
        job = JobCreate(
            name="test",
            urls=["https://example.com"],
            fetch_strategy="",
        )
        assert job.fetch_strategy == ""

        # Invalid strategy rejected
        with pytest.raises(ValidationError):
            JobCreate(
                name="test",
                urls=["https://example.com"],
                fetch_strategy="nonexistent_strategy",
            )

    def test_webhook_secret_optional(self) -> None:
        job = JobCreate(
            name="test",
            urls=["https://example.com"],
            webhook_url="https://example.com/hook",
            webhook_secret="my-secret",
        )
        assert job.webhook_secret == "my-secret"

        # Default is None
        job2 = JobCreate(
            name="test",
            urls=["https://example.com"],
        )
        assert job2.webhook_secret is None
