# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T18:28:47.060043+00:00
- end_time: 2026-06-13T18:28:47.113000+00:00
- duration_seconds: 0.05
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
TRY004 Prefer `TypeError` exception for invalid type
   --> backend/app/billing/webhooks.py:142:13
    |
140 |         loaded = json.loads(raw_body.decode("utf-8"))
141 |         if not isinstance(loaded, dict):
142 |             raise ValueError("Webhook payload must be a JSON object")
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
143 |         body: dict[str, Any] = loaded
144 |     except Exception as exc:
    |

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/billing/webhooks.py:142:30
    |
140 |         loaded = json.loads(raw_body.decode("utf-8"))
141 |         if not isinstance(loaded, dict):
142 |             raise ValueError("Webhook payload must be a JSON object")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
143 |         body: dict[str, Any] = loaded
144 |     except Exception as exc:
    |
help: Assign to variable; remove string literal

Found 2 errors.
No fixes available (1 hidden fix can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```
