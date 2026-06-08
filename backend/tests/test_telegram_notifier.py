"""Unit tests for ``app.utils.telegram_notifier``.

The tests deliberately mock ``requests.post`` so that they can run in
CI without contacting the real Telegram API. The notifier is also
exercised end-to-end via the conftest hooks in
``backend/tests/conftest.py`` — but those are guarded behind
``TELEGRAM_ENABLED`` and so are no-ops in default test runs.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest
from app.utils import telegram_notifier as tn
from app.utils.telegram_notifier import TelegramNotifier, get_notifier, reset_notifier


# ─── Fixtures ───────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Reset the notifier cache and any Telegram env vars between tests."""
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ENABLED",
        "DATAFORGE_TELEGRAM_BOT_TOKEN",
        "DATAFORGE_TELEGRAM_CHAT_ID",
        "DATAFORGE_TELEGRAM_ENABLED",
        "DATAFORGE_TELEGRAM_API_BASE",
    ):
        monkeypatch.delenv(var, raising=False)
    reset_notifier()
    yield
    reset_notifier()


def _make_enabled(token: str = "123456:ABCDEFG", chat_id: str = "999") -> TelegramNotifier:  # noqa: S107
    """Build a fully-enabled notifier using direct env-var injection."""
    import os

    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["TELEGRAM_CHAT_ID"] = chat_id
    os.environ["TELEGRAM_ENABLED"] = "true"
    return TelegramNotifier()


# ─── Configuration ─────────────────────────────────────────────────
class TestConfiguration:
    def test_disabled_by_default(self):
        n = TelegramNotifier()
        assert n.is_configured is False
        assert n.send_message("hi") is False

    def test_enabled_but_missing_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        n = TelegramNotifier()
        assert n.is_configured is False
        assert "disabled" in n.status or "misconfigured" in n.status

    def test_placeholder_token_is_rejected(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        n = TelegramNotifier()
        assert n.is_configured is False

    def test_token_without_colon_is_rejected(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "notavalidtoken")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        n = TelegramNotifier()
        assert n.is_configured is False

    def test_prefixed_env_vars_are_honoured(self, monkeypatch):
        monkeypatch.setenv("DATAFORGE_TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_BOT_TOKEN", "123:abc")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_CHAT_ID", "42")
        n = TelegramNotifier()
        assert n.is_configured is True
        assert n.chat_id == "42"
        assert n.token == "123:abc"

    def test_unprefixed_env_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:legacy")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_BOT_TOKEN", "123:prefixed")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        n = TelegramNotifier()
        assert n.token == "123:legacy"


# ─── send_message ──────────────────────────────────────────────────
class TestSendMessage:
    def test_returns_false_when_not_configured(self):
        n = TelegramNotifier()
        with patch("app.utils.telegram_notifier.requests.post") as post:
            assert n.send_message("hi") is False
            post.assert_not_called()

    def test_returns_false_on_empty_text(self):
        n = _make_enabled()
        with patch("app.utils.telegram_notifier.requests.post") as post:
            assert n.send_message("") is False
            post.assert_not_called()

    def test_returns_true_on_2xx(self):
        n = _make_enabled()
        response = MagicMock(status_code=200, text="{}")
        with patch("app.utils.telegram_notifier.requests.post", return_value=response) as post:
            assert n.send_message("hello") is True
            post.assert_called_once()
            url = post.call_args.args[0]
            assert url == "https://api.telegram.org/bot123456:ABCDEFG/sendMessage"
            payload = post.call_args.kwargs["json"]
            assert payload["chat_id"] == "999"
            assert payload["text"] == "hello"
            assert payload["parse_mode"] == "HTML"
            assert payload["disable_web_page_preview"] is True

    def test_returns_false_on_4xx(self):
        n = _make_enabled()
        response = MagicMock(status_code=400, text='{"ok":false}')
        with patch("app.utils.telegram_notifier.requests.post", return_value=response):
            assert n.send_message("hi") is False

    def test_returns_false_on_network_error(self):
        import requests as _req

        n = _make_enabled()
        with patch("app.utils.telegram_notifier.requests.post", side_effect=_req.ConnectionError("boom")):
            assert n.send_message("hi") is False

    def test_custom_api_base(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:a")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_API_BASE", "http://localhost:8081")
        n = TelegramNotifier()
        response = MagicMock(status_code=200, text="{}")
        with patch("app.utils.telegram_notifier.requests.post", return_value=response) as post:
            assert n.send_message("hi") is True
            url = post.call_args.args[0]
            assert url.startswith("http://localhost:8081/bot1:a/sendMessage")


# ─── High-level helpers ──────────────────────────────────────────
def _wait_for_notifier_thread():
    """Join the daemon thread that the notifier spawns, with a small timeout."""
    for t in threading.enumerate():
        if t.name == "telegram-notifier":
            t.join(timeout=2)
            return
    # If the thread has already finished, it is no longer in enumerate().
    # Give the runtime a moment to clean up; this is best-effort.
    import time

    time.sleep(0.05)


