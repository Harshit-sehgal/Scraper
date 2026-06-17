# compileall

- status: failed
- command: `/usr/bin/python3 -m compileall -q backend scripts architecture_validator.py`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T23:06:04.535765+00:00
- end_time: 2026-06-16T23:06:04.574462+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 60
- required: true
- redaction_applied: false

## stdout

```text
*** Error compiling 'backend/app/worker_queue_postgres_psycopg3.py'...
  File "backend/app/worker_queue_postgres_psycopg3.py", line 88
    _pool: Any = None
    ^^^^^^^^^^^^^^^^^
SyntaxError: annotated name '_pool' can't be global


```

## stderr

```text

```
