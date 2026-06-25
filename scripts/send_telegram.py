#!/usr/bin/env python3
"""Send a one-off message to the configured Telegram bot.

Usage
-----
* Default (uses DATAFORGE_TELEGRAM_* env vars / .env)::

      python3 scripts/send_telegram.py "Hello from the scraper"

* Override the bot token / chat id on the command line::

      python3 scripts/send_telegram.py \\
          --token-file /run/secrets/telegram_bot_token \\
          --chat-id-file /run/secrets/telegram_chat_id "manual ping"

  Avoid passing the token directly via ``--token`` so the secret does
  not land in shell history, ``ps``, or process accounting. The
  ``--token`` / ``--chat-id`` overrides remain available for trusted
  local use, but prefer the file-based variants in CI.

* Prompt for the token interactively (useful in shell scripts)::

      python3 scripts/send_telegram.py \\
          --token-prompt --chat-id-prompt "manual ping"

* Print the current status without sending anything::

      python3 scripts/send_telegram.py --status

* Send a test-suite-style summary::

      python3 scripts/send_telegram.py --summary \\
          --suite "nightly" --result FAILED \\
          --passed 120 --failed 3 --skipped 5

* Critical-error notification::

      python3 scripts/send_telegram.py --critical "Worker X exited"

The script is deliberately dependency-light: it imports the project's
``app.utils.telegram_notifier`` so that the same configuration
mechanism (env vars, .env, settings) is used as the live scraper and
the test suite. It exits with code 0 on a successful send, 2 when
the bot is not configured, and 1 on any other failure.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

# Ensure the backend package is importable when this script is run
# directly from the project root (i.e. ``python3 scripts/send_telegram.py``).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a message via the configured Telegram bot.",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default=None,
        help="Plain-text message body to send. Ignored when --summary or --critical is used.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the current bot status and exit (no message is sent).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help=(
            "Override the bot token (otherwise read from env / .env). "
            "Prefer --token-file or --token-prompt to avoid leaking the "
            "secret into shell history or process accounting."
        ),
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help=("Read the bot token from the first line of PATH, trimmed of trailing whitespace. Safer than --token."),
    )
    parser.add_argument(
        "--token-prompt",
        action="store_true",
        help="Prompt for the bot token via getpass instead of passing it on argv.",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help=(
            "Override the chat id (otherwise read from env / .env). "
            "Prefer --chat-id-file or --chat-id-prompt to avoid leaking it."
        ),
    )
    parser.add_argument(
        "--chat-id-file",
        default=None,
        help="Read the chat id from the first line of PATH.",
    )
    parser.add_argument(
        "--chat-id-prompt",
        action="store_true",
        help="Prompt for the chat id via getpass instead of passing it on argv.",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Force TELEGRAM_ENABLED=true for this invocation.",
    )
    parser.add_argument(
        "--parse-mode",
        default="HTML",
        choices=("HTML", "Markdown", "MarkdownV2"),
        help="Telegram parse mode (default: HTML).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Send a formatted test-suite summary (use --suite/--result/--passed/--failed/--skipped).",
    )
    parser.add_argument("--suite", default="manual")
    parser.add_argument("--result", default="PASSED", choices=("PASSED", "FAILED"))
    parser.add_argument("--passed", type=int, default=0)
    parser.add_argument("--failed", type=int, default=0)
    parser.add_argument("--skipped", type=int, default=0)
    parser.add_argument("--duration", type=float, default=None, help="Optional duration in seconds.")
    parser.add_argument(
        "--critical",
        default=None,
        help="Send a critical-error notification with the given message body.",
    )
    return parser


def _resolve_secret(arg_value: str | None, file_path: str | None, prompt: bool, *, name: str) -> str | None:
    """Resolve a CLI-supplied secret from the value, file, or interactive prompt.

    Priority: explicit ``arg_value`` > ``file_path`` > ``prompt``. Returns
    ``None`` when none of the options provided the secret.
    """
    if arg_value:
        return arg_value
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8").splitlines()[0].strip()
        except (FileNotFoundError, IndexError, PermissionError, OSError) as exc:
            print(f"ERROR: cannot read {name} from {file_path}: {exc}", file=sys.stderr)
            return None
    if prompt:
        try:
            return getpass.getpass(f"Enter {name}: ")
        except (EOFError, KeyboardInterrupt):
            print(f"ERROR: {name} prompt aborted.", file=sys.stderr)
            return None
    return None


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    # Apply CLI overrides to the environment BEFORE importing the
    # notifier module, so the notifier picks them up.
    token_override = _resolve_secret(args.token, args.token_file, args.token_prompt, name="bot token")
    chat_id_override = _resolve_secret(args.chat_id, args.chat_id_file, args.chat_id_prompt, name="chat id")
    if token_override is not None:
        os.environ["TELEGRAM_BOT_TOKEN"] = token_override
    if chat_id_override is not None:
        os.environ["TELEGRAM_CHAT_ID"] = chat_id_override
    if args.enable:
        os.environ["TELEGRAM_ENABLED"] = "true"

    from app.utils.telegram_notifier import TelegramNotifier

    notifier = TelegramNotifier()

    if args.status:
        print(f"Telegram notifier: {notifier.status}")
        print(f"  api_base    = {notifier.api_base}")
        print(f"  token set   = {bool(notifier.token)}")
        print(f"  chat_id set = {bool(notifier.chat_id)}")
        return 0 if notifier.is_configured else 2

    if not notifier.is_configured:
        print(
            "Telegram notifier is not configured.\n"
            "Set DATAFORGE_TELEGRAM_BOT_TOKEN, DATAFORGE_TELEGRAM_CHAT_ID, and\n"
            "DATAFORGE_TELEGRAM_ENABLED=true in your environment or .env,\n"
            "or pass --token-file / --chat-id-file / --token-prompt / --chat-id-prompt\n"
            "(or --token / --chat-id for trusted local use).",
            file=sys.stderr,
        )
        return 2

    if args.summary:
        ok = notifier.send_now(
            f"{'✅' if args.result == 'PASSED' else '❌'} <b>Manual test summary</b>\n"
            f"Suite: <code>{args.suite}</code>\n"
            f"Result: <b>{args.result}</b>\n"
            f"Passed: <b>{args.passed}</b>\n"
            f"Failed: <b>{args.failed}</b>\n"
            f"Skipped: <b>{args.skipped}</b>"
            + (f"\nDuration: <code>{args.duration:.1f}s</code>" if args.duration is not None else ""),
            parse_mode=args.parse_mode,
        )
    elif args.critical is not None:
        ok = notifier.send_now(
            f"🚨 <b>CRITICAL ERROR</b>\n\n<pre><code>{args.critical[:1500]}</code></pre>",
            parse_mode=args.parse_mode,
        )
    elif args.message is not None:
        ok = notifier.send_now(args.message, parse_mode=args.parse_mode)
    else:
        print("Nothing to send. Provide a message body, or use --status / --summary / --critical.", file=sys.stderr)
        return 1

    if ok:
        print("OK — Telegram message accepted by the bot API.")
        return 0
    print("FAILED — Telegram API did not accept the message (see logs above).", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
