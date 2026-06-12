# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T18:48:15.893390+00:00
- end_time: 2026-06-12T18:48:18.583267+00:00
- duration_seconds: 2.69
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/models.py:583: error: Name "AuthProfile" already defined on line 486  [no-redef]
backend/app/services/workflow_runner.py:216: error: Name "rows" already defined on line 208  [no-redef]
Found 2 errors in 2 files (checked 537 source files)

```

## stderr

```text

```
