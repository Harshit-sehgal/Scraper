# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T18:39:09.042597+00:00
- end_time: 2026-06-16T18:39:09.069174+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
UP017 [*] Use `datetime.UTC` alias
  --> backend/app/utils/auth_profile_store.py:61:25
   |
60 | def _utc_now_iso() -> str:
61 |     return datetime.now(timezone.utc).isoformat()
   |                         ^^^^^^^^^^^^
   |
help: Convert to `datetime.UTC` alias

Found 1 error.
[*] 1 fixable with the `--fix` option.

```

## stderr

```text

```
