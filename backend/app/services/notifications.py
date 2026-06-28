import logging
import threading

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
        # L1: protect lazy client init from races when multiple coroutines
        # call _get_client() concurrently — without a guard two callers
        # can both observe None, both build a client, and leak the loser.
        self._client_lock = threading.Lock()

    def _get_client(self) -> httpx.AsyncClient:
        # Fast-path: client already alive — no lock needed for the common
        # case where the singleton was initialised on a prior call.
        client = self._client
        if client is not None and not client.is_closed:
            return client
        with self._client_lock:
            # Re-check under lock so only the first racer builds a client.
            client = self._client
            if client is None or client.is_closed:
                from app.url_safety import get_safe_async_client

                client = get_safe_async_client(timeout=30.0)
                self._client = client
            return client

    async def send_message(self, text: str) -> None:
        """Send a simple text message to the connected chat."""
        if not self.enabled or not self.token or not self.chat_id:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}

        try:
            client = self._get_client()
            response = await client.post(url, json=payload)
            try:
                response.raise_for_status()
            finally:
                # H5: always release the response back to the pool
                # before the function exits — the previous pattern let
                # undetermined responses pile up under failure paths.
                await response.aclose()
        except Exception:
            logger.exception("Failed to send Telegram notification")

    async def close(self) -> None:
        """Close the underlying HTTP client to release sockets."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


notifier = TelegramNotifier()


def get_telegram_notifier() -> TelegramNotifier:
    """Return the module-level singleton notifier."""
    return notifier
