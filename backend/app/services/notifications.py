import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Handles sending notifications via the Telegram Bot API."""

    def __init__(self) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = settings.TELEGRAM_ENABLED
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    async def send_message(self, text: str) -> None:
        """Send a simple text message to the connected chat."""
        if not self.enabled or not self.token or not self.chat_id:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}

        try:
            client = self._get_client()
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except Exception:
            logger.exception("Failed to send Telegram notification")


notifier = TelegramNotifier()
