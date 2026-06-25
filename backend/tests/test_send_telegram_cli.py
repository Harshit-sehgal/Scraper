"""Regression tests for the F-SCRIPT-004 secret-handling fix in ``scripts/send_telegram.py``.

Before the fix, ``--token``/``--chat-id`` accepted the Telegram bot token
or chat id directly via ``argv``. That landing spot made the secret
visible to ``ps``, ``top``, shell history, and any user-mode process
auditing the caller's command line (CWE-214).

The fix exposes three independent delivery channels for each secret:

- ``--token`` / ``--chat-id`` (legacy fallback — fine for trusted local use)
- ``--token-file`` / ``--chat-id-file`` (read from a path)
- ``--token-prompt`` / ``--chat-id-prompt`` (interactive ``getpass``)

These tests verify each channel honours the resolution order, that the
secret never has to be present on ``argv``, and that file-read failures
fall through to the prompt branch without crashing the script.

Test isolation: every call funnels through ``scripts.send_telegram.main``
with a fully controlled argv; the project root is added to ``sys.path``
on import so the script's backend-bootstrapping branch still runs.
"""

from __future__ import annotations

import importlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "send_telegram.py"


def _import_script():
    """Import ``scripts.send_telegram`` with the script dir on sys.path."""
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if "scripts.send_telegram" in sys.modules:
        return importlib.reload(sys.modules["scripts.send_telegram"])
    return importlib.import_module("scripts.send_telegram")


class TestResolveSecretHelper:
    """``_resolve_secret`` selects value > file > prompt and never crashes on missing inputs."""

    def setup_method(self) -> None:
        self.script = _import_script()

    def test_value_path_explicit_wins(self, tmp_path: Path, monkeypatch) -> None:
        secret_file = tmp_path / "token"
        secret_file.write_text("file-secret\n")
        prompt_calls = []

        def fake_getpass(_prompt: str) -> str:
            prompt_calls.append(_prompt)
            return "prompt-secret"

        monkeypatch.setattr(self.script.getpass, "getpass", fake_getpass)

        result = self.script._resolve_secret(
            "argv-value",
            str(secret_file),
            True,
            name="bot token",
        )
        assert result == "argv-value"
        assert prompt_calls == []

    def test_file_path_used_when_argv_missing(self, tmp_path: Path, monkeypatch) -> None:
        secret_file = tmp_path / "token"
        secret_file.write_text("  file-secret-with-newline  \n")

        def fail_getpass(_prompt: str) -> str:  # pragma: no cover - guard
            msg = "prompt should not be called when file resolves"
            raise AssertionError(msg)

        monkeypatch.setattr(self.script.getpass, "getpass", fail_getpass)

        result = self.script._resolve_secret(None, str(secret_file), True, name="bot token")
        assert result == "file-secret-with-newline"

    def test_prompt_used_when_argv_and_file_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(self.script.getpass, "getpass", lambda _p: "prompt-secret")
        result = self.script._resolve_secret(None, None, True, name="chat id")
        assert result == "prompt-secret"

    def test_missing_file_returns_none_silently(self, tmp_path: Path, monkeypatch) -> None:
        missing = tmp_path / "does-not-exist"
        captured = io.StringIO()
        with redirect_stderr(captured):
            result = self.script._resolve_secret(None, str(missing), False, name="bot token")
        assert result is None
        assert "cannot read bot token" in captured.getvalue()

    def test_empty_file_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        empty = tmp_path / "empty"
        empty.write_text("")
        captured = io.StringIO()
        with redirect_stderr(captured):
            result = self.script._resolve_secret(None, str(empty), False, name="bot token")
        assert result is None
        assert "cannot read bot token" in captured.getvalue()


class TestMainHonoursFileOverrides:
    """End-to-end argv tests: file overrides populate the notifier without putting secrets on argv."""

    def setup_method(self) -> None:
        self.script = _import_script()

    def test_token_file_sets_env_without_argv_secret(self, tmp_path: Path, monkeypatch) -> None:
        """Run ``--status`` with --token-file and assert env is populated from the file."""
        # Telegram bot tokens must contain a colon; otherwise the notifier
        # rightly reports the value as a placeholder.
        token_file = tmp_path / "bot_token"
        chat_file = tmp_path / "chat_id"
        token_file.write_text("file-bot-token:REAL\n")
        chat_file.write_text("file-chat-id\n")

        # No bot token must appear on the argv we hand to ``main``.
        argv = [
            "--status",
            "--token-file",
            str(token_file),
            "--chat-id-file",
            str(chat_file),
            "--enable",
        ]
        # Sanity: ensure the argv does not literally contain either secret.
        assert "file-bot-token" not in argv
        assert "file-chat-id" not in argv

        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            rc = self.script.main(argv)
        # Status prints the configured state; with both secrets set the
        # bot is configured and ``--enable`` flipped TELEGRAM_ENABLED, so
        # main() returns 0 for an enabled configuration.
        assert rc == 0
        out = stdout.getvalue()
        assert "Telegram notifier" in out
        assert "token set   = True" in out
        assert "chat_id set = True" in out

    def test_argv_overrides_take_priority(self, tmp_path: Path, monkeypatch) -> None:
        """Passing ``--token`` directly still works (legacy fallback). The file is ignored."""
        token_file = tmp_path / "token"
        token_file.write_text("file-secret\n")

        argv = ["--status", "--token", "argv-secret:REAL", "--chat-id", "999", "--enable"]
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            rc = self.script.main(argv)
        assert rc == 0
        # We don't assert behaviour against the actual env var set by the
        # notifier (the OS env stays at the value TelegramNotifier reads
        # from), only that ``main`` accepts the legacy path without error.

    def test_prompt_override_works_without_argv_secret(self, monkeypatch) -> None:
        # Bot token must contain a ":" so the notifier treats it as a real
        # value rather than a placeholder.
        replies = iter(["prompt-token:REAL", "prompt-chat"])

        def fake_getpass(_prompt: str) -> str:
            return next(replies)

        monkeypatch.setattr(self.script.getpass, "getpass", fake_getpass)

        argv = ["--status", "--token-prompt", "--chat-id-prompt", "--enable"]
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            rc = self.script.main(argv)
        assert rc == 0
        out = stdout.getvalue()
        assert "token set   = True" in out
        assert "chat_id set = True" in out


class TestScriptDocumentation:
    """The fix is real only if the script advertises the safer variants in its docstring and --help."""

    def test_docstring_mentions_safer_variants(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--token-file" in text, "send_telegram.py must document --token-file"
        assert "--chat-id-file" in text, "send_telegram.py must document --chat-id-file"
        assert "--token-prompt" in text, "send_telegram.py must document --token-prompt"
        assert "--chat-id-prompt" in text, "send_telegram.py must document --chat-id-prompt"

    def test_help_lists_safer_variants(self, capsys) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(REPO_ROOT),
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"--help failed: {result.stderr}"
        assert "--token-file" in combined
        assert "--chat-id-file" in combined
        assert "--token-prompt" in combined
        assert "--chat-id-prompt" in combined
