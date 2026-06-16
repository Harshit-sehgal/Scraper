# pyflakes

- status: failed
- command: `/usr/bin/python3 -m pyflakes backend/app backend/tests scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T18:39:09.069420+00:00
- end_time: 2026-06-16T18:39:11.394545+00:00
- duration_seconds: 2.33
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/tests/test_plan_enforcer_unknown_tier.py:87:9: local variable '_fake_get_user_tier_from_billing' is assigned to but never used

```

## stderr

```text

```
