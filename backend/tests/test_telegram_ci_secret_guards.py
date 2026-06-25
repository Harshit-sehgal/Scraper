"""Static guard for F-CI-005 — non-empty-secret CI guards.

Regression target:
    - F-CI-005 (P1): GHA substitutes an empty string for an unset secret,
      so a misconfigured bot token / chat ID combination must not call
      the action with empty values and silently swallow the notification.

Lock-in: every Telegram notification step in every workflow must
require direct truthiness checks for both env-backed secrets. GitHub's
documented expression semantics treat empty strings as falsy, and this
avoids unsupported helper functions inside workflow ``if:`` expressions.

This is text-only; we don't invoke the action in CI because GHA
semantics are too easily mocked. The complement for production-rail
action-pin enforcement already lives in
``backend/tests/test_workflow_action_pins.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# The full set of cron / post-merge CI workflows that gate a Telegram
# notification behind ``env.TELEGRAM_*``. ``stale-cleanup.yml`` was
# excluded earlier (it does not have a Telegram notify step).
TELEGRAM_NOTIFY_WORKFLOWS = (
    "ci.yml",
    "browser-e2e.yml",
    "optional-suites.yml",
    "postgres-tests.yml",
    "nightly-integration.yml",
    "golden-dataset.yml",
    "validate-production.yml",
)


def _has_telegram_notify(path: Path) -> bool:
    """True if this workflow has a Telegram notify step (search for `appleboy/telegram-action`)."""
    text = path.read_text(encoding="utf-8")
    return "appleboy/telegram-action" in text or "TELEGRAM_TOKEN" in text


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


_TELEGRAM_GUARD = re.compile(r"if:\s*env\.TELEGRAM_TOKEN\s*&&\s*env\.TELEGRAM_TO\s*$", re.MULTILINE)


class TestTelegramSecretGuards:
    """Telegram notify steps use env truthiness so empty secrets fail closed."""

    def test_ci_yamls_have_telegram_workflows(self) -> None:
        for name in TELEGRAM_NOTIFY_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            assert path.is_file(), f"expected {path} — workflow file removed"

    def test_each_telegram_notify_uses_truthiness_guard(self) -> None:
        """Every workflow with a Telegram step must use a supported truthiness guard."""
        for name in TELEGRAM_NOTIFY_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            if not _has_telegram_notify(path):
                continue  # Workflow without Telegram step; nothing to assert.
            m = _TELEGRAM_GUARD.search(text)
            assert m, (
                f"{name}: Telegram notify `if:` must use"
                " `env.TELEGRAM_TOKEN && env.TELEGRAM_TO`. F-CI-005: GitHub"
                " Actions treats empty strings as falsy, so this skips the"
                " action when either env-backed secret is unset or empty."
            )

    def test_bare_telegram_guard_regression_forbidden(self) -> None:
        """The old bare ``!= ''`` comparison form is no longer the lock-in."""
        bare_only = re.compile(r"if:\s*env\.TELEGRAM_TOKEN\s*!=\s*''\s*&&\s*env\.TELEGRAM_TO\s*!=\s*''\s*$")
        for name in TELEGRAM_NOTIFY_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            if not _has_telegram_notify(path):
                continue
            assert not bare_only.search(text), (
                f"{name}: Telegram notify `if:` still has the bare ``!= ''``"
                " guard. F-CI-005 now locks the documented truthiness form so"
                " empty-secret substitutions are rejected."
            )

    def test_unsupported_length_function_is_not_used(self) -> None:
        """GitHub Actions does not document a `length()` expression helper."""
        for name in TELEGRAM_NOTIFY_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            if not _has_telegram_notify(path):
                continue
            assert "length(" not in text, (
                f"{name}: Telegram notify guard must not use unsupported GitHub Actions expression helper `length(...)`."
            )
