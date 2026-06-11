"""Unit tests for the async ``app.services.notifications`` TelegramNotifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.config import settings
from app.services.notifications import TelegramNotifier, get_telegram_notifier


@pytest.mark.asyncio
class TestNotificationsService:
    async def test_notifier_initialization(self) -> None:
        """Verify the notifier correctly reads settings fields."""
        notifier = TelegramNotifier()
        assert notifier.token == settings.TELEGRAM_BOT_TOKEN
        assert notifier.chat_id == settings.TELEGRAM_CHAT_ID
        assert notifier.enabled == settings.TELEGRAM_ENABLED

    async def test_send_message_disabled(self) -> None:
        """Verify send_message immediately returns if disabled."""
        notifier = TelegramNotifier()
        notifier.enabled = False
        notifier.token = "123:abc"
        notifier.chat_id = "999"

        with patch("httpx.AsyncClient.post") as mock_post:
            await notifier.send_message("Hello")
            mock_post.assert_not_called()

    async def test_send_message_missing_token_or_chat_id(self) -> None:
        """Verify send_message returns if token or chat_id is missing."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.token = ""
        notifier.chat_id = "999"

        with patch("httpx.AsyncClient.post") as mock_post:
            await notifier.send_message("Hello")
            mock_post.assert_not_called()

            notifier.token = "123:abc"
            notifier.chat_id = ""
            await notifier.send_message("Hello")
            mock_post.assert_not_called()

    async def test_send_message_success(self) -> None:
        """Verify send_message invokes httpx AsyncClient post with correct params."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.token = "123:abc"
        notifier.chat_id = "999"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await notifier.send_message("Hello Async Telegram")

            mock_post.assert_called_once_with(
                "https://api.telegram.org/bot123:abc/sendMessage",
                json={
                    "chat_id": "999",
                    "text": "Hello Async Telegram",
                    "parse_mode": "Markdown",
                },
            )
            mock_resp.raise_for_status.assert_called_once()
            await notifier.close()

    async def test_send_message_http_error(self) -> None:
        """Verify send_message catches HTTP errors and logs them (fail-safe)."""
        notifier = TelegramNotifier()
        notifier.enabled = True
        notifier.token = "123:abc"
        notifier.chat_id = "999"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=MagicMock(status_code=400),
            )
            # Should not raise
            await notifier.send_message("Hello Fail-Safe")
            mock_post.assert_called_once()
            await notifier.close()

    async def test_get_telegram_notifier_singleton(self) -> None:
        """Verify get_telegram_notifier returns the singleton instance."""
        notifier1 = get_telegram_notifier()
        notifier2 = get_telegram_notifier()
        assert notifier1 is notifier2
        assert isinstance(notifier1, TelegramNotifier)