class TestHighLevelHelpers:
    def test_notify_test_failure_truncates_long_errors(self):
        n = _make_enabled()
        long_error = "x" * 5000
        captured: dict = {}
        response = MagicMock(status_code=200, text="{}")

        def fake_post(url, json=None, timeout=None):
            captured["text"] = json["text"]
            return response

        with patch("app.utils.telegram_notifier.requests.post", side_effect=fake_post):
            n.notify_test_failure("test_x", long_error)
            _wait_for_notifier_thread()
        assert "x" * 800 in captured["text"]
        # The full 5000-char error must have been truncated, leaving a
        # trailing "…" before the closing </code> tag.
        assert "…" in captured["text"]
        assert len(captured["text"]) < 1100  # well under the 5000-char input

    def test_notify_test_end_builds_summary(self):
        n = _make_enabled()
        captured: dict = {}
        response = MagicMock(status_code=200, text="{}")

        def fake_post(url, json=None, timeout=None):
            captured["text"] = json["text"]
            return response

        with patch("app.utils.telegram_notifier.requests.post", side_effect=fake_post):
            n.notify_test_end(
                suite_name="nightly",
                result="PASSED",
                passed=42,
                failed=0,
                skipped=3,
                duration_seconds=12.5,
            )
            _wait_for_notifier_thread()
        body = captured["text"]
        assert "nightly" in body
        assert "PASSED" in body
        assert "42" in body
        assert "12.5s" in body
        assert "✅" in body

    def test_notify_critical_error_uses_emoji(self):
        n = _make_enabled()
        captured: dict = {}
        response = MagicMock(status_code=200, text="{}")

        def fake_post(url, json=None, timeout=None):
            captured["text"] = json["text"]
            return response

        with patch("app.utils.telegram_notifier.requests.post", side_effect=fake_post):
            n.notify_critical_error("worker X died")
            _wait_for_notifier_thread()
        body = captured["text"]
        assert "🚨" in body
        assert "worker X died" in body

    def test_high_level_helpers_are_silent_when_not_configured(self):
        n = TelegramNotifier()  # disabled
        # None of these should raise or call requests.post
        with patch("app.utils.telegram_notifier.requests.post") as post:
            n.notify_test_start("s")
            n.notify_test_failure("t", "err")
            n.notify_test_end("s", "PASSED", 1, 0, 0)
            n.notify_critical_error("oops")
            post.assert_not_called()


# ─── Module-level singleton ──────────────────────────────────────
class TestModuleSingleton:
    def test_get_notifier_caches(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:a")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        a = get_notifier()
        b = get_notifier()
        assert a is b

    def test_reset_notifier_rebuilds(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:a")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        a = get_notifier()
        reset_notifier()
        b = get_notifier()
        assert a is not b

    def test_notifier_module_attribute_is_built(self):
        # The module exposes a ``notifier`` singleton for backwards compat.
        assert isinstance(tn.notifier, TelegramNotifier)


# ─── is_configured edge cases ───────────────────────────────────
class TestIsConfigured:
    @pytest.mark.parametrize(
        ("enabled", "token", "chat_id", "expected"),
        [
            (False, "1:a", "1", False),
            (True, "", "1", False),
            (True, "1:a", "", False),
            (True, "YOUR_BOT_TOKEN_HERE", "1", False),
            (True, "1:a", "YOUR_CHAT_ID_HERE", False),
            (True, "1:a", "1", True),
            (True, "9999999:xyzabcDEF", "555", True),
        ],
    )
    def test_matrix(self, monkeypatch, enabled, token, chat_id, expected):
        if enabled:
            monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", chat_id)
        n = TelegramNotifier()
        assert n.is_configured is expected


# ─── CI workflow env-var resolution ───────────────────────────────────
class TestCIWorkflowAliases:
    """Verify the notifier picks up the same bot used by the existing
    ``appleboy/telegram-action`` step in
    ``.github/workflows/*.yml``, which reads ``secrets.TELEGRAM_TOKEN``
    and ``secrets.TELEGRAM_TO`` and exposes them as ``TELEGRAM_TOKEN`` /
    ``TELEGRAM_TO`` env vars. Without this mapping, the in-process
    notifier would never find the bot in CI.
    """

    def test_telegram_token_maps_to_bot_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "111:right")
        monkeypatch.setenv("TELEGRAM_TO", "999")
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        n = TelegramNotifier()
        assert n.is_configured is True
        assert n.token == "111:right"
        assert n.chat_id == "999"

    def test_standard_name_takes_precedence(self, monkeypatch):
        # If both forms are set, the standard Pydantic-settings name wins
        # so the two layers never disagree.
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:standard")
        monkeypatch.setenv("TELEGRAM_TOKEN", "111:alias")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        n = TelegramNotifier()
        assert n.token == "111:standard"

    def test_dataforge_alias_still_honoured(self, monkeypatch):
        # Backwards compatibility: the DATAFORGE_-prefixed names still
        # work as a third-tier fallback.
        monkeypatch.setenv("DATAFORGE_TELEGRAM_BOT_TOKEN", "111:df")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_ENABLED", "true")
        n = TelegramNotifier()
        assert n.is_configured is True
        assert n.token == "111:df"
        assert n.chat_id == "1"

    def test_ci_alias_works_with_dataforge_alias(self, monkeypatch):
        # The CI alias and the DATAFORGE alias are different
        # namespaces, so both should be resolvable in different
        # environments.
        monkeypatch.setenv("TELEGRAM_TOKEN", "111:ci")
        monkeypatch.setenv("TELEGRAM_TO", "999")
        monkeypatch.setenv("DATAFORGE_TELEGRAM_ENABLED", "true")
        n = TelegramNotifier()
        # TE*_ENABLED is read from DATAFORGE_TELEGRAM_ENABLED, but the
        # token / chat id are read from the CI aliases.
        assert n.token == "111:ci"
        assert n.chat_id == "999"
        assert n.enabled is True
