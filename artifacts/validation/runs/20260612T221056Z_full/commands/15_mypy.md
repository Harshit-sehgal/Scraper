# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T22:14:43.070893+00:00
- end_time: 2026-06-12T22:14:43.649118+00:00
- duration_seconds: 0.58
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/models.py:427: error: Name "auth_profile_id" already defined on line 420  [no-redef]
backend/app/routers/workflow.py:180: error: Item "dict[Any, Any]" of "Any | dict[Any, Any]" has no attribute "model_dump"  [union-attr]
backend/app/plan_enforcer.py:25: error: Module has no attribute "get"  [attr-defined]
Found 3 errors in 3 files (checked 545 source files)

```

## stderr

```text

```
