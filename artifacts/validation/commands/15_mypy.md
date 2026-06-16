# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T18:56:43.833121+00:00
- end_time: 2026-06-16T18:56:44.308966+00:00
- duration_seconds: 0.48
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/tests/test_auth_profile_store_cross_process.py:69: error: Value of type "dict[str, Any] | None" is not indexable  [index]
backend/tests/test_auth_profile_store_cross_process.py:94: error: Value of type "dict[str, Any] | None" is not indexable  [index]
backend/tests/test_auth_profile_store_cross_process.py:138: error: Value of type "dict[str, Any] | None" is not indexable  [index]
Found 3 errors in 1 file (checked 545 source files)

```

## stderr

```text

```
