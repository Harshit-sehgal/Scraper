import logging

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Utility class for sending notifications via Telegram Bot API."""

    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = settings.TELEGRAM_ENABLED

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Sends a text message to the configured Telegram chat."""
        if not self.enabled or not self.token or not self.chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to send Telegram notification")
            return False
        else:
            return True

    def notify_test_start(self, suite_name: str):
        """Sends a notification when a test suite starts."""
        if not settings.TELEGRAM_NOTIFY_ON_TEST_START:
            return

        text = f"🚀 <b>Test Suite Started</b>\n\nSuite: <code>{suite_name}</code>"
        self.send_message(text)

    def notify_test_failure(self, test_name: str, error: str):
        """Sends a notification when a test fails."""
        if not settings.TELEGRAM_NOTIFY_ON_TEST_FAILURE:
            return

        error_display = f"{error[:500]}..." if len(error) > 500 else error
        text = f"❌ <b>Test Failure</b>\n\nTest: <code>{test_name}</code>\n\nError: <code>{error_display}</code>"
        self.send_message(text)

    def notify_test_end(self, suite_name: str, result: str, passed: int, failed: int, skipped: int):
        """Sends a summary notification when a test suite ends."""
        if not settings.TELEGRAM_NOTIFY_ON_TEST_END:
            return

        emoji = "✅" if result == "PASSED" else "❌"
        text = (
            f"{emoji} <b>Test Suite Finished</b>\n\n"
            f"Suite: <code>{suite_name}</code>\n"
            f"Result: <b>{result}</b>\n\n"
            f"✅ Passed: {passed}\n"
            f"❌ Failed: {failed}\n"
            f"⏭️ Skipped: {skipped}"
        )
        self.send_message(text)

    def notify_critical_error(self, error_msg: str):
        """Sends a notification for critical application errors."""
        if not settings.TELEGRAM_NOTIFY_ON_CRITICAL_ERROR:
            return

        text = f"🚨 <b>CRITICAL ERROR</b>\n\n<code>{error_msg[:1000]}</code>"
        self.send_message(text)


# Global instance for easy access
notifier = TelegramNotifier()
