# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T21:13:54.198465+00:00
- end_time: 2026-06-16T21:13:54.618863+00:00
- duration_seconds: 0.42
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/tests/test_pagination_sync.py:208: error: Value of type "Callable[[BaseModel], dict[str, FieldInfo]]" is not indexable  [index]
Found 1 error in 1 file (checked 554 source files)

```

## stderr

```text

```
