# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T23:10:33.614295+00:00
- end_time: 2026-06-16T23:10:33.641825+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
F401 [*] `typing.Any` imported but unused
  --> backend/app/worker_queue_postgres_psycopg3.py:20:35
   |
18 | import threading
19 | from contextlib import contextmanager
20 | from typing import TYPE_CHECKING, Any
   |                                   ^^^
21 |
22 | from app.config import settings as _settings
   |
help: Remove unused import: `typing.Any`

Found 1 error.
[*] 1 fixable with the `--fix` option.

```

## stderr

```text

```
