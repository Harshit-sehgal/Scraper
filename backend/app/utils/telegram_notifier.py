"""Telegram bot notification utility.

This module provides a single :class:`TelegramNotifier` that wraps the
Telegram Bot API ``sendMessage`` endpoint. The notifier is designed to
be **fail-safe**:

* When ``TELEGRAM_ENABLED`` is false, or the bot token / chat ID are
  missing or still set to placeholder values from ``.env.example``, the
  notifier silently short-circuits. No HTTP call is made.
* Network errors and 4xx/5xx responses are logged but **never** raised.
  A flaky Telegram API cannot interrupt a test run or the live scraper.
* High-level helpers (``notify_test_start`` etc.) post to a daemon
  thread, so the caller is never blocked.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)

# Placeholder values treated as "not configured". A half-filled .env
# must not produce noisy 401s against the real Telegram API.
_PLACEHOLDER_TOKENS = frozenset({"", "YOUR_BOT_TOKEN_HERE", "your_bot_token_here"})
_PLACEHOLDER_CHAT_IDS = frozenset({"", "YOUR_CHAT_ID_HERE", "your_chat_id_here"})

# Module-level lock + cache for the lazy notifier singleton. The cache
# exists so tests that monkey-patch ``settings.TELEGRAM_*`` can call
# :func:`reset_notifier` to force a fresh read on the next access.
_NOTIFIER_LOCK = threading.Lock()
_NOTIFIER_INSTANCE: TelegramNotifier | None = None


def _env(name: str, default: str = "") -> str:
    """Read an env var, falling back to ``default`` if unset or empty.

    The notifier accepts three naming conventions so the same bot can be
    used everywhere (local dev, CI, and the live scraper):

    1. **Canonical** ``DATAFORGE_TELEGRAM_*`` (the documented form)
    2. **Standard** ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID`` (also
       accepted by ``app.config._communication.CommunicationSettings``)
    3. **CI workflow aliases** ``TELEGRAM_TOKEN`` / ``TELEGRAM_TO`` (the
       names already used by the GitHub Actions ``appleboy/telegram-action``
       job, so the existing bot is reused without re-creating it)

    Resolution order: standard → CI alias → canonical → default. The
    standard name wins because the project also reads it via the
    Pydantic settings layer, and the two layers must agree.
    """
    # Standard Pydantic-settings name
    val = os.getenv(name)
    if val:
        return val
    # CI workflow aliases — must come before the canonical
    # DATAFORGE_* alias so that ``TELEGRAM_TOKEN`` is treated as the
    # *bot token* and not as ``DATAFORGE_TELEGRAM_TOKEN`` would imply.
    if name == "TELEGRAM_BOT_TOKEN":
        val = os.getenv("TELEGRAM_TOKEN")
        if val:
            return val
    elif name == "TELEGRAM_CHAT_ID":
        val = os.getenv("TELEGRAM_TO")
        if val:
            return val
    elif name == "TELEGRAM_ENABLED":
        val = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED") or os.getenv("TELEGRAM_ENABLE_NOTIFICATIONS")
        if val:
            return val
    # Canonical DATAFORGE_-prefixed alias
    prefixed = os.getenv(f"DATAFORGE_{name}")
    return prefixed if prefixed is not None else default


class TelegramNotifier:
    """Lightweight wrapper around the Telegram Bot API.

    The notifier is constructed from environment variables (and the
    cached Pydantic ``settings`` object). It performs no I/O at
    construction time, so building one is always safe.
    """

    def __init__(self) -> None:
        # Re-read at construction time so test monkey-patching of
        # ``settings.TELEGRAM_*`` is honoured when the cache is reset.
        self.token: str = _env("TELEGRAM_BOT_TOKEN") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        self.chat_id: str = _env("TELEGRAM_CHAT_ID") or getattr(settings, "TELEGRAM_CHAT_ID", "")
        self.enabled: bool = bool(_env("TELEGRAM_ENABLED") or getattr(settings, "TELEGRAM_ENABLED", False))
        self.api_base: str = (
            _env("TELEGRAM_API_BASE") or getattr(settings, "TELEGRAM_API_BASE", "https://api.telegram.org")
        ).rstrip("/")

    @property
    def is_configured(self) -> bool:
        """Return True only if the bot is enabled and credentials look real."""
        if not self.enabled:
            return False
        if self.token in _PLACEHOLDER_TOKENS or self.chat_id in _PLACEHOLDER_CHAT_IDS:
            return False
        # Telegram bot tokens are shaped "<digits>:<alnum>". A missing
        # colon almost always means a placeholder was filled with the
        # wrong value.
        return ":" in self.token

    @property
    def status(self) -> str:
        """Human-readable status string for logs and CLI output."""
        if not self.enabled:
            return "disabled (set DATAFORGE_TELEGRAM_ENABLED=true to enable)"
        if not self.is_configured:
            return "misconfigured (check DATAFORGE_TELEGRAM_BOT_TOKEN / _CHAT_ID)"
        return f"enabled (chat_id={self.chat_id})"

    # ─── Core transport ──────────────────────────────────────────────
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Synchronously send ``text`` to the configured chat.

        Returns True on a 2xx response, False otherwise (including when
        the notifier is not configured, the text is empty, or the
        network call fails). Never raises.
        """
        if not self.is_configured:
            logger.debug("Telegram notifier not configured; skipping message")
            return False
        if not text:
            return False

        url = f"{self.api_base}/bot{self.token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
        except requests.RequestException:
            logger.exception("Telegram send_message network error")
            return False

        if response.status_code >= 400:
            logger.warning(
                "Telegram send_message HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True

    # ─── Threaded high-level helpers (fire-and-forget) ───────────────
    def _fire_and_forget(self, text: str) -> None:
        """Send ``text`` in a daemon thread; never raise to the caller."""

        def _runner() -> None:
            try:
                self.send_message(text)
            except Exception:
                logger.exception("Telegram background send failed")

        thread = threading.Thread(target=_runner, name="telegram-notifier", daemon=True)
        thread.start()

    def notify_test_start(self, suite_name: str) -> None:
        """Notify that a test suite has started."""
        if not getattr(settings, "TELEGRAM_NOTIFY_ON_TEST_START", True):
            return
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        text = f"🚀 <b>Test Suite Started</b>\n\nSuite: <code>{suite_name}</code>\nStarted: <code>{ts}</code>"
        self._fire_and_forget(text)

    def notify_test_failure(self, test_name: str, error: str) -> None:
        """Notify that a single test has failed."""
        if not getattr(settings, "TELEGRAM_NOTIFY_ON_TEST_FAILURE", True):
            return
        # Telegram messages cap at 4096 chars; keep error well under.
        if len(error) > 800:
            error = error[:800] + "…"
        text = f"❌ <b>Test Failure</b>\n\nTest: <code>{test_name}</code>\n\nError:\n<pre><code>{error}</code></pre>"
        self._fire_and_forget(text)

    def notify_test_end(  # noqa: PLR0913
        self,
        suite_name: str,
        result: str,
        passed: int,
        failed: int,
        skipped: int,
        duration_seconds: float | None = None,
    ) -> None:
        """Notify that a test suite has finished, with a pass/fail summary."""
        if not getattr(settings, "TELEGRAM_NOTIFY_ON_TEST_END", True):
            return
        emoji = "✅" if result.upper() == "PASSED" else "❌"
        total = passed + failed + skipped
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        duration_block = f"⏱ Duration: <code>{duration_seconds:.1f}s</code>\n" if duration_seconds is not None else ""
        text = (
            f"{emoji} <b>Test Suite Finished</b>\n\n"
            f"Suite: <code>{suite_name}</code>\n"
            f"Result: <b>{result.upper()}</b>\n"
            f"Finished: <code>{ts}</code>\n"
            f"{duration_block}\n"
            f"Total: <b>{total}</b>\n"
            f"✅ Passed: <b>{passed}</b>\n"
            f"❌ Failed: <b>{failed}</b>\n"
            f"⏭️ Skipped: <b>{skipped}</b>"
        )
        self._fire_and_forget(text)

    def notify_critical_error(self, error_msg: str) -> None:
        """Notify on critical application errors."""
        if not getattr(settings, "TELEGRAM_NOTIFY_ON_CRITICAL_ERROR", True):
            return
        if len(error_msg) > 1500:
            error_msg = error_msg[:1500] + "…"
        text = f"🚨 <b>CRITICAL ERROR</b>\n\n<pre><code>{error_msg}</code></pre>"
        self._fire_and_forget(text)

    def send_now(self, text: str, parse_mode: str = "HTML") -> bool:
        """Synchronous send. Returns True on success, False on any error.

        Identical to :meth:`send_message`; the separate name exists so
        the CLI helper script can make its intent obvious.
        """
        return self.send_message(text, parse_mode=parse_mode)


def get_notifier() -> TelegramNotifier:
    """Return a lazily-constructed module-level notifier.

    Tests that monkey-patch ``settings.TELEGRAM_*`` should call
    :func:`reset_notifier` afterwards so the next call picks up the
    new values.
    """
    global _NOTIFIER_INSTANCE
    with _NOTIFIER_LOCK:
        if _NOTIFIER_INSTANCE is None:
            _NOTIFIER_INSTANCE = TelegramNotifier()
        return _NOTIFIER_INSTANCE


def reset_notifier() -> None:
    """Drop the cached notifier instance (test / CLI helper)."""
    global _NOTIFIER_INSTANCE
    with _NOTIFIER_LOCK:
        _NOTIFIER_INSTANCE = None


# Backwards-compatible module-level singleton. New code should prefer
# :func:`get_notifier` so that monkey-patched settings are honoured.
notifier = get_notifier()
