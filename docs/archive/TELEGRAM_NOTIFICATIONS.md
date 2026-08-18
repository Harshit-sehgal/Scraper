# Telegram Bot Notifications

The DataForge scraper can push **start / failure / summary** notifications
for every test run (and other critical events) to a Telegram bot. This
lets you keep an eye on CI / nightly runs from your phone without having
to tail log files.

The notifier is **fail-safe** — when it is disabled or mis-configured it
short-circuits silently, so a flaky Telegram API can never break a test
run or the live scraper.

The project **already has a bot wired up** for CI notifications (the
`appleboy/telegram-action` step in `.github/workflows/*.yml` reads
`secrets.TELEGRAM_TOKEN` and `secrets.TELEGRAM_TO`). The same bot is
reused here, so you do not need to create a second one.

---

## 1. One-time setup

1. **The bot is already created.** It is stored as the
   `TELEGRAM_TOKEN` / `TELEGRAM_TO` GitHub Actions secrets on the
   `Harshit-sehgal/Scraper` repository. To use it locally, open
   *Settings → Secrets and variables → Actions* on GitHub and read off
   the two values.

2. **Edit your `.env`** (at the project root). Paste the values from
   GitHub into the matching lines:

   ```ini
   TELEGRAM_BOT_TOKEN=123456789:AAH_...   # = secrets.TELEGRAM_TOKEN
   TELEGRAM_CHAT_ID=987654321            # = secrets.TELEGRAM_TO
   TELEGRAM_ENABLED=true
   ```

   Equivalently, you can use the project-canonical aliases:

   ```ini
   DATAFORGE_TELEGRAM_BOT_TOKEN=123456789:AAH_...
   DATAFORGE_TELEGRAM_CHAT_ID=987654321
   DATAFORGE_TELEGRAM_ENABLED=true
   ```

   The notifier resolves credentials in this order (first hit wins):

   1. `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (also read by
      Pydantic-settings; this is the canonical form)
   2. `TELEGRAM_TOKEN` / `TELEGRAM_TO` (the names used by the existing
      `appleboy/telegram-action` step in CI workflows)
   3. `DATAFORGE_TELEGRAM_BOT_TOKEN` / `DATAFORGE_TELEGRAM_CHAT_ID`
      (backwards-compat alias)

3. **Verify** the wiring locally before relying on it in CI:

   ```bash
   # Status (does not send anything):
   make test-telegram
   # Or directly:
   python3 scripts/send_telegram.py --status

   # Send a one-off ping:
   make test-telegram-ping

   # Send a fake pass/fail summary:
   make test-telegram-summary
   RESULT=FAILED FAILED=2 make test-telegram-summary
   ```

---

## 2. What gets notified

| Event | Default | Message |
| --- | --- | --- |
| `pytest` session start | on | 🚀 *Test Suite Started* + suite name + UTC timestamp |
| `pytest` session end   | on | ✅ / ❌ *Test Suite Finished* + totals + duration |
| Individual test fail   | on | ❌ *Test Failure* + nodeid + truncated traceback |
| Critical app error     | on | 🚨 *CRITICAL ERROR* + truncated message |

Each message is dispatched on a daemon thread, so the test run is never
blocked on Telegram's API.

---

## 3. Using it in CI

The pytest conftest automatically sends the start / end / failure
messages when `DATAFORGE_TELEGRAM_ENABLED=true` is in the environment.
The simplest way to enable that is the `make test-notify` target,
which sets the flag for one `docker compose exec` invocation:

```bash
make test-notify
```

Under the hood:

```bash
docker compose exec -e TELEGRAM_ENABLED=true dataforge \
    python -m pytest -q --tb=short -k "not test_scrape_url_end_to_end_multiple_records"
```

In GitHub Actions, add the four env vars as repository / workflow
**Secrets** and export them in the relevant step:

```yaml
env:
  DATAFORGE_TELEGRAM_ENABLED: "true"
  DATAFORGE_TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
  DATAFORGE_TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
```

---

## 4. CLI helper

`scripts/send_telegram.py` is a small CLI that wraps the same
notifier used by the conftest. It is useful for ad-hoc pings and for
debugging credential issues from the shell.

```text
usage: send_telegram.py [-h] [--status]
                        [--token TOKEN] [--chat-id CHAT_ID] [--enable]
                        [--parse-mode {HTML,Markdown,MarkdownV2}]
                        [--summary] [--suite SUITE]
                        [--result {PASSED,FAILED}]
                        [--passed PASSED] [--failed FAILED]
                        [--skipped SKIPPED] [--duration DURATION]
                        [--critical CRITICAL]
                        [message]
```

Exit codes:

* `0` — message accepted by the Telegram API (or `--status` reports
  fully configured)
* `1` — the bot is configured but Telegram rejected the message
  (4xx/5xx or network error). Check `bot_token` and `chat_id`.
* `2` — the bot is **not** configured (missing token, missing chat id,
  placeholder value, or `TELEGRAM_ENABLED` is not `true`)

---

## 5. Local Bot API server (optional)

For very high-throughput or air-gapped deployments, you can run your
own [Telegram Bot API server](https://github.com/tdlib/telegram-bot-api)
and point the notifier at it:

```ini
DATAFORGE_TELEGRAM_API_BASE=http://localhost:8081
```

The default `https://api.telegram.org` is fine for most use cases.

---

## 6. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `make test-telegram` shows `disabled` | `DATAFORGE_TELEGRAM_ENABLED` is not `true`, or the env file isn't being loaded |
| `make test-telegram` shows `misconfigured` | `BOT_TOKEN` or `CHAT_ID` is still the placeholder (`YOUR_BOT_TOKEN_HERE`) or is empty |
| `python3 scripts/send_telegram.py "hi"` prints `HTTP 401` | Token is wrong — double-check with @BotFather |
| `HTTP 400 chat not found` | Chat id is wrong, **or** the user has not yet started a chat with the bot (send `/start` to the bot from the target account) |
| Notifications never arrive but the script says `OK` | Check the **chat id** — group / channel ids are negative numbers (e.g. `-1001234567890`) and need the bot to be a member of the group |
